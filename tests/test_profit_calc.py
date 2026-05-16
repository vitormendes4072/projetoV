from decimal import Decimal
from app.services.profit_calc import extract_net_from_shipment_events


def _event(sku, charge, fee, qty=1):
    return {
        "ShipmentItemList": [{
            "SellerSKU": sku,
            "QuantityShipped": str(qty),
            "ItemChargeList": [{"ChargeAmount": {"CurrencyAmount": str(charge)}}],
            "ItemFeeList": [{"FeeAmount": {"CurrencyAmount": str(fee)}}],
        }]
    }


def test_extract_net_vazio():
    result = extract_net_from_shipment_events([])
    assert result["revenue"] == Decimal("0")
    assert result["fees"] == Decimal("0")
    assert result["net"] == Decimal("0")
    assert result["by_sku"] == {}


def test_extract_net_charges_e_fees():
    result = extract_net_from_shipment_events([_event("SKU-A", charge="100", fee="-30")])
    assert result["revenue"] == Decimal("100")
    assert result["fees"] == Decimal("-30")
    assert result["net"] == Decimal("70")


def test_extract_net_por_sku():
    events = [
        _event("SKU-A", charge="100", fee="-20"),
        _event("SKU-B", charge="50", fee="-10"),
    ]
    result = extract_net_from_shipment_events(events)
    assert result["by_sku"]["SKU-A"]["net"] == Decimal("80")
    assert result["by_sku"]["SKU-B"]["net"] == Decimal("40")
    assert result["net"] == Decimal("120")


def test_extract_net_qty():
    result = extract_net_from_shipment_events([_event("SKU-A", charge="100", fee="-10", qty=3)])
    assert result["by_sku"]["SKU-A"]["qty"] == Decimal("3")
