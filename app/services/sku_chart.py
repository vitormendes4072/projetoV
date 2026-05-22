"""
Dados para o scatter plot de margem × volume por SKU.

Duas fontes:
  get_sku_scatter_real()     — ShipmentEventList da Amazon (margem real)
  get_sku_scatter_estimado() — PricingHistory com product_id (margem estimada)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app import db
from app.models.pricing import PricingHistory
from app.models.product import Product

_PERIOD_DAYS: dict[str, int] = {"30d": 30, "90d": 90}
_MAX_SKUS = 80


def _r2(x: Any) -> float:
    try:
        return round(float(x), 2)
    except Exception:
        return 0.0


def _user_tax_rate(user_id: int) -> float:
    """Retorna a taxa de imposto padrão do usuário (%)."""
    try:
        from app.models.user import User
        u = db.session.get(User, user_id)
        return float(getattr(u, "default_tax_rate", 0) or 0)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Real — dados da Amazon (ShipmentEventList)
# ---------------------------------------------------------------------------

def get_sku_scatter_real(user_id: int, period: str = "all") -> list[dict]:
    """
    Agrega ShipmentEventList por SKU e retorna pontos para o scatter real.

    Retorna [] se não houver dados ou em ambiente SQLite (sem schema public).
    """
    try:
        from app.models.amazon_finances import AmazonFinancialEvent
        from app.models.amazon_sku_link import AmazonSkuLink
        from app.services.profit_calc import extract_net_from_shipment_events

        query = db.select(AmazonFinancialEvent).where(
            AmazonFinancialEvent.user_id == user_id,
            AmazonFinancialEvent.event_type == "ShipmentEventList",
        )
        if period in _PERIOD_DAYS:
            cutoff = datetime.now(timezone.utc) - timedelta(days=_PERIOD_DAYS[period])
            query = query.where(AmazonFinancialEvent.posted_date >= cutoff)

        rows = db.session.scalars(query).all()
        shipment_events = [r.raw_json for r in rows if r.raw_json]
        if not shipment_events:
            return []

        info = extract_net_from_shipment_events(shipment_events)
        skus = list(info["by_sku"].keys())

        # Nomes via AmazonSkuLink
        sku_names: dict[str, str] = {}
        links = db.session.scalars(
            db.select(AmazonSkuLink).where(
                AmazonSkuLink.user_id == user_id,
                AmazonSkuLink.amazon_seller_sku.in_(skus),
            )
        ).all()
        for lk in links:
            if lk.product:
                sku_names[lk.amazon_seller_sku] = lk.product.name

        # Fallback: Product.sku direto
        for p in db.session.scalars(
            db.select(Product).where(
                Product.user_id == user_id,
                Product.sku.in_(skus),
            )
        ).all():
            sku_names.setdefault(p.sku, p.name)

        # Custos por SKU (para margem real)
        product_costs: dict[str, tuple[float, float]] = {}
        for p in db.session.scalars(
            db.select(Product).where(
                Product.user_id == user_id,
                Product.sku.in_(skus),
            )
        ).all():
            product_costs[p.sku] = (float(p.cost or 0), float(p.packaging_cost or 0))

    except Exception:
        return []

    user_tax = _user_tax_rate(user_id)

    points: list[dict] = []
    for sku, v in info["by_sku"].items():
        revenue = float(v["revenue"])
        fees = float(v["fees"])
        units = float(v["qty"])
        if units <= 0 or revenue <= 0:
            continue

        net = revenue + fees
        imposto = revenue * (user_tax / 100.0)
        cost, pack = product_costs.get(sku, (0.0, 0.0))
        lucro = net - imposto - (cost * units) - (pack * units)
        margin_pct = _r2(lucro / revenue * 100.0)

        points.append({
            "sku": sku,
            "product_name": sku_names.get(sku, sku),
            "units_sold": _r2(units),
            "revenue_total": _r2(revenue),
            "lucro_total": _r2(lucro),
            "margin_pct": margin_pct,
            "avg_lucro_per_unit": _r2(lucro / units),
        })

    points.sort(key=lambda p: p["revenue_total"], reverse=True)
    return points[:_MAX_SKUS]


# ---------------------------------------------------------------------------
# Estimado — PricingHistory vinculada a produtos
# ---------------------------------------------------------------------------

def get_sku_scatter_estimado(user_id: int) -> list[dict]:
    """
    Agrega PricingHistory com product_id por produto.

    X = número de simulações salvas (proxy de atenção/volume)
    Y = margem estimada média
    Funciona sem Amazon (puro SQLite-friendly).
    """
    rows = db.session.scalars(
        db.select(PricingHistory)
        .where(
            PricingHistory.user_id == user_id,
            PricingHistory.product_id.is_not(None),
        )
        .order_by(PricingHistory.created_at.desc())
    ).all()

    if not rows:
        return []

    agg: dict[int, dict] = {}
    for r in rows:
        pid = r.product_id
        if pid not in agg:
            agg[pid] = {"product_id": pid, "margins": [], "net_profits": []}
        agg[pid]["margins"].append(float(r.margin))
        agg[pid]["net_profits"].append(float(r.net_profit))

    pids = list(agg.keys())
    prod_map: dict[int, Product] = {}
    try:
        prod_map = {
            p.id: p
            for p in db.session.scalars(
                db.select(Product).where(Product.id.in_(pids))
            ).all()
        }
    except Exception:
        pass

    points: list[dict] = []
    for pid, data in agg.items():
        prod = prod_map.get(pid)
        sim_count = len(data["margins"])
        avg_margin = _r2(sum(data["margins"]) / sim_count)
        avg_net = _r2(sum(data["net_profits"]) / sim_count)
        points.append({
            "sku": prod.sku if prod else f"produto-{pid}",
            "product_name": prod.name if prod else f"Produto #{pid}",
            "sim_count": sim_count,
            "avg_margin_pct": avg_margin,
            "avg_net_profit": avg_net,
        })

    points.sort(key=lambda p: p["avg_margin_pct"], reverse=True)
    return points
