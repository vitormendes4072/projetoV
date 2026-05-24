"""
Testes para a camada de cache em profit_service.py.

Estratégia: patcheia o objeto `cache` diretamente no módulo — funciona com
qualquer CACHE_TYPE e não depende de comportamento do backend (NullCache,
SimpleCache ou RedisCache).
"""
from decimal import Decimal
from unittest.mock import MagicMock, call, patch

import pytest

from app.integrations.amazon.profit_service import (
    _breakdown_key,
    _cache_version,
    _profit_key,
    compute_order_profit,
    compute_order_item_breakdown,
    invalidate_order_profit_cache,
    invalidate_user_profit_cache,
)

_PS = "app.integrations.amazon.profit_service"


# ---------------------------------------------------------------------------
# _cache_version
# ---------------------------------------------------------------------------

class TestCacheVersion:

    def test_returns_zero_when_key_absent(self):
        with patch(f"{_PS}.cache") as mock_cache:
            mock_cache.get.return_value = None
            assert _cache_version(1) == 0

    def test_returns_stored_integer(self):
        with patch(f"{_PS}.cache") as mock_cache:
            mock_cache.get.return_value = 7
            assert _cache_version(99) == 7

    def test_queries_correct_cache_key(self):
        with patch(f"{_PS}.cache") as mock_cache:
            mock_cache.get.return_value = 0
            _cache_version(42)
            mock_cache.get.assert_called_once_with("ucv:42")


# ---------------------------------------------------------------------------
# _profit_key / _breakdown_key
# ---------------------------------------------------------------------------

class TestCacheKeys:

    def _fixed_cache(self, version=0):
        m = MagicMock()
        m.get.return_value = version
        return m

    def test_profit_key_contains_user_order_tax(self):
        with patch(f"{_PS}.cache", self._fixed_cache()):
            key = _profit_key(5, "111-222-333", 4.5)
        assert "5" in key
        assert "111-222-333" in key
        assert "4.5" in key

    def test_breakdown_key_differs_from_profit_key(self):
        with patch(f"{_PS}.cache", self._fixed_cache()):
            k1 = _profit_key(1, "ORD", 4.0)
            k2 = _breakdown_key(1, "ORD", 4.0)
        assert k1 != k2

    def test_different_version_yields_different_key(self):
        with patch(f"{_PS}.cache", self._fixed_cache(version=0)):
            k_v0 = _profit_key(1, "ORD", 4.0)
        with patch(f"{_PS}.cache", self._fixed_cache(version=1)):
            k_v1 = _profit_key(1, "ORD", 4.0)
        assert k_v0 != k_v1

    def test_different_users_yield_different_keys(self):
        with patch(f"{_PS}.cache", self._fixed_cache()):
            k1 = _profit_key(1, "ORD", 4.0)
            k2 = _profit_key(2, "ORD", 4.0)
        assert k1 != k2

    def test_different_tax_rates_yield_different_keys(self):
        with patch(f"{_PS}.cache", self._fixed_cache()):
            k1 = _profit_key(1, "ORD", 4.0)
            k2 = _profit_key(1, "ORD", 6.0)
        assert k1 != k2


# ---------------------------------------------------------------------------
# invalidate_order_profit_cache
# ---------------------------------------------------------------------------

class TestInvalidateOrderCache:

    def test_calls_delete_twice(self):
        with patch(f"{_PS}.cache") as mock_cache:
            mock_cache.get.return_value = 0
            invalidate_order_profit_cache(1, "ORD-1", 4.0)
        assert mock_cache.delete.call_count == 2

    def test_deletes_profit_and_breakdown_keys(self):
        with patch(f"{_PS}.cache") as mock_cache:
            mock_cache.get.return_value = 0
            with patch(f"{_PS}.cache", mock_cache):
                expected_profit = _profit_key.__wrapped__(0, 1, "ORD-1", 4.0) \
                    if hasattr(_profit_key, "__wrapped__") else None

            invalidate_order_profit_cache(1, "ORD-1", 4.0)

        # Verifica que as duas chaves deletadas são distintas (profit ≠ breakdown)
        deleted_keys = [c.args[0] for c in mock_cache.delete.call_args_list]
        assert len(set(deleted_keys)) == 2, "profit_key e breakdown_key devem ser distintas"


# ---------------------------------------------------------------------------
# invalidate_user_profit_cache
# ---------------------------------------------------------------------------

