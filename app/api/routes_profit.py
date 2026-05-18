from flask_login import current_user
from flask_smorest import abort

from app.api import blp
from app.api.schemas import ProfitResultSchema
from app.models import AmazonConnection
from app.integrations.amazon.profit_service import compute_order_profit, compute_order_item_breakdown


@blp.get("/amazon/profit/<amazon_order_id>")
@blp.response(200, ProfitResultSchema, description="Resultado do cálculo de lucratividade")
def api_profit_order(amazon_order_id: str):
    """Calcula o lucro líquido de um pedido Amazon.

    Utiliza os eventos financeiros (ShipmentEventList) já sincronizados.
    Se não houver dados financeiros, retorna `mode: no_finance_events` com sugestão
    de executar `POST /amazon/sync/finances` antes.
    """
    conn = AmazonConnection.query.filter_by(user_id=current_user.id).first()
    if not conn:
        abort(400, message="Integração Amazon não configurada")

    default_tax_rate = float(getattr(current_user, "default_tax_rate", 4.0) or 0.0)
    result = compute_order_profit(current_user.id, amazon_order_id, default_tax_rate)

    if result is None:
        return {
            "ok": True,
            "amazon_order_id": amazon_order_id,
            "mode": "no_finance_events",
            "message": "Nenhum ShipmentEventList encontrado. Execute POST /amazon/sync/finances primeiro.",
        }

    return result


@blp.get("/amazon/orders/<amazon_order_id>/items")
@blp.response(200, ProfitResultSchema, description="Breakdown de lucratividade por item")
def api_order_items_profit(amazon_order_id: str):
    """Retorna o breakdown de lucratividade por item de um pedido Amazon."""
    default_tax_rate = float(getattr(current_user, "default_tax_rate", 0.0) or 0.0)
    result = compute_order_item_breakdown(current_user.id, amazon_order_id, default_tax_rate)
    return result
