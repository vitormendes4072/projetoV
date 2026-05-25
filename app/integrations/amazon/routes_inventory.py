import logging

from flask import jsonify, render_template, request
from flask_login import login_required

from app import db
from app.models import AmazonConnection
from app.models.amazon_inventory import AmazonInventorySnapshot
from app.integrations.amazon import amazon
from app.integrations.amazon.utils import user_key
from app.integrations.amazon.service import get_inventory_summaries, upsert_inventory_snapshots
from app.integrations.amazon.inventory import get_min_stock_map

logger = logging.getLogger(__name__)


@amazon.get("/inventory")
@login_required
def inventory_page():
    page = request.args.get("page", 1, type=int)
    q    = request.args.get("q", "").strip()

    stmt = (
        db.select(AmazonInventorySnapshot)
        .filter_by(user_id=user_key())
        .order_by(AmazonInventorySnapshot.updated_at.desc())
    )

    if q:
        stmt = stmt.filter(
            db.or_(
                AmazonInventorySnapshot.seller_sku.ilike(f"%{q}%"),
                AmazonInventorySnapshot.asin.ilike(f"%{q}%"),
            )
        )

    pagination = db.paginate(stmt, page=page, per_page=50, error_out=False)

    # Cruzar SKUs da página com min_stock dos produtos vinculados (2 queries fixas).
    page_skus = [snap.seller_sku for snap in pagination.items]
    min_stock_map = get_min_stock_map(user_key(), page_skus)
    alert_count = sum(
        1 for snap in pagination.items
        if snap.seller_sku in min_stock_map
        and (snap.fulfillable_qty or 0) <= min_stock_map[snap.seller_sku]
    )

    return render_template(
        "amazon/inventory.html",
        pagination=pagination,
        q=q,
        min_stock_map=min_stock_map,
        alert_count=alert_count,
    )


@amazon.post("/sync_inventory")
@login_required
def sync_inventory():
    conn = db.session.scalar(db.select(AmazonConnection).filter_by(user_id=user_key()))
    if not conn:
        return jsonify({"ok": False, "error": "Integração Amazon não configurada"}), 400

    try:
        summaries = get_inventory_summaries(conn, conn.marketplace_id)
    except Exception:
        logger.exception("Erro ao buscar inventory summaries")
        return jsonify({"ok": False, "error": "Falha ao buscar inventário"}), 400

    inserted, updated = upsert_inventory_snapshots(
        user_id=user_key(),
        marketplace_id=conn.marketplace_id,
        summaries=summaries,
    )

    db.session.commit()
    return jsonify({"ok": True, "inserted": inserted, "updated": updated, "total": len(summaries)})
