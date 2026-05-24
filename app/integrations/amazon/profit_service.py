"""
Cálculos de lucro/margem por pedido Amazon, baseados em finance events.
"""
from __future__ import annotations

from datetime import timedelta, timezone
from typing import Any

from sqlalchemy.orm import joinedload

from app import db, cache
from app.models import AmazonOrder, AmazonOrderItem
from app.models.amazon_finances import AmazonFinancialEvent
from app.models.amazon_sku_link import AmazonSkuLink
from app.models.product import Product
from app.integrations.amazon.utils import utcnow, iso_z
from app.integrations.amazon.service import sync_financial_events

# ---------------------------------------------------------------------------
# Cache helpers — generation-counter strategy
#
# Each user has a "cache version" (ucv) stored in the cache backend.
# All per-order keys embed this version, so bumping it in one call
# effectively invalidates every cached result for that user — without
# requiring pattern-delete support (works with SimpleCache and RedisCache).
#
# NullCache (used in tests) makes cache.get() always return None and
# cache.set() a no-op, so the helpers below are fully transparent in tests.
# ---------------------------------------------------------------------------

_PROFIT_TIMEOUT = 300  # seconds — 5 minutes
_GEN_TIMEOUT = 86_400  # seconds — 1 day (generation key TTL)


def _cache_version(user_id: int) -> int:
    """Return the current generation counter for user_id (0 if unset)."""
    return cache.get(f"ucv:{user_id}") or 0


def _profit_key(user_id: int, order_id: str, tax_rate: float) -> str:
    v = _cache_version(user_id)
    return f"profit:v{v}:{user_id}:{order_id}:{round(tax_rate, 4)}"


def _breakdown_key(user_id: int, order_id: str, tax_rate: float) -> str:
    v = _cache_version(user_id)
    return f"brkdown:v{v}:{user_id}:{order_id}:{round(tax_rate, 4)}"


def invalidate_order_profit_cache(user_id: int, order_id: str, tax_rate: float) -> None:
    """Invalidate cached results for a single order (called after per-order refresh)."""
    cache.delete(_profit_key(user_id, order_id, tax_rate))
    cache.delete(_breakdown_key(user_id, order_id, tax_rate))


def invalidate_user_profit_cache(user_id: int) -> None:
    """Invalidate all cached profit results for a user (called after full sync)."""
    v = _cache_version(user_id)
    cache.set(f"ucv:{user_id}", v + 1, timeout=_GEN_TIMEOUT)


def _r2(x: Any) -> float:
    try:
        return round(float(x), 2)
    except Exception:
        return 0.0


def _amount_from_money(m: Any) -> float:
    try:
        if isinstance(m, dict):
            return float(m.get("Amount") or m.get("CurrencyAmount") or 0)
    except Exception:
        pass
    return 0.0


def _resolve_products_bulk(user_id: int, skus: list[str]) -> dict[str, Any]:
    """Resolve Product para múltiplos SKUs em 2 queries fixas (sem N+1).

    Query 1: sku_links JOIN products (joinedload).
    Query 2: products por sku direto, apenas para skus sem link.
    """
    if not skus:
        return {}

    links = db.session.scalars(
        db.select(AmazonSkuLink)
        .options(joinedload(AmazonSkuLink.product))
        .filter(
            AmazonSkuLink.user_id == user_id,
            AmazonSkuLink.amazon_seller_sku.in_(skus),
        )
    ).all()

    result = {}
    linked_skus = set()
    for link in links:
        if link.product:
            result[link.amazon_seller_sku] = link.product
            linked_skus.add(link.amazon_seller_sku)

    unlinked = [s for s in skus if s not in linked_skus]
    if unlinked:
        prods = db.session.scalars(
            db.select(Product).filter(
                Product.user_id == user_id,
                Product.sku.in_(unlinked),
            )
        ).all()
        for p in prods:
            result[p.sku] = p

    return result


def _compute_order_start(user_id: int, amazon_order_id: str) -> tuple:
    """
    Calcula a janela de início para busca de finance events de um pedido.

    Regra:
    - Padrão: 7 dias atrás.
    - Se o pedido existe e tem purchase_date: purchase_date - 5 dias
      (garante captura de eventos que chegam ligeiramente antes da data oficial).

    Retorna (start_dt, start_iso) onde start_iso é string ISO-8601 com 'Z'.
    Não faz commit — apenas leitura.
    """
    start = utcnow() - timedelta(days=7)
    order = db.session.scalar(
        db.select(AmazonOrder).filter_by(user_id=user_id, amazon_order_id=amazon_order_id)
    )
    if order and order.purchase_date:
        purchase_utc = order.purchase_date.astimezone(timezone.utc)
        start = purchase_utc - timedelta(days=5)
    return start, iso_z(start)


