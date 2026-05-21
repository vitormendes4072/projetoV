import csv
import io
import logging
from datetime import timedelta

from flask import jsonify, make_response
from flask_login import login_required, current_user

from app import db
from app.models import AmazonConnection, AmazonOrder
from app.models.amazon_finances import AmazonFinancialEvent
from app.integrations.amazon import amazon
from app.integrations.amazon.utils import user_key, utcnow, iso_z
from app.integrations.amazon.service import sync_financial_events
from app.integrations.amazon.profit_service import compute_order_profit, compute_order_item_breakdown

logger = logging.getLogger(__name__)

from app.integrations.amazon.utils import SP_TZ


@amazon.get("/orders")
@login_required
def orders_page():
    from flask import render_template, request

    page   = request.args.get("page", 1, type=int)
    q      = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()

    stmt = (
        db.select(AmazonOrder)
        .filter_by(user_id=user_key())
        .order_by(AmazonOrder.purchase_date.desc().nullslast(), AmazonOrder.id.desc())
    )

    if status:
        stmt = stmt.filter(AmazonOrder.order_status == status)
    if q:
        stmt = stmt.filter(AmazonOrder.amazon_order_id.ilike(f"%{q}%"))

    pagination = db.paginate(stmt, page=page, per_page=50, error_out=False)

    return render_template(
        "amazon/orders.html",
        pagination=pagination,
        q=q,
        status=status,
        SP_TZ=SP_TZ,
    )


@amazon.get("/orders/exportar-csv")
@login_required
def exportar_orders_csv():
    orders = db.session.scalars(
        db.select(AmazonOrder)
        .filter_by(user_id=user_key())
        .order_by(AmazonOrder.purchase_date.desc().nullslast())
    ).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['order_id', 'status', 'data_compra', 'total', 'moeda', 'qtd_itens'])
    for o in orders:
        writer.writerow([
            o.amazon_order_id,
            o.order_status or '',
            o.purchase_date.strftime('%Y-%m-%d') if o.purchase_date else '',
            o.order_total_amount or '',
            o.currency or '',
            o.num_items_shipped or '',
        ])

    resp = make_response(buf.getvalue())
    resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
    resp.headers['Content-Disposition'] = 'attachment; filename="pedidos_amazon.csv"'
    return resp


@amazon.get("/profit/order/<amazon_order_id>")
@login_required
def profit_order(amazon_order_id: str):
    conn = db.session.scalar(db.select(AmazonConnection).filter_by(user_id=user_key()))
    if not conn:
        return jsonify({"ok": False, "error": "Integração Amazon não configurada"}), 400

    default_tax_rate = float(getattr(current_user, "default_tax_rate", 4.0) or 0.0)

    result = compute_order_profit(user_key(), amazon_order_id, default_tax_rate)

    if result is not None:
        return jsonify(result)

    # Nenhum ShipmentEventList: tenta sync curto focado na data do pedido
    order = db.session.scalar(db.select(AmazonOrder).filter_by(user_id=user_key(), amazon_order_id=amazon_order_id))

    start = utcnow() - timedelta(days=7)
    if order and order.purchase_date:
        from datetime import timezone
        purchase_utc = order.purchase_date.astimezone(timezone.utc)
        start = purchase_utc - timedelta(days=5)

    start_iso = iso_z(start)

    try:
        db.session.execute(
            db.delete(AmazonFinancialEvent)
            .where(
                AmazonFinancialEvent.user_id == user_key(),
                AmazonFinancialEvent.posted_date >= start,
            )
        )
        db.session.flush()

        sync_financial_events(conn, user_id=user_key(), posted_after_iso=start_iso)
        db.session.commit()

        result = compute_order_profit(user_key(), amazon_order_id, default_tax_rate)

    except Exception:
        db.session.rollback()
        logger.exception("Falha no sync_finances curto para profit_order %s", amazon_order_id)
        return jsonify({
            "ok": False,
            "amazon_order_id": amazon_order_id,
            "mode": "no_finance_events",
            "message": "Não encontrei ShipmentEventList e falhou ao tentar sync_finances curto.",
            "from": start_iso,
        }), 400

    if result is None:
        return jsonify({
            "ok": True,
            "amazon_order_id": amazon_order_id,
            "mode": "no_finance_events",
            "message": (
                "Nenhum ShipmentEventList encontrado para este pedido mesmo após sync curto. "
                "Tente ampliar a janela: POST /sync_finances?days=30&wipe=1"
            ),
            "from": start_iso,
        })

    return jsonify(result)


@amazon.get("/orders/<amazon_order_id>/details")
@login_required
def order_details(amazon_order_id: str):
    default_tax_rate = float(getattr(current_user, "default_tax_rate", 0.0) or 0.0)
    result = compute_order_item_breakdown(user_key(), amazon_order_id, default_tax_rate)
    return jsonify(result)
