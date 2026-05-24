import csv
import io
import logging

from flask import Response, jsonify, render_template, request, stream_with_context
from flask_login import login_required, current_user

from app import db, limiter
from app.models import AmazonConnection, AmazonOrder
from app.integrations.amazon import amazon
from app.integrations.amazon.utils import user_key, SP_TZ
from app.integrations.amazon.profit_service import (
    compute_order_profit,
    compute_order_item_breakdown,
    _compute_order_start,
    refresh_order_finances,
    invalidate_order_profit_cache,
)

logger = logging.getLogger(__name__)


@amazon.get("/orders")
@login_required
def orders_page():
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


_CSV_CHUNK = 500


def _iter_orders_csv(uid: int):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['order_id', 'status', 'data_compra', 'total', 'moeda', 'qtd_itens'])
    yield buf.getvalue()
    buf.seek(0)
    buf.truncate()

    offset = 0
    while True:
        batch = db.session.scalars(
            db.select(AmazonOrder)
            .filter_by(user_id=uid)
            .order_by(AmazonOrder.purchase_date.desc().nullslast())
            .limit(_CSV_CHUNK)
            .offset(offset)
        ).all()
        if not batch:
            break
        for o in batch:
            writer.writerow([
                o.amazon_order_id,
                o.order_status or '',
                o.purchase_date.strftime('%Y-%m-%d') if o.purchase_date else '',
                o.order_total_amount or '',
                o.currency or '',
                o.num_items_shipped or '',
            ])
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate()
        offset += _CSV_CHUNK


@amazon.get("/orders/exportar-csv")
@login_required
def exportar_orders_csv():
    return Response(
        stream_with_context(_iter_orders_csv(user_key())),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename="pedidos_amazon.csv"'},
    )


@amazon.get("/profit/order/<amazon_order_id>")
@login_required
@limiter.limit("10 per minute")
def profit_order(amazon_order_id: str):
    """Leitura pura: retorna lucro calculado a partir dos dados locais. Não escreve no BD."""
    conn = db.session.scalar(db.select(AmazonConnection).filter_by(user_id=user_key()))
    if not conn:
        return jsonify({"ok": False, "error": "Integração Amazon não configurada"}), 400

    default_tax_rate = float(getattr(current_user, "default_tax_rate", 4.0) or 0.0)
    result = compute_order_profit(user_key(), amazon_order_id, default_tax_rate)

    if result is not None:
        return jsonify(result)

    # Sem ShipmentEventList local — indica ao cliente sem fazer writes.
    _, start_iso = _compute_order_start(user_key(), amazon_order_id)
    return jsonify({
        "ok": True,
        "amazon_order_id": amazon_order_id,
        "mode": "no_finance_events",
        "message": (
            "Nenhum ShipmentEventList encontrado para este pedido. "
            "Use POST /profit/order/<id>/refresh para buscar do SP-API."
        ),
        "from": start_iso,
    })


@amazon.post("/profit/order/<amazon_order_id>/refresh")
@login_required
@limiter.limit("5 per minute")
def profit_order_refresh(amazon_order_id: str):
    """Dispara sync curto de finances e recalcula o lucro. Separa a escrita do GET."""
    conn = db.session.scalar(db.select(AmazonConnection).filter_by(user_id=user_key()))
    if not conn:
        return jsonify({"ok": False, "error": "Integração Amazon não configurada"}), 400

    default_tax_rate = float(getattr(current_user, "default_tax_rate", 4.0) or 0.0)

    try:
        start_iso, _ = refresh_order_finances(conn, user_key(), amazon_order_id)
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Falha no sync_finances curto para profit_order_refresh %s", amazon_order_id)
        return jsonify({
            "ok": False,
            "amazon_order_id": amazon_order_id,
            "error": "Falha ao sincronizar finances do SP-API.",
        }), 500

    # Dados novos no DB — descarta a entrada em cache para este pedido.
    invalidate_order_profit_cache(user_key(), amazon_order_id, default_tax_rate)

    result = compute_order_profit(user_key(), amazon_order_id, default_tax_rate)

    if result is None:
        return jsonify({
            "ok": True,
            "amazon_order_id": amazon_order_id,
            "mode": "no_finance_events",
            "message": (
                "Nenhum ShipmentEventList encontrado mesmo após sync curto. "
                "Tente ampliar a janela: POST /sync_finances?days=30&wipe=1"
            ),
            "from": start_iso,
        })

    return jsonify(result)


@amazon.get("/orders/<amazon_order_id>/details")
@login_required
@limiter.limit("20 per minute")
def order_details(amazon_order_id: str):
    default_tax_rate = float(getattr(current_user, "default_tax_rate", 0.0) or 0.0)
    result = compute_order_item_breakdown(user_key(), amazon_order_id, default_tax_rate)
    return jsonify(result)