def refresh_order_finances(conn: Any, user_id: int, amazon_order_id: str) -> tuple:
    """
    Faz sync curto de finance events para um pedido específico.

    Passos:
    1. Calcula a janela temporal ideal via _compute_order_start.
    2. Apaga AmazonFinancialEvent do user_id com posted_date >= start
       (limpa dados possivelmente desatualizados antes de re-sincronizar).
    3. Chama sync_financial_events para repopular a janela.

    Retorna (start_iso, events_inserted).
    Não faz db.session.commit() — responsabilidade do chamador.
    Lança exceção em caso de falha no SP-API — o chamador faz rollback.
    """
    start_dt, start_iso = _compute_order_start(user_id, amazon_order_id)

    db.session.execute(
        db.delete(AmazonFinancialEvent).where(
            AmazonFinancialEvent.user_id == user_id,
            AmazonFinancialEvent.posted_date >= start_dt,
        )
    )
    db.session.flush()

    events_inserted = sync_financial_events(
        conn, user_id=user_id, posted_after_iso=start_iso
    )
    return start_iso, events_inserted


def compute_order_profit(user_id: int, amazon_order_id: str, default_tax_rate: float) -> dict[str, Any] | None:
    """
    Calcula lucro líquido de um pedido a partir dos ShipmentEventList.
    Retorna dict pronto para jsonify, ou None se não houver finance events.
    Resultado é cacheado por _PROFIT_TIMEOUT segundos; None não é cacheado
    (ausência de eventos pode mudar após próximo sync).
    """
    _key = _profit_key(user_id, amazon_order_id, default_tax_rate)
    _cached = cache.get(_key)
    if _cached is not None:
        return _cached

    from app.services.profit_calc import extract_net_from_shipment_events

    fin_rows = db.session.scalars(
        db.select(AmazonFinancialEvent).filter_by(user_id=user_id, amazon_order_id=amazon_order_id)
    ).all()
    shipment_events = [r.raw_json for r in fin_rows if r.event_type == "ShipmentEventList"]

    if not shipment_events:
        return None

    net_info = extract_net_from_shipment_events(shipment_events)

    imposto_rate = (default_tax_rate or 0.0) / 100.0

    amazon_revenue = _r2(net_info["revenue"])
    amazon_fees = _r2(net_info["fees"])
    amazon_net = _r2(net_info["net"])

    imposto = _r2(amazon_revenue * imposto_rate)

    total_revenue_for_split = sum(
        float(v.get("revenue", 0)) for v in net_info["by_sku"].values()
    )

    skus = list(net_info["by_sku"].keys())
    products = _resolve_products_bulk(user_id, skus)

    cmv_total = 0.0
    embalagem_total = 0.0
    by_sku = {}

    for sku, v in net_info["by_sku"].items():
        sku_revenue = _r2(v["revenue"])
        sku_fees = _r2(v["fees"])
        sku_net = _r2(v["net"])
        sku_qty = float(v.get("qty", 0))

        prod = products.get(sku)
        unit_cost = float(prod.cost) if prod else 0.0
        unit_pack = float(getattr(prod, "packaging_cost", 0.0)) if prod else 0.0

        sku_cmv = unit_cost * sku_qty
        sku_pack = unit_pack * sku_qty
        cmv_total += sku_cmv
        embalagem_total += sku_pack

        tax_alloc = (
            imposto * (sku_revenue / total_revenue_for_split)
            if total_revenue_for_split > 0 else 0.0
        )
        tax_alloc = _r2(tax_alloc)

        sku_net_after_tax = _r2(sku_net - tax_alloc)
        sku_profit_after_tax = _r2(sku_net_after_tax - sku_cmv - sku_pack)

        by_sku[sku] = {
            "qty": _r2(sku_qty),
            "revenue": sku_revenue,
            "fees": sku_fees,
            "net": sku_net,
            "tax_allocated": tax_alloc,
            "net_after_tax": sku_net_after_tax,
            "unit_cost": _r2(unit_cost),
            "cmv": _r2(sku_cmv),
            "unit_packaging_cost": _r2(unit_pack),
            "embalagem": _r2(sku_pack),
            "profit_after_tax": sku_profit_after_tax,
        }

    cmv_total = _r2(cmv_total)
    embalagem_total = _r2(embalagem_total)
    lucro = _r2(amazon_net - (cmv_total + embalagem_total + imposto))

    result = {
        "ok": True,
        "amazon_order_id": amazon_order_id,
        "mode": "real_from_finance_events",
        "amazon_revenue": amazon_revenue,
        "amazon_fees": amazon_fees,
        "amazon_net": amazon_net,
        "imposto_rate_pct": _r2(default_tax_rate or 0.0),
        "imposto": imposto,
        "tax_base": "amazon_revenue",
        "cmv_total": cmv_total,
        "embalagem_total": embalagem_total,
        "lucro": lucro,
        "by_sku": by_sku,
        "notes": {
            "tax_source": "User.default_tax_rate (%)",
            "tax_allocation": "Proporcional ao revenue por SKU",
            "cmv_source": "Product.cost by SKU",
            "embalagem_source": "Product.packaging_cost by SKU",
        },
    }
    cache.set(_key, result, timeout=_PROFIT_TIMEOUT)
    return result


