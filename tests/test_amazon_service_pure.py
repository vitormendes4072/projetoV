"""
Testes unitários para funções puras de app/integrations/amazon/service.py.
Nenhuma chamada real à SP-API — time.sleep é mockado nos testes de retry.
"""
import pytest
from unittest.mock import MagicMock, patch

from sp_api.base import Marketplaces
from sp_api.base.exceptions import SellingApiRequestThrottledException

from app.integrations.amazon.service import (
    _compute_fingerprint,
    _credentials,
    _safe_payload,
    _with_retry,
    marketplace_from_id,
)


class _Throttled(SellingApiRequestThrottledException):
    """Subclasse sem __init__ para instanciar sem args obrigatórios."""
    def __init__(self):
        pass


# ---------------------------------------------------------------------------
# _safe_payload
# ---------------------------------------------------------------------------

def test_safe_payload_none_response_raises():
    with pytest.raises(RuntimeError, match="None"):
        _safe_payload(None, "test_ctx")


def test_safe_payload_payload_is_none_raises():
    res = MagicMock()
    res.payload = None
    with pytest.raises(RuntimeError, match="payload"):
        _safe_payload(res, "test_ctx")


def test_safe_payload_returns_payload():
    res = MagicMock()
    res.payload = {"Orders": [{"AmazonOrderId": "123"}]}
    payload = _safe_payload(res, "test_ctx")
    assert payload == {"Orders": [{"AmazonOrderId": "123"}]}


def test_safe_payload_empty_dict_payload():
    res = MagicMock()
    res.payload = {}
    # empty dict is falsy → `payload or {}` returns {}; no RuntimeError
    payload = _safe_payload(res, "test_ctx")
    assert payload == {}


# ---------------------------------------------------------------------------
# marketplace_from_id
# ---------------------------------------------------------------------------

def test_marketplace_from_id_brazil():
    result = marketplace_from_id(Marketplaces.BR.marketplace_id)
    assert result == Marketplaces.BR


def test_marketplace_from_id_unknown_falls_back_to_br():
    result = marketplace_from_id("UNKNOWN_MARKETPLACE_ID")
    assert result == Marketplaces.BR


# ---------------------------------------------------------------------------
# _credentials
# ---------------------------------------------------------------------------

def test_credentials_fields_mapped_correctly():
    conn = MagicMock()
    conn.lwa_refresh_token = "tok_refresh"
    conn.lwa_client_id = "client_id_123"
    conn.lwa_client_secret = "client_secret_abc"
    conn.aws_access_key_id = "AKIATEST"
    conn.aws_secret_access_key = "secret_key"
    conn.role_arn = None

    creds = _credentials(conn)

    assert creds["refresh_token"] == "tok_refresh"
    assert creds["lwa_app_id"] == "client_id_123"
    assert creds["lwa_client_secret"] == "client_secret_abc"
    assert creds["aws_access_key"] == "AKIATEST"
    assert creds["aws_secret_key"] == "secret_key"


def test_credentials_without_role_arn_omits_key():
    conn = MagicMock()
    conn.role_arn = None
    assert "role_arn" not in _credentials(conn)


def test_credentials_with_role_arn_includes_key():
    conn = MagicMock()
    conn.role_arn = "arn:aws:iam::123456789:role/SpApiRole"
    creds = _credentials(conn)
    assert creds["role_arn"] == "arn:aws:iam::123456789:role/SpApiRole"


# ---------------------------------------------------------------------------
# _with_retry
# ---------------------------------------------------------------------------

def test_with_retry_success_first_call():
    fn = MagicMock(return_value={"ok": True})
    with patch("app.integrations.amazon.service.time.sleep") as mock_sleep:
        result = _with_retry(fn, max_retries=3)
    assert result == {"ok": True}
    fn.assert_called_once()
    mock_sleep.assert_not_called()


