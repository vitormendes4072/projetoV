import logging
from datetime import timedelta

from flask import request, jsonify
from flask_login import login_required

from app import db
from app.models import AmazonConnection, AmazonOrder, AmazonOrderItem
from app.models.amazon_finances import AmazonFinancialEvent
from app.integrations.amazon import amazon
from app.integrations.amazon.utils import user_key, utcnow, iso_z, compute_sync_start
from app.integrations.amazon.service import (
    list_orders,
    list_order_items,
    sync_orders_and_items,
    sync_financial_events,
)

logger = logging.getLogger(__name__)


@amazon.route("/sync_orders_only", methods=["GET", "POST"])
@login_required
def sync_orders_only():
    """Sync apenas pedidos (sem itens). Útil para popular listagem rapidamente."""
    conn = AmazonConnection.query.filter_by(user_id=user_key()).first()
    if not conn:
        return jsonify({"ok": False, "error": "Integração Amazon não configurada"}), 400

    days = int(request.args.get("days", "30"))
    created_after = iso_z(utcnow() - timedelta(days=days))

    try:
        orders = list_orders(conn, created_after_iso=created_after)
    except Exception:
        logger.exception("Erro em sync_orders_only")
        return jsonify({"ok": False, "error": "Falha ao buscar pedidos", "created_after": created_after}), 400

    upserted = 0
    for o in orders:
        amazon_order_id = o.get("AmazonOrderId")
        if not amazon_order_id:
            continue

        from app.integrations.amazon.utils import parse_iso_dt, to_sp
        order = AmazonOrder.query.filter_by(user_id=user_key(), amazon_order_id=amazon_order_id).first()
        if not order:
            order = AmazonOrder(
                user_id=user_key(),
                amazon_order_id=amazon_order_id,
                marketplace_id=conn.marketplace_id,
            )

        order.order_status = o.get("OrderStatus")

        dt = parse_iso_dt(o.get("PurchaseDate", ""))
        order.purchase_date = to_sp(dt)

        ot = o.get("OrderTotal") or {}
        order.currency = ot.get("CurrencyCode")
        order.order_total_amount = ot.get("Amount")

        order.raw_json = o
        db.session.add(order)
        upserted += 1

    db.session.commit()

    return jsonify({
        "ok": True,
        "from": created_after,
        "orders_upserted": upserted,
        "orders_returned_by_api": len(orders),
    })


@amazon.post("/sync_orders")
@login_required
def sync_orders():
    conn = AmazonConnection.query.filter_by(user_id=user_key()).first()
    if not conn:
        return jsonify({"ok": False, "error": "Integração Amazon não configurada"}), 400

    days = int(request.args.get("days", "30"))
    start = compute_sync_start(conn, days_default=days)
    start_iso = iso_z(start)

    try:
        orders_upserted, items_inserted, returned = sync_orders_and_items(
            conn, user_id=user_key(), created_after_iso=start_iso
        )
        conn.last_sync_at = utcnow()
        db.session.add(conn)
        db.session.commit()
        return jsonify({
            "ok": True,
            "from": start_iso,
            "orders": orders_upserted,
            "items": items_inserted,
            "returned": returned,
        })
    except Exception:
        db.session.rollback()
        logger.exception("Erro em sync_orders")
        return jsonify({"ok": False, "error": "Falha ao sincronizar pedidos", "from": start_iso}), 400


