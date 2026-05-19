import logging

from flask import jsonify
from flask_login import login_required

from app import db
from app.models import AmazonConnection
from app.integrations.amazon import amazon
from app.integrations.amazon.utils import user_key
from app.integrations.amazon.service import get_inventory_summaries, upsert_inventory_snapshots

logger = logging.getLogger(__name__)


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
