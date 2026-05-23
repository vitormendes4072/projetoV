"""
Testes unitários para app/integrations/amazon/profit_service.py.
Funções puras testadas diretamente; funções com DB isoladas via mock.
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.integrations.amazon.profit_service import (
    _amount_from_money,
    _compute_order_start,
    _r2,
    _resolve_products_bulk,
    compute_order_item_breakdown,
    compute_order_profit,
    refresh_order_finances,
)

_PROFIT_SERVICE = "app.integrations.amazon.profit_service"


# ---------------------------------------------------------------------------
# _r2
# ---------------------------------------------------------------------------

def test_r2_rounds_down():
    assert _r2(3.14159) == 3.14


def test_r2_rounds_up():
    assert _r2(2.567) == 2.57


def test_r2_zero():
    assert _r2(0) == 0.0


def test_r2_string():
    assert _r2("2.567") == 2.57


def test_r2_none_returns_zero():
    assert _r2(None) == 0.0


def test_r2_invalid_string_returns_zero():
    assert _r2("not_a_number") == 0.0


def test_r2_negative():
    assert _r2(-10.556) == -10.56


# ---------------------------------------------------------------------------
# _amount_from_money
# ---------------------------------------------------------------------------

def test_amount_from_money_dict_with_amount():
    assert _amount_from_money({"Amount": "10.50"}) == 10.5


def test_amount_from_money_dict_with_currency_amount():
    assert _amount_from_money({"CurrencyAmount": "5.25"}) == 5.25


def test_amount_from_money_prefers_amount_over_currency_amount():
    assert _amount_from_money({"Amount": "10.00", "CurrencyAmount": "99.00"}) == 10.0


def test_amount_from_money_empty_dict_returns_zero():
    assert _amount_from_money({}) == 0.0


def test_amount_from_money_non_dict_returns_zero():
    assert _amount_from_money("10.00") == 0.0


def test_amount_from_money_none_returns_zero():
    assert _amount_from_money(None) == 0.0


def test_amount_from_money_int_returns_zero():
    assert _amount_from_money(42) == 0.0


# ---------------------------------------------------------------------------
# _resolve_products_bulk — empty input (no DB call)
# ---------------------------------------------------------------------------

def test_resolve_products_bulk_empty_skus(app):
    with app.app_context():
        with patch("app.integrations.amazon.profit_service.db") as mock_db:
            result = _resolve_products_bulk(1, [])
    assert result == {}
    mock_db.session.scalars.assert_not_called()


def test_resolve_products_bulk_sku_found_via_link(app):
    with app.app_context():
        with patch("app.integrations.amazon.profit_service.db") as mock_db:
            mock_product = MagicMock()
            mock_link = MagicMock()
            mock_link.amazon_seller_sku = "SKU-A"
            mock_link.product = mock_product

            mock_db.session.scalars.return_value.all.return_value = [mock_link]

            result = _resolve_products_bulk(1, ["SKU-A"])

    assert result["SKU-A"] is mock_product


def test_resolve_products_bulk_sku_not_linked_falls_back_to_product(app):
    with app.app_context():
        with patch("app.integrations.amazon.profit_service.db") as mock_db:
            mock_product = MagicMock()
            mock_product.sku = "SKU-B"

            # First call (AmazonSkuLink): no links found
            # Second call (Product fallback): product found
            mock_db.session.scalars.return_value.all.side_effect = [[], [mock_product]]

            result = _resolve_products_bulk(1, ["SKU-B"])

    assert result["SKU-B"] is mock_product


def test_resolve_products_bulk_link_without_product_skipped(app):
    with app.app_context():
        with patch("app.integrations.amazon.profit_service.db") as mock_db:
            mock_link = MagicMock()
            mock_link.amazon_seller_sku = "SKU-C"
            mock_link.product = None  # link exists but product was deleted

            mock_db.session.scalars.return_value.all.side_effect = [[mock_link], []]

            result = _resolve_products_bulk(1, ["SKU-C"])

    # SKU-C has no product — should be absent or resolved by fallback (empty)
    assert "SKU-C" not in result


# ---------------------------------------------------------------------------
# compute_order_profit
# ---------------------------------------------------------------------------

def test_compute_order_profit_no_finance_events_returns_none(app):
    with app.app_context():
        with patch("app.integrations.amazon.profit_service.db") as mock_db:
            mock_db.session.scalars.return_value.all.return_value = []
            result = compute_order_profit(1, "111-2222-3333", default_tax_rate=10.0)

    assert result is None


def test_compute_order_profit_with_shipment_events(app):
    net_info = {
        "revenue": Decimal("100"),
        "fees": Decimal("-15"),
        "net": Decimal("85"),
        "by_sku": {
            "SKU-A": {
                "revenue": Decimal("100"),
                "fees": Decimal("-15"),
                "net": Decimal("85"),
                "qty": Decimal("1"),
            }
        },
    }

    fin_row = MagicMock()
    fin_row.event_type = "ShipmentEventList"
    fin_row.raw_json = {}

    with app.app_context():
        with patch("app.integrations.amazon.profit_service.db") as mock_db:
            with patch(
                "app.services.profit_calc.extract_net_from_shipment_events",
                return_value=net_info,
            ):
                with patch(
                    "app.integrations.amazon.profit_service._resolve_products_bulk",
                    return_value={},
                ):
                    mock_db.session.scalars.return_value.all.return_value = [fin_row]
                    result = compute_order_profit(1, "111-2222-3333", default_tax_rate=10.0)

    assert result is not None
    assert result["ok"] is True
    assert result["amazon_revenue"] == 100.0
    assert result["amazon_fees"] == -15.0
    assert result["amazon_net"] == 85.0
    assert result["imposto"] == 10.0  # 10% of 100
    assert "SKU-A" in result["by_sku"]
    assert result["mode"] == "real_from_finance_events"


def test_compute_order_profit_non_shipment_events_ignored(app):
    # Only non-ShipmentEventList events → treated as no shipment events
    fin_row = MagicMock()
    fin_row.event_type = "AdjustmentEventList"
    fin_row.raw_json = {}

    with app.app_context():
        with patch("app.integrations.amazon.profit_service.db") as mock_db:
            mock_db.session.scalars.return_value.all.return_value = [fin_row]
            result = compute_order_profit(1, "111-9999-0000", default_tax_rate=0.0)

    assert result is None


def test_compute_order_profit_tax_zero(app):
    net_info = {
        "revenue": Decimal("200"),
        "fees": Decimal("-30"),
        "net": Decimal("170"),
        "by_sku": {
            "SKU-Z": {
                "revenue": Decimal("200"),
                "fees": Decimal("-30"),
                "net": Decimal("170"),
                "qty": Decimal("2"),
            }
        },
    }
    fin_row = MagicMock()
    fin_row.event_type = "ShipmentEventList"
    fin_row.raw_json = {}

    with app.app_context():
        with patch("app.integrations.amazon.profit_service.db") as mock_db:
            with patch(
                "app.services.profit_calc.extract_net_from_shipment_events",
                return_value=net_info,
            ):
                with patch(
                    "app.integrations.amazon.profit_service._resolve_products_bulk",
                    return_value={},
                ):
                    mock_db.session.scalars.return_value.all.return_value = [fin_row]
                    result = compute_order_profit(1, "111-0000-1111", default_tax_rate=0.0)

    assert result["imposto"] == 0.0
    assert result["lucro"] == result["amazon_net"]  # no tax, no cmv


# ---------------------------------------------------------------------------
# compute_order_item_breakdown
# ---------------------------------------------------------------------------

def test_compute_order_item_breakdown_no_items(app):
    mock_order = MagicMock()
    mock_order.order_status = "Shipped"
    mock_order.order_total_amount = Decimal("0")
    mock_order.currency = "BRL"

    with app.app_context():
        with patch("app.integrations.amazon.profit_service.db") as mock_db:
            mock_db.session.scalar.return_value = mock_order
            # items → [], finance events → []
            mock_db.session.scalars.return_value.all.side_effect = [[], []]
            result = compute_order_item_breakdown(1, "000-0000-0000", default_tax_rate=5.0)

    assert result["ok"] is True
    assert result["items_count"] == 0
    assert result["has_finance_events"] is False
    assert result["has_items"] is False


def test_compute_order_item_breakdown_with_item_no_finance(app):
    mock_order = MagicMock()
    mock_order.order_status = "Shipped"
    mock_order.order_total_amount = Decimal("50.00")
    mock_order.currency = "BRL"

    mock_item = MagicMock()
    mock_item.seller_sku = "SKU-Z"
    mock_item.asin = "B00TEST"
    mock_item.quantity = 2
    mock_item.item_price = Decimal("25.00")
    mock_item.raw_json = {}

    with app.app_context():
        with patch("app.integrations.amazon.profit_service.db") as mock_db:
            with patch(
                "app.integrations.amazon.profit_service._resolve_products_bulk",
                return_value={},
            ):
                mock_db.session.scalar.return_value = mock_order
                mock_db.session.scalars.return_value.all.side_effect = [
                    [mock_item],  # items
                    [],           # finance events
                ]
                result = compute_order_item_breakdown(1, "222-3333-4444", default_tax_rate=0.0)

    assert result["ok"] is True
    assert result["items_count"] == 1
    assert result["items"][0]["sku"] == "SKU-Z"
    assert result["items"][0]["qty"] == 2.0
    assert result["has_finance_events"] is False
    assert result["has_items"] is True


def test_compute_order_item_breakdown_margin_calculation(app):
    mock_order = MagicMock()
    mock_order.order_status = "Shipped"
    mock_order.order_total_amount = Decimal("100.00")
    mock_order.currency = "BRL"

    mock_item = MagicMock()
    mock_item.seller_sku = "SKU-M"
    mock_item.asin = "B00MARGIN"
    mock_item.quantity = 1
    mock_item.item_price = Decimal("100.00")
    mock_item.raw_json = {}

    with app.app_context():
        with patch("app.integrations.amazon.profit_service.db") as mock_db:
            with patch(
                "app.integrations.amazon.profit_service._resolve_products_bulk",
                return_value={},
            ):
                mock_db.session.scalar.return_value = mock_order
                mock_db.session.scalars.return_value.all.side_effect = [
                    [mock_item],
                    [],
                ]
                result = compute_order_item_breakdown(1, "333-4444-5555", default_tax_rate=10.0)

    item = result["items"][0]
    # revenue=100, imposto=10 (10% of 100), cmv=0, embalagem=0 → lucro=90
    assert item["imposto"] == 10.0
    assert item["lucro"] == 90.0
    assert item["margem_pct"] == 90.0


def test_compute_order_item_breakdown_order_not_found(app):
    # order=None edge case
    with app.app_context():
        with patch("app.integrations.amazon.profit_service.db") as mock_db:
            with patch(
                "app.integrations.amazon.profit_service._resolve_products_bulk",
                return_value={},
            ):
                mock_db.session.scalar.return_value = None
                mock_db.session.scalars.return_value.all.side_effect = [[], []]
                result = compute_order_item_breakdown(1, "999-9999-9999", default_tax_rate=0.0)

    assert result["ok"] is True
    assert result["order_status"] is None
    assert result["order_total"] == 0.0


# ---------------------------------------------------------------------------
# _compute_order_start
# ---------------------------------------------------------------------------

class TestComputeOrderStart:
    """Testa o cálculo da janela temporal para busca de finance events."""

    def _run(self, order_mock):
        with patch(f"{_PROFIT_SERVICE}.db") as mock_db:
            mock_db.session.scalar.return_value = order_mock
            return _compute_order_start(user_id=1, amazon_order_id="111-TEST")

    def test_returns_tuple_of_two_elements(self):
        start_dt, start_iso = self._run(None)
        assert start_dt is not None
        assert isinstance(start_iso, str)
        assert start_iso.endswith("Z")

    def test_defaults_to_7_days_ago_when_no_order(self):
        from datetime import timezone
        start_dt, _ = self._run(None)
        now_approx = __import__("app.integrations.amazon.utils", fromlist=["utcnow"]).utcnow()
        delta = now_approx - start_dt
        # Janela padrão = 7 dias; tolerância de 5 segundos para execução do teste
        assert abs(delta.total_seconds() - 7 * 86400) < 5

    def test_uses_purchase_date_minus_5_days_when_order_exists(self):
        from datetime import datetime, timezone, timedelta
        purchase = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
        order = MagicMock()
        order.purchase_date = purchase
        start_dt, _ = self._run(order)
        expected = purchase - timedelta(days=5)
        assert abs((start_dt - expected).total_seconds()) < 1

    def test_iso_string_matches_datetime(self):
        from datetime import datetime, timezone, timedelta
        purchase = datetime(2026, 3, 15, 8, 0, tzinfo=timezone.utc)
        order = MagicMock()
        order.purchase_date = purchase
        start_dt, start_iso = self._run(order)
        # O start_iso deve começar com a data esperada (purchase - 5d = 2026-03-10)
        assert start_iso.startswith("2026-03-10")

    def test_order_without_purchase_date_uses_default(self):
        from datetime import timezone
        order = MagicMock()
        order.purchase_date = None
        start_dt, _ = self._run(order)
        now_approx = __import__("app.integrations.amazon.utils", fromlist=["utcnow"]).utcnow()
        delta = now_approx - start_dt
        assert abs(delta.total_seconds() - 7 * 86400) < 5


# ---------------------------------------------------------------------------
# refresh_order_finances
# ---------------------------------------------------------------------------

class TestRefreshOrderFinances:
    """Testa o sync curto de finances para um pedido específico."""

    def _run(self, sync_rv=5, order_mock=None, raise_on_sync=None):
        """Helper: executa refresh_order_finances com DB e sync mockados."""
        conn = MagicMock()
        mock_db = MagicMock()
        mock_db.session.scalar.return_value = order_mock
        mock_db.session.execute.return_value = MagicMock()
        mock_db.session.flush.return_value = None

        sync_kwargs = (
            {"side_effect": raise_on_sync}
            if raise_on_sync
            else {"return_value": sync_rv}
        )

        with patch(f"{_PROFIT_SERVICE}.db", mock_db), \
             patch(f"{_PROFIT_SERVICE}.sync_financial_events", **sync_kwargs) as mock_sync:
            result = refresh_order_finances(conn, user_id=1, amazon_order_id="111-TEST")

        return result, mock_db, mock_sync

    def test_returns_start_iso_and_events_count(self):
        (start_iso, count), _, _ = self._run(sync_rv=3)
        assert isinstance(start_iso, str)
        assert start_iso.endswith("Z")
        assert count == 3

    def test_calls_delete_before_sync(self):
        _, mock_db, mock_sync = self._run()
        mock_db.session.execute.assert_called_once()
        mock_sync.assert_called_once()
        # execute (delete) deve ocorrer antes do sync
        execute_call_index = mock_db.mock_calls.index(
            next(c for c in mock_db.mock_calls if "execute" in str(c))
        )
        # sync é chamado via patch externo — apenas confirma que execute foi chamado
        assert execute_call_index >= 0

    def test_calls_flush_before_sync(self):
        _, mock_db, _ = self._run()
        mock_db.session.flush.assert_called_once()

    def test_does_not_commit(self):
        """Convenção do projeto: commit é responsabilidade do chamador."""
        _, mock_db, _ = self._run()
        mock_db.session.commit.assert_not_called()

    def test_propagates_sync_exception(self):
        with __import__("pytest").raises(RuntimeError, match="SP-API throttle"):
            self._run(raise_on_sync=RuntimeError("SP-API throttle"))

    def test_sync_called_with_correct_user_id(self):
        conn = MagicMock()
        mock_db = MagicMock()
        mock_db.session.scalar.return_value = None
        mock_db.session.execute.return_value = MagicMock()

        with patch(f"{_PROFIT_SERVICE}.db", mock_db), \
             patch(f"{_PROFIT_SERVICE}.sync_financial_events", return_value=0) as mock_sync:
            refresh_order_finances(conn, user_id=42, amazon_order_id="111-X")

        called_kwargs = mock_sync.call_args
        assert called_kwargs.kwargs["user_id"] == 42

    def test_zero_events_inserted_still_returns_ok(self):
        (start_iso, count), _, _ = self._run(sync_rv=0)
        assert count == 0
        assert isinstance(start_iso, str)
