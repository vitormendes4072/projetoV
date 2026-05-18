from flask import jsonify
from flask_login import current_user
from flask_smorest import Blueprint

blp = Blueprint(
    "api_v1",
    __name__,
    url_prefix="/api/v1",
    description="VEntregaz REST API — Amazon FBA Marketplace Manager",
)


@blp.before_request
def _require_login():
    if not current_user.is_authenticated:
        return jsonify({"ok": False, "error": "Autenticação necessária"}), 401


from app.api import routes_sync, routes_inventory, routes_profit, routes_alertas  # noqa: F401, E402
