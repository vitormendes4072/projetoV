"""
app/services/vendas.py
─────────────────────
Aggregated sales analytics from Amazon order/item data.

All queries are guarded by a PostgreSQL dialect check because
AmazonOrder and AmazonOrderItem use schema="public", which does not
exist in the SQLite database used in tests.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app import db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PERIOD_DAYS: dict[str, int] = {"7d": 7, "30d": 30, "90d": 90}


def _period_start(period: str) -> datetime | None:
    """Return UTC datetime for the start of the requested period, or None for 'all'."""
    if period in _PERIOD_DAYS:
        return datetime.now(timezone.utc) - timedelta(days=_PERIOD_DAYS[period])
    return None


def _empty_kpis() -> dict[str, Any]:
    return {
        "total_orders": 0,
        "receita_bruta": 0.0,
        "ticket_medio": 0.0,
        "top_skus": [],
        "has_amazon_data": False,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_vendas_kpis(user_id: int, period: str) -> dict[str, Any]:
    """Return sales KPIs and top-SKU breakdown for *user_id* in *period*.

    Uses two aggregate queries against AmazonOrder + AmazonOrderItem.
    Returns an empty dict when the database dialect is not PostgreSQL
    (e.g. SQLite in tests) so callers never need to handle exceptions.
    """
    if db.engine.dialect.name != "postgresql":
        return _empty_kpis()

    from app.models.amazon import AmazonOrder, AmazonOrderItem  # noqa: PLC0415

    date_from = _period_start(period)

    # Q1 — aggregate totals from AmazonOrder (non-cancelled orders in period)
    order_cond: list[Any] = [
        AmazonOrder.user_id == user_id,
        AmazonOrder.order_status != "Canceled",
    ]
    if date_from:
        order_cond.append(AmazonOrder.purchase_date >= date_from)

    agg = db.session.execute(
        db.select(
            db.func.count(AmazonOrder.id).label("total"),
            db.func.coalesce(
                db.func.sum(AmazonOrder.order_total_amount), 0
            ).label("receita"),
        ).where(*order_cond)
    ).one()

    total_orders = int(agg.total)
    receita_bruta = float(agg.receita)

    # Q2 — top SKUs from AmazonOrderItem, filtered to the same order set
    order_ids_sub = (
        db.select(AmazonOrder.amazon_order_id)
        .where(*order_cond)
        .scalar_subquery()
    )

    top_rows = db.session.execute(
        db.select(
            AmazonOrderItem.seller_sku,
            db.func.count(
                db.func.distinct(AmazonOrderItem.amazon_order_id)
            ).label("orders"),
            db.func.coalesce(
                db.func.sum(AmazonOrderItem.quantity), 0
            ).label("qty"),
            db.func.coalesce(
                db.func.sum(AmazonOrderItem.item_price), 0
            ).label("revenue"),
        )
        .where(
            AmazonOrderItem.user_id == user_id,
            AmazonOrderItem.amazon_order_id.in_(order_ids_sub),
        )
        .group_by(AmazonOrderItem.seller_sku)
        .order_by(
            db.func.coalesce(db.func.sum(AmazonOrderItem.item_price), 0).desc()
        )
        .limit(10)
    ).all()

    # Use actual item revenue sum as denominator; fall back to order total when
    # no item-level price data is available (items not yet synced).
    item_revenue_total = sum(float(r.revenue) for r in top_rows)
    denominator = item_revenue_total if item_revenue_total > 0 else (receita_bruta or 1.0)

    top_skus = [
        {
            "sku": r.seller_sku or "UNKNOWN",
            "orders": int(r.orders),
            "qty": int(r.qty or 0),
            "revenue": float(r.revenue),
            "pct": round(float(r.revenue) / denominator * 100, 1),
        }
        for r in top_rows
    ]

    return {
        "total_orders": total_orders,
        "receita_bruta": receita_bruta,
        "ticket_medio": round(receita_bruta / total_orders, 2) if total_orders > 0 else 0.0,
        "top_skus": top_skus,
        "has_amazon_data": total_orders > 0,
    }