def test_with_retry_none_response_retries_then_succeeds():
    success = {"data": "ok"}
    fn = MagicMock(side_effect=[None, None, success])
    with patch("app.integrations.amazon.service.time.sleep"):
        result = _with_retry(fn, max_retries=5)
    assert result == success
    assert fn.call_count == 3


def test_with_retry_throttled_then_succeeds():
    success = {"data": "ok"}
    fn = MagicMock(side_effect=[_Throttled(), _Throttled(), success])
    with patch("app.integrations.amazon.service.time.sleep"):
        result = _with_retry(fn, max_retries=5)
    assert result == success
    assert fn.call_count == 3


def test_with_retry_network_error_then_succeeds():
    success = {"data": "ok"}
    fn = MagicMock(side_effect=[ConnectionError("timeout"), success])
    with patch("app.integrations.amazon.service.time.sleep"):
        result = _with_retry(fn, max_retries=3)
    assert result == success
    assert fn.call_count == 2


def test_with_retry_all_throttled_reraises():
    fn = MagicMock(side_effect=_Throttled())
    with patch("app.integrations.amazon.service.time.sleep"):
        with pytest.raises(SellingApiRequestThrottledException):
            _with_retry(fn, max_retries=3)
    assert fn.call_count == 3


def test_with_retry_all_none_raises_runtime_error():
    fn = MagicMock(return_value=None)
    with patch("app.integrations.amazon.service.time.sleep"):
        with pytest.raises(RuntimeError, match="None"):
            _with_retry(fn, max_retries=3, ctx="test_ctx")
    assert fn.call_count == 3


def test_with_retry_non_retryable_raises_immediately():
    fn = MagicMock(side_effect=ValueError("unexpected error"))
    with patch("app.integrations.amazon.service.time.sleep"):
        with pytest.raises(ValueError, match="unexpected error"):
            _with_retry(fn, max_retries=5)
    fn.assert_called_once()


def test_with_retry_os_error_is_retryable():
    success = {"data": "ok"}
    fn = MagicMock(side_effect=[OSError("connection reset"), success])
    with patch("app.integrations.amazon.service.time.sleep"):
        result = _with_retry(fn, max_retries=3)
    assert result == success


def test_with_retry_sleep_called_on_throttle():
    fn = MagicMock(side_effect=[_Throttled(), {"ok": True}])
    with patch("app.integrations.amazon.service.time.sleep") as mock_sleep:
        _with_retry(fn, max_retries=3, base_sleep=1.0)
    # Sleep must have been called once (after the throttle)
    assert mock_sleep.call_count == 1


# ---------------------------------------------------------------------------
# _compute_fingerprint
# ---------------------------------------------------------------------------

_FP_TUPLE = ("ShipmentEventList", "111-2222-3333", None, "2026-01-01", "100.00", "BRL", "SKU-A")


def test_compute_fingerprint_consistent():
    fp1 = _compute_fingerprint(1, _FP_TUPLE)
    fp2 = _compute_fingerprint(1, _FP_TUPLE)
    assert fp1 == fp2


def test_compute_fingerprint_max_64_chars():
    fp = _compute_fingerprint(1, _FP_TUPLE)
    assert len(fp) <= 64


def test_compute_fingerprint_different_users_differ():
    fp1 = _compute_fingerprint(1, _FP_TUPLE)
    fp2 = _compute_fingerprint(2, _FP_TUPLE)
    assert fp1 != fp2


def test_compute_fingerprint_different_tuples_differ():
    fp1 = _compute_fingerprint(1, ("TypeA", "order-1", None, "2026-01-01", "10.00", "BRL", "x"))
    fp2 = _compute_fingerprint(1, ("TypeB", "order-2", None, "2026-01-02", "20.00", "USD", "y"))
    assert fp1 != fp2


def test_compute_fingerprint_hex_string():
    fp = _compute_fingerprint(1, _FP_TUPLE)
    # sha256 hex chars only
    assert all(c in "0123456789abcdef" for c in fp)
