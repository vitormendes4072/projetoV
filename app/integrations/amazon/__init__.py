from flask import Blueprint

amazon = Blueprint("amazon", __name__, url_prefix="/integrations/amazon")

from . import (  # noqa: E402, F401
    routes_connection,
    routes_sync,
    routes_orders,
    routes_sku_links,
    routes_inventory,
    routes_dev,
)