@amazon.post("/sync_finances")
@login_required
def sync_finances():
    """
    Sync Finances quota-safe.
    - days: janela curta (default 7)
    - wipe=1: apaga eventos do range e reimporta (idempotente)
    - force_days=1: ignora last_sync_at e usa agora-days
    """
    conn = AmazonConnection.query.filter_by(user_id=user_key()).first()
    if not conn:
        return jsonify({"ok": False, "error": "Integração Amazon não configurada"}), 400

    days = int(request.args.get("days", "7"))
    wipe = request.args.get("wipe", "1") == "1"
    force_days = request.args.get("force_days", "0") == "1"

    if force_days:
        start = utcnow() - timedelta(days=days)
    else:
        start = compute_sync_start(conn, days_default=days)

    start_iso = iso_z(start)

    try:
        if wipe:
            AmazonFinancialEvent.query.filter(
                AmazonFinancialEvent.user_id == user_key(),
                AmazonFinancialEvent.posted_date >= start,
            ).delete(synchronize_session=False)
            db.session.flush()

        conn.last_sync_at = utcnow()
        db.session.add(conn)

        events_count = sync_financial_events(conn, user_id=user_key(), posted_after_iso=start_iso)
        db.session.commit()
        return jsonify({"ok": True, "from": start_iso, "financial_events": events_count, "wipe": wipe})
    except Exception:
        db.session.rollback()
        logger.exception("Erro em sync_finances")
        return jsonify({"ok": False, "error": "Falha ao sincronizar financeiro", "from": start_iso}), 400


@amazon.post("/sync_full")
@login_required
def sync_full():
    """Sync completo: Orders+Items + Finances + atualiza last_sync_at."""
    conn = AmazonConnection.query.filter_by(user_id=user_key()).first()
    if not conn:
        return jsonify({"ok": False, "error": "Integração Amazon não configurada"}), 400

    now = utcnow()
    days = int(request.args.get("days", "30"))
    start = compute_sync_start(conn, days_default=days)
    start_iso = iso_z(start)

    try:
        orders_count, items_count, returned = sync_orders_and_items(
            conn, user_id=user_key(), created_after_iso=start_iso
        )

        AmazonFinancialEvent.query.filter(
            AmazonFinancialEvent.user_id == user_key(),
            AmazonFinancialEvent.posted_date >= start,
        ).delete(synchronize_session=False)
        db.session.flush()

        events_count = sync_financial_events(conn, user_id=user_key(), posted_after_iso=start_iso)

        conn.last_sync_at = now
        db.session.add(conn)
        db.session.commit()

        return jsonify({
            "ok": True,
            "from": start_iso,
            "orders": orders_count,
            "items": items_count,
            "returned_orders": returned,
            "financial_events": events_count,
        })
    except Exception:
        db.session.rollback()
        logger.exception("Erro em sync_full")
        return jsonify({"ok": False, "error": "Falha no sync completo", "from": start_iso}), 400


@amazon.get("/sync_full_debug")
@login_required
def sync_full_debug():
    return sync_full()


@amazon.post("/sync_items_batch")
@login_required
def sync_items_batch():
    conn = AmazonConnection.query.filter_by(user_id=user_key()).first()
    if not conn:
        return jsonify({"ok": False, "error": "Integração Amazon não configurada"}), 400

    limit = int(request.args.get("limit", "15"))

    orders = (
        AmazonOrder.query
        .filter_by(user_id=user_key())
        .order_by(AmazonOrder.purchase_date.desc().nullslast(), AmazonOrder.id.desc())
        .limit(200)
        .all()
    )

    processed = 0
    inserted_items = 0
    skipped = 0

    for o in orders:
        if processed >= limit:
            break

        exists = AmazonOrderItem.query.filter_by(
            user_id=user_key(), amazon_order_id=o.amazon_order_id
        ).first()
        if exists:
            skipped += 1
            continue

        try:
            items = list_order_items(conn, o.amazon_order_id)
        except Exception as e:
            return jsonify({"ok": False, "error": f"Falha ao buscar itens {o.amazon_order_id}: {repr(e)}"}), 400

        for it in items:
            ip = it.get("ItemPrice") or {}
            item = AmazonOrderItem(
                user_id=user_key(),
                amazon_order_id=o.amazon_order_id,
                seller_sku=it.get("SellerSKU"),
                asin=it.get("ASIN"),
                quantity=it.get("QuantityOrdered"),
                item_price=ip.get("Amount"),
                currency=ip.get("CurrencyCode"),
                raw_json=it,
            )
            db.session.add(item)
            inserted_items += 1

        processed += 1

    db.session.commit()
    return jsonify({
        "ok": True,
        "processed_orders": processed,
        "skipped_orders": skipped,
        "inserted_items": inserted_items,
    })
