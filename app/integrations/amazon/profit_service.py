"""
Cálculos de lucro/margem por pedido Amazon, baseados em finance events.
"""
from app import db
from app.models import AmazonOrder, AmazonOrderItem
from app.models.amazon_finances import AmazonFinancialEvent
from app.models.amazon_sku_link import AmazonSkuLink
from app.models.product import Product


def _r2(x) -> float:
    try:
        return round(float(x), 2)
    except Exception:
        return 0.0


def _amount_from_money(m) -> float:
    try:
        if isinstance(m, dict):
            return float(m.get("Amount") or m.get("CurrencyAmount") or 0)
    except Exception:
        pass
    return 0.0


def _resolve_product(user_id: int, sku: str):
    """Resolve Product por SKU link ou SKU direto."""
    link = db.session.scalar(db.select(AmazonSkuLink).filter_by(user_id=user_id, amazon_seller_sku=sku))
    if link and link.product:
        return link.product
    return db.session.scalar(db.select(Product).filter_by(user_id=user_id, sku=sku))


def compute_order_profit(user_id: int, amazon_order_id: str, default_tax_rate: float):
    """
    Calcula lucro líquido de um pedido a partir dos ShipmentEventList.
    Retorna dict pronto para jsonify, ou None se não houver finance events.
    """
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

    cmv_total = 0.0
    embalagem_total = 0.0
    by_sku = {}

    for sku, v in net_info["by_sku"].items():
        sku_revenue = _r2(v["revenue"])
        sku_fees = _r2(v["fees"])
        sku_net = _r2(v["net"])
        sku_qty = float(v.get("qty", 0))

        prod = _resolve_product(user_id, sku)
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

    return {
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


def compute_order_item_breakdown(user_id: int, amazon_order_id: str, default_tax_rate: float):
    """
    Detalha lucro por item de um pedido.
    Retorna dict pronto para jsonify.
    """
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

        prod = _resolve_product(user_id, sku)
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

    return {
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
