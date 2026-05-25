"""
app/services/estoque.py
───────────────────────
Inventory health analytics with two data paths:

  FBA path   — reads AmazonInventorySnapshot (schema="public", PostgreSQL only).
               Falls through when no FBA snapshots exist.
  Internal   — reads Product.stock_quantity / min_stock (SQLite-safe, always works).

Public API
----------
  get_estoque_data(user_id)  → dict   (used by the route)
  _classify_status(qty, min_stock)    (exported for unit tests)
  _reorder_qty(qty, min_stock)        (exported for unit tests)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app import db


# ---------------------------------------------------------------------------
# Pure helpers — exported so tests can unit-test them directly
# ---------------------------------------------------------------------------

def _classify_status(qty: int, min_stock: int | None) -> str:
    """Return 'critical', 'alert', or 'ok' for a given stock level.

    Rules:
      qty == 0              → critical  (completely out of stock)
      qty <= min_stock      → alert     (below safety threshold)
      else                  → ok
    min_stock=None means no threshold is configured; only qty==0 triggers critical.
    """
    if qty == 0:
        return "critical"
    if min_stock is not None and qty <= min_stock:
        return "alert"
    return "ok"


def _reorder_qty(qty: int, min_stock: int | None) -> int:
    """Suggested replenishment quantity: top up to 2× the minimum threshold.

    Returns 0 when no replenishment is needed or no threshold is configured.
    """
    if min_stock is None or qty > min_stock:
        return 0
    return max(0, min_stock * 2 - qty)


# ---------------------------------------------------------------------------
# Internal data path — uses Product model (SQLite-safe)
# ---------------------------------------------------------------------------

def _get_internal_data(user_id: int) -> dict[str, Any]:
    from app.models.product import Product  # noqa: PLC0415

    products = db.session.scalars(
        db.select(Product)
        .where(Product.user_id == user_id)
        .order_by(Product.stock_quantity.asc(), Product.name.asc())
    ).all()

    if not products:
        return _empty_result()

    all_items: list[dict] = []
    last_updated: datetime | None = None

    for p in products:
        qty = int(p.stock_quantity or 0)
        min_s = int(p.min_stock) if p.min_stock is not None else None
        status = _classify_status(qty, min_s)
        sugerida = _reorder_qty(qty, min_s)

        if p.updated_at and (last_updated is None or p.updated_at > last_updated):
            last_updated = p.updated_at

        all_items.append(
            {
                "sku": p.sku,
                "product_name": p.name,
                "qty": qty,
                "min_stock": min_s,
                "reserved_qty": 0,
                "inbound_qty": 0,
                "status": status,
                "qty_sugerida": sugerida,
            }
        )

    reposicao = [i for i in all_items if i["status"] != "ok"]
    criticos = [i for i in all_items if i["status"] == "critical"]

    return {
        "total_skus": len(all_items),
        "total_alertas": len(reposicao),
        "total_criticos": len(criticos),
        "total_inbound": 0,
        "reposicao_items": reposicao,
        "has_any_data": True,
        "has_fba_data": False,
        "data_source": "internal",
        "last_updated": last_updated,
    }


# ---------------------------------------------------------------------------
# FBA data path — uses AmazonInventorySnapshot (PostgreSQL only)
# ---------------------------------------------------------------------------

def _get_fba_data(user_id: int) -> dict[str, Any]:
    from app.models.amazon_inventory import AmazonInventorySnapshot  # noqa: PLC0415
    from app.models.amazon_sku_link import AmazonSkuLink              # noqa: PLC0415
    from app.models.product import Product                             # noqa: PLC0415

    inbound_sum = (
        AmazonInventorySnapshot.inbound_working_qty
        + AmazonInventorySnapshot.inbound_shipped_qty
        + AmazonInventorySnapshot.inbound_receiving_qty
    )

    rows = db.session.execute(
        db.select(
            AmazonInventorySnapshot.seller_sku,
            AmazonInventorySnapshot.asin,
            AmazonInventorySnapshot.fulfillable_qty,
            AmazonInventorySnapshot.reserved_qty,
            inbound_sum.label("inbound_qty"),
            AmazonInventorySnapshot.updated_at,
            Product.min_stock,
            Product.name.label("product_name"),
        )
        .select_from(AmazonInventorySnapshot)
        .outerjoin(
            AmazonSkuLink,
            db.and_(
                AmazonSkuLink.user_id == AmazonInventorySnapshot.user_id,
                AmazonSkuLink.amazon_seller_sku == AmazonInventorySnapshot.seller_sku,
            ),
        )
        .outerjoin(Product, Product.id == AmazonSkuLink.product_id)
        .where(AmazonInventorySnapshot.user_id == user_id)
        .order_by(
            AmazonInventorySnapshot.fulfillable_qty.asc(),
            AmazonInventorySnapshot.seller_sku.asc(),
        )
    ).all()

    if not rows:
        return _empty_result()

    all_items: list[dict] = []
    last_updated: datetime | None = None
    total_inbound = 0

    for r in rows:
        qty = int(r.fulfillable_qty or 0)
        min_s = int(r.min_stock) if r.min_stock is not None else None
        inbound = int(r.inbound_qty or 0)
        status = _classify_status(qty, min_s)
        sugerida = _reorder_qty(qty, min_s)
        total_inbound += inbound

        if r.updated_at and (last_updated is None or r.updated_at > last_updated):
            last_updated = r.updated_at

        all_items.append(
            {
                "sku": r.seller_sku,
                "product_name": r.product_name,
                "qty": qty,
                "min_stock": min_s,
                "reserved_qty": int(r.reserved_qty or 0),
                "inbound_qty": inbound,
                "status": status,
                "qty_sugerida": sugerida,
            }
        )

    reposicao = [i for i in all_items if i["status"] != "ok"]
    criticos = [i for i in all_items if i["status"] == "critical"]

    return {
        "total_skus": len(all_items),
        "total_alertas": len(reposicao),
        "total_criticos": len(criticos),
        "total_inbound": total_inbound,
        "reposicao_items": reposicao,
        "has_any_data": True,
        "has_fba_data": True,
        "data_source": "fba",
        "last_updated": last_updated,
    }


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _empty_result() -> dict[str, Any]:
    return {
        "total_skus": 0,
        "total_alertas": 0,
        "total_criticos": 0,
        "total_inbound": 0,
        "reposicao_items": [],
        "has_any_data": False,
        "has_fba_data": False,
        "data_source": "none",
        "last_updated": None,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def get_estoque_data(user_id: int) -> dict[str, Any]:
    """Return inventory health data for *user_id*.

    Tries the FBA path first (PostgreSQL only). Falls through to the internal
    Product-based path when no FBA snapshots exist or the dialect is SQLite.
    """
    if db.engine.dialect.name == "postgresql":
        fba = _get_fba_data(user_id)
        if fba["has_any_data"]:
            return fba
    return _get_internal_data(user_id)
