from __future__ import annotations

from decimal import Decimal
from typing import Any


def _d(x: Any) -> Decimal:
    try:
        return Decimal(str(x))
    except Exception:
        return Decimal("0")

def extract_net_from_shipment_events(shipment_events: list[dict]) -> dict:
    """
    Lê ShipmentEventList (mock ou SP-API) e retorna:
      revenue: soma de charges (positivo)
      fees: soma de fees (normalmente negativo)
      net: revenue + fees
      by_sku: sku -> {revenue, fees, net, qty}
    """
    revenue = Decimal("0")
    fees = Decimal("0")
    by_sku = {}

    for ev in shipment_events:
        for it in (ev.get("ShipmentItemList") or []):
            sku = it.get("SellerSKU") or "UNKNOWN"
            qty = _d(it.get("QuantityShipped") or it.get("Quantity") or 0)

            sku_rev = Decimal("0")
            sku_fee = Decimal("0")

            # Charges
            for ch in (it.get("ItemChargeList") or []):
                amt = (ch.get("ChargeAmount") or {}).get("CurrencyAmount")
                sku_rev += _d(amt)

            # Fees
            for f in (it.get("ItemFeeList") or []):
                amt = (f.get("FeeAmount") or {}).get("CurrencyAmount")
                sku_fee += _d(amt)

            revenue += sku_rev
            fees += sku_fee

            if sku not in by_sku:
                by_sku[sku] = {
                    "revenue": Decimal("0"),
                    "fees": Decimal("0"),
                    "net": Decimal("0"),
                    "qty": Decimal("0"),
                }

            by_sku[sku]["revenue"] += sku_rev
            by_sku[sku]["fees"] += sku_fee
            by_sku[sku]["qty"] += qty

    for sku, v in by_sku.items():
        v["net"] = v["revenue"] + v["fees"]

    return {
        "revenue": revenue,
        "fees": fees,
        "net": revenue + fees,
        "by_sku": by_sku,
    }
