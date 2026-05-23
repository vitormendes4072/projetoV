# app/integrations/amazon/service/__init__.py
"""
Re-exporta toda a API pública do package service/ para preservar
compatibilidade com todos os importadores existentes:

    from app.integrations.amazon.service import sync_orders_and_items
    from app.integrations.amazon.service import _credentials, _with_retry
    ...

Nenhum arquivo externo precisa ser alterado.
"""
from .client import (
    DEFAULT_SLEEP,
    _RETRYABLE_NETWORK,
    _credentials,
    _safe_payload,
    _with_retry,
    make_finances_client,
    make_orders_client,
    marketplace_from_id,
)
from .finances import (
    _compute_fingerprint,
    list_financial_events,
    sync_financial_events,
)
from .inventory import (
    get_inventory_summaries,
    make_inventory_client,
    upsert_inventory_snapshots,
)
from .orders import (
    list_order_items,
    list_orders,
    sync_orders_and_items,
)

__all__ = [
    # client
    "DEFAULT_SLEEP",
    "_RETRYABLE_NETWORK",
    "_credentials",
    "_safe_payload",
    "_with_retry",
    "make_finances_client",
    "make_orders_client",
    "marketplace_from_id",
    # finances
    "_compute_fingerprint",
    "list_financial_events",
    "sync_financial_events",
    # inventory
    "get_inventory_summaries",
    "make_inventory_client",
    "upsert_inventory_snapshots",
    # orders
    "list_order_items",
    "list_orders",
    "sync_orders_and_items",
]
