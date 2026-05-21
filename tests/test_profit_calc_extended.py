"""
Edge cases para app/services/profit_calc.py.
Funções puras — sem fixtures de DB ou contexto Flask.
"""
from decimal import Decimal

import pytest

from app.services.profit_calc import extract_net_from_shipment_events


def _item(sku, charge, fee, qty=1, sku_key="SellerSKU", qty_key="QuantityShipped"):
    return {
        sku_key: sku,
        qty_key: str(qty),
        "ItemChargeList": [{"ChargeAmount": {"CurrencyAmount": str(charge)}}],
        "ItemFeeList": [{"FeeAmount": {"CurrencyAmount": str(fee)}}],
    }


def _event(*items):
    return {"ShipmentItemList": list(items)}


# ---------------------------------------------------------------------------
# Empty / missing input
# ---------------------------------------------------------------------------

def test_empty_event_list():
    result = extract_net_from_shipment_events([])
    assert result["revenue"] == Decimal("0")
    assert result["fees"] == Decimal("0")
    assert result["net"] == Decimal("0")
    assert result["by_sku"] == {}


def test_event_with_empty_shipment_item_list():
    result = extract_net_from_shipment_events([{"ShipmentItemList": []}])
    assert result["revenue"] == Decimal("0")
    assert result["by_sku"] == {}


def test_event_with_no_shipment_item_list_key():
    result = extract_net_from_shipment_events([{"SomeOtherKey": "irrelevant"}])
    assert result["revenue"] == Decimal("0")
    assert result["by_sku"] == {}


def test_event_shipment_item_list_is_none():
    result = extract_net_from_shipment_events([{"ShipmentItemList": None}])
    assert result["revenue"] == Decimal("0")


# ---------------------------------------------------------------------------
# SKU accumulation across multiple events
# ---------------------------------------------------------------------------

def test_same_sku_accumulates_across_two_events():
    events = [
        _event(_item("SKU-A", charge="50", fee="-10", qty=1)),
        _event(_item("SKU-A", charge="100", fee="-20", qty=2)),
    ]
    result = extract_net_from_shipment_events(events)
    by = result["by_sku"]["SKU-A"]
    assert by["revenue"] == Decimal("150")
    assert by["fees"] == Decimal("-30")
    assert by["net"] == Decimal("120")
    assert by["qty"] == Decimal("3")


def test_multiple_skus_in_single_event():
    event = _event(
        _item("SKU-X", charge="30", fee="-5", qty=1),
        _item("SKU-Y", charge="60", fee="-10", qty=2),
    )
    result = extract_net_from_shipment_events([event])
    assert result["revenue"] == Decimal("90")
    assert result["fees"] == Decimal("-15")
    assert result["net"] == Decimal("75")
    assert result["by_sku"]["SKU-X"]["net"] == Decimal("25")
    assert result["by_sku"]["SKU-Y"]["net"] == Decimal("50")


def test_total_equals_sum_of_sku_nets():
    events = [
        _event(_item("A", charge="100", fee="-20")),
        _event(_item("B", charge="50", fee="-10")),
    ]
    result = extract_net_from_shipment_events(events)
    sku_nets = sum(v["net"] for v in result["by_sku"].values())
    assert result["net"] == sku_nets


# ---------------------------------------------------------------------------
# Null / missing amounts → treated as zero
# ---------------------------------------------------------------------------

def test_none_charge_amount_treated_as_zero():
    event = {"ShipmentItemList": [{
        "SellerSKU": "SKU-B",
        "QuantityShipped": "1",
        "ItemChargeList": [{"ChargeAmount": {"CurrencyAmount": None}}],
        "ItemFeeList": [],
    }]}
    result = extract_net_from_shipment_events([event])
    assert result["by_sku"]["SKU-B"]["revenue"] == Decimal("0")


def test_none_fee_amount_treated_as_zero():
    event = {"ShipmentItemList": [{
        "SellerSKU": "SKU-C",
        "QuantityShipped": "1",
        "ItemChargeList": [],
        "ItemFeeList": [{"FeeAmount": {"CurrencyAmount": None}}],
    }]}
    result = extract_net_from_shipment_events([event])
    assert result["by_sku"]["SKU-C"]["fees"] == Decimal("0")


def test_empty_charge_and_fee_lists():
    event = {"ShipmentItemList": [{
        "SellerSKU": "SKU-D",
        "QuantityShipped": "1",
        "ItemChargeList": [],
        "ItemFeeList": [],
    }]}
    result = extract_net_from_shipment_events([event])
    assert result["by_sku"]["SKU-D"]["net"] == Decimal("0")


# ---------------------------------------------------------------------------
# Negative charges (refunds / chargebacks)
# ---------------------------------------------------------------------------

def test_negative_charge_refund():
    result = extract_net_from_shipment_events(
        [_event(_item("SKU-E", charge="-50.00", fee="0"))]
    )
    assert result["by_sku"]["SKU-E"]["revenue"] == Decimal("-50.00")
    assert result["net"] == Decimal("-50.00")


# ---------------------------------------------------------------------------
# Missing SKU key → falls back to "UNKNOWN"
# ---------------------------------------------------------------------------

def test_missing_sku_falls_back_to_unknown():
    event = {"ShipmentItemList": [{
        "QuantityShipped": "1",
        "ItemChargeList": [{"ChargeAmount": {"CurrencyAmount": "20"}}],
        "ItemFeeList": [],
    }]}
    result = extract_net_from_shipment_events([event])
    assert "UNKNOWN" in result["by_sku"]


# ---------------------------------------------------------------------------
# Quantity via alternative key
# ---------------------------------------------------------------------------

def test_qty_via_quantity_key_fallback():
    event = {"ShipmentItemList": [{
        "SellerSKU": "SKU-F",
        "Quantity": "5",
        "ItemChargeList": [],
        "ItemFeeList": [],
    }]}
    result = extract_net_from_shipment_events([event])
    assert result["by_sku"]["SKU-F"]["qty"] == Decimal("5")


def test_qty_zero_when_missing():
    event = {"ShipmentItemList": [{
        "SellerSKU": "SKU-G",
        "ItemChargeList": [],
        "ItemFeeList": [],
    }]}
    result = extract_net_from_shipment_events([event])
    assert result["by_sku"]["SKU-G"]["qty"] == Decimal("0")
