from flask_login import current_user
from flask_smorest import abort

from app import db
from app.api import blp
from app.api.schemas import InventorySyncResultSchema
from app.models import AmazonConnection
from app.integrations.amazon.service import get_inventory_summaries, upsert_inventory_snapshots


@blp.post("/amazon/inventory/sync")
@blp.response(200, InventorySyncResultSchema, description="Resultado da sincronização de inventário")
def api_sync_inventory():
    """Sincroniza o inventário Amazon com o banco de dados local.

    Busca os snapshots de estoque via SP-API e faz upsert na tabela local.
    """
    conn = AmazonConnection.query.filter_by(user_id=current_user.id).first()
    if not conn:
        abort(400, message="Integração Amazon não configurada")

    try:
        summaries = get_inventory_summaries(conn, conn.marketplace_id)
    except Exception:
        abort(502, message="Falha ao buscar inventário da API Amazon")

    inserted, updated = upsert_inventory_snapshots(
        user_id=current_user.id,
        marketplace_id=conn.marketplace_id,
        summaries=summaries,
    )
    db.session.commit()
    return {"ok": True, "inserted": inserted, "updated": updated, "total": len(summaries)}
