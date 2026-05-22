"""
Comparativo de margem Estimada (simulação do calculator) x Real (vendas Amazon).

Cruza a última PricingHistory vinculada a um produto com os eventos
financeiros (ShipmentEventList) da Amazon para os SKUs desse produto.
"""
from __future__ import annotations

from typing import Any

from app import db
from app.models.pricing import PricingHistory
from app.models.product import Product


def _r2(x: Any) -> float:
    try:
        return round(float(x), 2)
    except Exception:
        return 0.0


def _latest_estimate(user_id: int, product_id: int) -> dict | None:
    """Última simulação salva (PricingHistory) vinculada ao produto."""
    sim = db.session.scalar(
        db.select(PricingHistory)
        .where(
            PricingHistory.user_id == user_id,
            PricingHistory.product_id == product_id,
        )
        .order_by(PricingHistory.created_at.desc())
        .limit(1)
    )
    if sim is None:
        return None
    return {
        "title": sim.title,
        "price": _r2(sim.price),
        "cost": _r2(sim.cost),
        "net_profit": _r2(sim.net_profit),
        "margin_pct": _r2(sim.margin),
        "roi_pct": _r2(sim.roi),
        "created_at": sim.created_at,
    }


def _real_target_skus(user_id: int, product: Product) -> set[str]:
    """SKUs Amazon associados ao produto (links + sku próprio do produto)."""
    skus: set[str] = set()
    if product.sku:
        skus.add(product.sku)
    try:
        from app.models.amazon_sku_link import AmazonSkuLink
        links = db.session.scalars(
            db.select(AmazonSkuLink.amazon_seller_sku).where(
                AmazonSkuLink.user_id == user_id,
                AmazonSkuLink.product_id == product.id,
            )
        ).all()
        skus.update(s for s in links if s)
    except Exception:
        # Tabela com schema="public" — ausente no SQLite de testes.
        pass
    return skus


def aggregate_real_margin(
    shipment_events: list[dict],
    target_skus: set[str],
    unit_cost: float,
    unit_pack: float,
    tax_rate_pct: float,
) -> dict | None:
    """
    Função pura: agrega ShipmentEventList para os SKUs do produto e calcula
    a margem real. Retorna None se não houver unidades vendidas para os SKUs.
    """
    from app.services.profit_calc import extract_net_from_shipment_events

    info = extract_net_from_shipment_events(shipment_events)

    revenue = fees = units = 0.0
    for sku, v in info["by_sku"].items():
        if sku in target_skus:
            revenue += float(v["revenue"])
            fees += float(v["fees"])
            units += float(v["qty"])

    if units <= 0:
        return None

    net = revenue + fees
    imposto = revenue * (tax_rate_pct / 100.0)
    cmv = unit_cost * units
    embalagem = unit_pack * units
    lucro = net - imposto - cmv - embalagem
    margin_pct = (lucro / revenue * 100.0) if revenue > 0 else 0.0

    return {
        "revenue_total": _r2(revenue),
        "fees_total": _r2(fees),
        "net_total": _r2(net),
        "imposto_total": _r2(imposto),
        "cmv_total": _r2(cmv),
        "embalagem_total": _r2(embalagem),
        "lucro_total": _r2(lucro),
        "units_sold": _r2(units),
        "avg_net_per_unit": _r2(lucro / units),
        "avg_revenue_per_unit": _r2(revenue / units),
        "margin_pct": _r2(margin_pct),
    }


def _real_from_finance_events(
    user_id: int, product: Product, tax_rate_pct: float
) -> dict | None:
    """Lê AmazonFinancialEvent e agrega a margem real. None se não houver dados."""
    try:
        from app.models.amazon_finances import AmazonFinancialEvent
        rows = db.session.scalars(
            db.select(AmazonFinancialEvent).where(
                AmazonFinancialEvent.user_id == user_id,
                AmazonFinancialEvent.event_type == "ShipmentEventList",
            )
        ).all()
    except Exception:
        # Tabela com schema="public" — ausente no SQLite de testes.
        return None

    shipment_events = [r.raw_json for r in rows if r.raw_json]
    if not shipment_events:
        return None

    target_skus = _real_target_skus(user_id, product)
    return aggregate_real_margin(
        shipment_events,
        target_skus,
        float(product.cost or 0),
        float(product.packaging_cost or 0),
        tax_rate_pct,
    )


def get_sku_comparison(
    user_id: int, product: Product, tax_rate_pct: float = 0.0
) -> dict[str, Any]:
    """
    Monta o comparativo margem estimada x real de um produto.

    Retorna dict com:
      product        — o objeto Product
      estimado       — dados da última simulação vinculada, ou None
      real           — agregado de vendas Amazon, ou None
      delta_margin   — real.margin_pct - estimado.margin_pct (pp), ou None
      delta_net_unit — real.avg_net_per_unit - estimado.net_profit, ou None
      has_amazon_data — bool
    """
    estimado = _latest_estimate(user_id, product.id)
    real = _real_from_finance_events(user_id, product, tax_rate_pct)

    delta_margin = None
    delta_net_unit = None
    if estimado and real:
        delta_margin = _r2(real["margin_pct"] - estimado["margin_pct"])
        delta_net_unit = _r2(real["avg_net_per_unit"] - estimado["net_profit"])

    return {
        "product": product,
        "estimado": estimado,
        "real": real,
        "delta_margin": delta_margin,
        "delta_net_unit": delta_net_unit,
        "has_amazon_data": real is not None,
    }