class TestInvalidateUserCache:

    def test_increments_version_from_existing(self):
        with patch(f"{_PS}.cache") as mock_cache:
            mock_cache.get.return_value = 5
            invalidate_user_profit_cache(1)
        mock_cache.set.assert_called_once()
        new_version = mock_cache.set.call_args[0][1]
        assert new_version == 6

    def test_sets_version_to_one_from_zero(self):
        with patch(f"{_PS}.cache") as mock_cache:
            mock_cache.get.return_value = None  # key absent → version 0
            invalidate_user_profit_cache(1)
        new_version = mock_cache.set.call_args[0][1]
        assert new_version == 1

    def test_uses_user_scoped_key(self):
        with patch(f"{_PS}.cache") as mock_cache:
            mock_cache.get.return_value = 0
            invalidate_user_profit_cache(99)
        set_key = mock_cache.set.call_args[0][0]
        assert "99" in set_key

    def test_sets_with_nonzero_timeout(self):
        with patch(f"{_PS}.cache") as mock_cache:
            mock_cache.get.return_value = 0
            invalidate_user_profit_cache(1)
        timeout = mock_cache.set.call_args[1].get("timeout") or mock_cache.set.call_args[0][2]
        assert timeout > 0


# ---------------------------------------------------------------------------
# compute_order_profit — cache hit / miss / no-store on None
# ---------------------------------------------------------------------------

class TestComputeOrderProfitCacheBehavior:

    def test_cache_hit_skips_db_query(self, app):
        """Se há cache hit, o DB não deve ser consultado."""
        cached = {"ok": True, "mode": "real_from_finance_events", "lucro": 42.0}
        with app.app_context():
            with patch(f"{_PS}.cache") as mock_cache:
                mock_cache.get.return_value = cached
                with patch(f"{_PS}.db") as mock_db:
                    result = compute_order_profit(1, "HIT-ORDER", 4.0)

        assert result is cached
        mock_db.session.scalars.assert_not_called()

    def test_cache_miss_stores_result(self, app):
        """Em cache miss com resultado válido, cache.set deve ser chamado."""
        net_info = {
            "revenue": Decimal("100"), "fees": Decimal("-15"), "net": Decimal("85"),
            "by_sku": {
                "SKU-X": {
                    "revenue": Decimal("100"), "fees": Decimal("-15"),
                    "net": Decimal("85"), "qty": Decimal("1"),
                }
            },
        }
        fin_row = MagicMock()
        fin_row.event_type = "ShipmentEventList"
        fin_row.raw_json = {}

        with app.app_context():
            with patch(f"{_PS}.cache") as mock_cache:
                mock_cache.get.return_value = None  # miss
                with patch(f"{_PS}.db") as mock_db:
                    with patch("app.services.profit_calc.extract_net_from_shipment_events",
                               return_value=net_info):
                        with patch(f"{_PS}._resolve_products_bulk", return_value={}):
                            mock_db.session.scalars.return_value.all.return_value = [fin_row]
                            result = compute_order_profit(1, "MISS-ORDER", 0.0)

        assert result is not None
        assert result["ok"] is True
        mock_cache.set.assert_called_once()
        # Confirma que o resultado armazenado é o mesmo retornado
        assert mock_cache.set.call_args[0][1] is result

    def test_none_result_not_cached(self, app):
        """None (sem eventos) não deve ser armazenado — pode mudar após sync."""
        with app.app_context():
            with patch(f"{_PS}.cache") as mock_cache:
                mock_cache.get.return_value = None
                with patch(f"{_PS}.db") as mock_db:
                    mock_db.session.scalars.return_value.all.return_value = []
                    result = compute_order_profit(1, "NO-EVENTS", 4.0)

        assert result is None
        mock_cache.set.assert_not_called()


# ---------------------------------------------------------------------------
# compute_order_item_breakdown — cache hit / miss
# ---------------------------------------------------------------------------

class TestComputeOrderItemBreakdownCacheBehavior:

    def test_cache_hit_skips_db_query(self, app):
        cached = {"ok": True, "items": [], "items_count": 0}
        with app.app_context():
            with patch(f"{_PS}.cache") as mock_cache:
                mock_cache.get.return_value = cached
                with patch(f"{_PS}.db") as mock_db:
                    result = compute_order_item_breakdown(1, "HIT-BD", 4.0)

        assert result is cached
        mock_db.session.scalar.assert_not_called()
        mock_db.session.scalars.assert_not_called()

    def test_cache_miss_stores_result(self, app):
        mock_order = MagicMock()
        mock_order.order_status = "Shipped"
        mock_order.order_total_amount = Decimal("0")
        mock_order.currency = "BRL"

        with app.app_context():
            with patch(f"{_PS}.cache") as mock_cache:
                mock_cache.get.return_value = None
                with patch(f"{_PS}.db") as mock_db:
                    with patch(f"{_PS}._resolve_products_bulk", return_value={}):
                        mock_db.session.scalar.return_value = mock_order
                        mock_db.session.scalars.return_value.all.side_effect = [[], []]
                        result = compute_order_item_breakdown(1, "MISS-BD", 0.0)

        assert result["ok"] is True
        mock_cache.set.assert_called_once()
        assert mock_cache.set.call_args[0][1] is result
