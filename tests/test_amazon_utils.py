"""
Testes unitários para app/integrations/amazon/utils.py.
Funções puras — sem fixtures de DB ou contexto Flask.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.integrations.amazon.utils import (
    compute_sync_start,
    extract_amount_currency,
    iso_z,
    parse_iso_dt,
    to_sp,
)

SP_TZ = ZoneInfo("America/Sao_Paulo")


# ---------------------------------------------------------------------------
# iso_z
# ---------------------------------------------------------------------------

def test_iso_z_removes_microseconds():
    dt = datetime(2026, 1, 15, 10, 30, 45, 123456, tzinfo=timezone.utc)
    assert iso_z(dt) == "2026-01-15T10:30:45Z"


def test_iso_z_ends_with_z():
    dt = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    result = iso_z(dt)
    assert result.endswith("Z")
    assert "+00:00" not in result


def test_iso_z_converts_non_utc_to_utc():
    # SP = UTC-3, então 07:00 SP == 10:00 UTC
    dt = datetime(2026, 1, 15, 7, 30, 0, tzinfo=SP_TZ)
    result = iso_z(dt)
    assert "10:30:00Z" in result


# ---------------------------------------------------------------------------
# parse_iso_dt
# ---------------------------------------------------------------------------

def test_parse_iso_dt_empty_string():
    assert parse_iso_dt("") is None


def test_parse_iso_dt_none():
    assert parse_iso_dt(None) is None


def test_parse_iso_dt_valid_z():
    result = parse_iso_dt("2026-01-15T10:30:00Z")
    assert result is not None
    assert result.year == 2026
    assert result.month == 1
    assert result.day == 15
    assert result.tzinfo is not None


def test_parse_iso_dt_invalid_string():
    assert parse_iso_dt("not-a-date") is None


# ---------------------------------------------------------------------------
# to_sp
# ---------------------------------------------------------------------------

def test_to_sp_none_returns_none():
    assert to_sp(None) is None


def test_to_sp_converts_to_sao_paulo():
    dt = datetime(2026, 1, 15, 13, 0, 0, tzinfo=timezone.utc)
    result = to_sp(dt)
    assert result is not None
    # UTC-3 => 10:00 SP
    assert result.hour == 10
    assert result.tzinfo is not None


# ---------------------------------------------------------------------------
# extract_amount_currency
# ---------------------------------------------------------------------------

def test_extract_empty_dict():
    amount, currency = extract_amount_currency({})
    assert amount is None
    assert currency is None


def test_extract_fee_amount_nested():
    ev = {"FeeAmount": {"Amount": "5.99", "CurrencyCode": "BRL"}}
    amount, currency = extract_amount_currency(ev)
    assert amount == "5.99"
    assert currency == "BRL"


def test_extract_currency_amount_key():
    ev = {"ChargeAmount": {"CurrencyAmount": "10.00", "CurrencyCode": "USD"}}
    amount, currency = extract_amount_currency(ev)
    assert amount == "10.00"
    assert currency == "USD"


def test_extract_lowercase_amount_key():
    ev = {"Amount": {"amount": "3.50", "currencyCode": "BRL"}}
    amount, currency = extract_amount_currency(ev)
    assert amount == "3.50"
    assert currency == "BRL"


def test_extract_numeric_value():
    ev = {"FeeAmount": 7.5}
    amount, currency = extract_amount_currency(ev)
    assert amount == 7.5
    assert currency is None


def test_extract_prefers_first_candidate():
    # FeeAmount tem prioridade sobre Amount
    ev = {"FeeAmount": {"Amount": "1.00", "CurrencyCode": "BRL"}, "Amount": {"Amount": "99.00", "CurrencyCode": "USD"}}
    amount, currency = extract_amount_currency(ev)
    assert amount == "1.00"
    assert currency == "BRL"


# ---------------------------------------------------------------------------
# compute_sync_start
# ---------------------------------------------------------------------------

class _FakeConn:
    def __init__(self, last_sync_at=None):
        self.last_sync_at = last_sync_at


def test_compute_sync_start_no_last_sync():
    conn = _FakeConn(last_sync_at=None)
    result = compute_sync_start(conn, days_default=30)
    expected = datetime.now(timezone.utc) - timedelta(days=30)
    assert abs((result - expected).total_seconds()) < 5


def test_compute_sync_start_with_last_sync():
    last = datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc)
    conn = _FakeConn(last_sync_at=last)
    result = compute_sync_start(conn, days_default=30)
    assert result == last - timedelta(days=2)


def test_compute_sync_start_buffer_before_last_sync():
    last = datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc)
    conn = _FakeConn(last_sync_at=last)
    result = compute_sync_start(conn, days_default=7)
    assert result < last  # sempre atrás do last_sync_at