def compute_order_item_breakdown(user_id: int, amazon_order_id: str, default_tax_rate: float) -> dict[str, Any]:
    """
    Detalha lucro por item de um pedido.
    Retorna dict pronto para jsonify.
    Resultado é cacheado por _PROFIT_TIMEOUT segundos.
    """
    _key = _breakdown_key(user_id, amazon_order_id, default_tax_rate)
    _cached = cache.get(_key)
    if _cached is not None:
        return _cached

    from app.services.profit_calc import extract_net_from_shipment_events

    order = db.session.scalar(db.select(AmazonOrder).filter_by(user_id=user_id, amazon_order_id=amazon_order_id))
    order_status = order.order_status if order else None
    order_total = float(order.order_total_amount or 0) if order else 0.0
    order_currency = order.currency if order else None

    items = db.session.scalars(
        db.select(AmazonOrderItem).filter_by(user_id=user_id, amazon_order_id=amazon_order_id)
    ).all()

    fin_rows = db.session.scalars(
        db.select(AmazonFinancialEvent).filter_by(user_id=user_id, amazon_order_id=amazon_order_id)
    ).all()
    shipment_events = [r.raw_json for r in fin_rows if r.event_type == "ShipmentEventList"]

    by_sku_fin = {}
    if shipment_events:
        net_info = extract_net_from_shipment_events(shipment_events)
        for sku, v in net_info["by_sku"].items():
            by_sku_fin[sku] = {
                "revenue": round(float(v["revenue"]), 2),
                "fees": round(float(v["fees"]), 2),
                "net": round(float(v["net"]), 2),
                "qty": float(v["qty"]),
            }

    imposto_rate_pct = float(default_tax_rate or 0.0)
    imposto_rate = imposto_rate_pct / 100.0

    skus = [it.seller_sku or "" for it in items]
    products = _resolve_products_bulk(user_id, skus)

    result_items = []
    for it in items:
        sku = it.seller_sku or ""
        qty = float(it.quantity or 0)

        price = float(it.item_price or 0)
        raw = it.raw_json or {}
        if price == 0 and isinstance(raw.get("ItemPrice"), dict):
            price = _amount_from_money(raw["ItemPrice"])
        if price == 0 and order_total > 0 and len(items) > 0:
            price = round(order_total / len(items), 2)

        prod = products.get(sku)
        unit_cost = float(prod.cost) if prod else 0.0
        unit_pack = float(getattr(prod, "packaging_cost", 0.0)) if prod else 0.0

        cmv = round(unit_cost * qty, 2)
        embalagem = round(unit_pack * qty, 2)

        fin = by_sku_fin.get(sku)
        if fin:
            revenue = fin["revenue"]
            fees = fin["fees"]
            net = fin["net"]
        else:
            revenue = round(price, 2)
            fees = 0.0
            net = round(revenue + fees, 2)

        imposto = round(revenue * imposto_rate, 2)
        lucro = round(net - imposto - cmv - embalagem, 2)
        margem = round((lucro / revenue) * 100, 2) if revenue > 0 else 0.0

        result_items.append({
            "sku": sku,
            "asin": it.asin,
            "qty": qty,
            "price": round(price, 2),
            "revenue": revenue,
            "fees": fees,
            "net": net,
            "imposto": imposto,
            "cmv": cmv,
            "embalagem": embalagem,
            "lucro": lucro,
            "margem_pct": margem,
        })

    result = {
        "ok": True,
        "amazon_order_id": amazon_order_id,
        "order_status": order_status,
        "order_total": round(order_total, 2),
        "order_currency": order_currency,
        "items_count": len(result_items),
        "imposto_rate_pct": round(imposto_rate_pct, 2),
        "items": result_items,
        "has_finance_events": bool(shipment_events),
        "has_items": bool(items),
    }
    cache.set(_key, result, timeout=_PROFIT_TIMEOUT)
    return result
