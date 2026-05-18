import logging
from datetime import timedelta

from flask import current_app, request, jsonify
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
from app.integrations.amazon.jobs import job_sync_orders, job_sync_finances, job_sync_full

logger = logging.getLogger(__name__)


def _get_queue():
    return current_app.extensions["rq_queue"]


# ---------------------------------------------------------------------------
# Sync assíncrono (enfileira job, retorna 202 + job_id imediatamente)
# ---------------------------------------------------------------------------

@amazon.post("/sync_orders")
@login_required
def sync_orders():
    conn = AmazonConnection.query.filter_by(user_id=user_key()).first()
    if not conn:
        return jsonify({"ok": False, "error": "Integração Amazon não configurada"}), 400

    days = int(request.args.get("days", "30"))
    job = _get_queue().enqueue(job_sync_orders, user_key(), conn.id, days, job_timeout=300)
    return jsonify({"ok": True, "job_id": job.id, "status": "queued"}), 202


@amazon.post("/sync_finances")
@login_required
def sync_finances():
    conn = AmazonConnection.query.filter_by(user_id=user_key()).first()
    if not conn:
        return jsonify({"ok": False, "error": "Integração Amazon não configurada"}), 400

    days = int(request.args.get("days", "7"))
    job = _get_queue().enqueue(job_sync_finances, user_key(), conn.id, days, job_timeout=300)
    return jsonify({"ok": True, "job_id": job.id, "status": "queued"}), 202


@amazon.post("/sync_full")
@login_required
def sync_full():
    conn = AmazonConnection.query.filter_by(user_id=user_key()).first()
    if not conn:
        return jsonify({"ok": False, "error": "Integração Amazon não configurada"}), 400

    days = int(request.args.get("days", "30"))
    job = _get_queue().enqueue(job_sync_full, user_key(), conn.id, days, job_timeout=600)
    return jsonify({"ok": True, "job_id": job.id, "status": "queued"}), 202


@amazon.get("/jobs/<job_id>")
@login_required
def job_status(job_id):
    """Polling de status de um job. Retorna status + resultado quando finalizado."""
    from rq.job import Job
    from rq.exceptions import NoSuchJobError

    queue = _get_queue()
    try:
        job = Job.fetch(job_id, connection=queue.connection)
    except NoSuchJobError:
        return jsonify({"ok": False, "error": "Job não encontrado"}), 404

    status = job.get_status(refresh=True)
    payload = {"ok": True, "job_id": job_id, "status": str(status)}

    if status.value == "finished":
        payload["result"] = job.result
    elif status.value == "failed":
        payload["error"] = str(job.latest_result().exc_string) if job.latest_result() else "unknown"

    return jsonify(payload)


# ---------------------------------------------------------------------------
# Síncrono — debug/dev apenas (não bloqueia em produção)
# ---------------------------------------------------------------------------

@amazon.get("/sync_full_debug")
@login_required
def sync_full_debug():
    """Executa sync completo de forma síncrona. Apenas para desenvolvimento."""
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
        logger.exception("Erro em sync_full_debug")
        return jsonify({"ok": False, "error": "Falha no sync completo", "from": start_iso}), 400


# ---------------------------------------------------------------------------
# Operações leves — mantidas síncronas (< 2 s tipicamente)
# ---------------------------------------------------------------------------

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
