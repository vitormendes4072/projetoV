"""
Testes unitários para app/relatorios/service.py (get_monthly_report, available_months).
Usa o fixture db do conftest — PricingHistory está nas tabelas SQLite compatíveis.
"""
from datetime import datetime
from decimal import Decimal

import pytest

from app.models.pricing import PricingHistory
from app.relatorios.service import available_months, get_monthly_report
from tests.conftest import make_user


def _make_pricing(db, user_id, margin, roi, year=2026, month=1):
    sim = PricingHistory(
        user_id=user_id,
        title="Test",
        price=Decimal("100"),
        cost=Decimal("60"),
        fba_fee=Decimal("10"),
        referral_fee=Decimal("15"),
        tax_rate=Decimal("5"),
        marketing=Decimal("0"),
        net_profit=Decimal(str(roi)),
        margin=Decimal(str(margin)),
        roi=Decimal(str(roi)),
        created_at=datetime(year, month, 15, 10, 0, 0),
    )
    db.session.add(sim)
    db.session.commit()
    return sim


# ---------------------------------------------------------------------------
# get_monthly_report — mês sem dados
# ---------------------------------------------------------------------------

def test_get_monthly_report_empty_returns_zeros(db):
    result = get_monthly_report(user_id=9999, year=2000, month=1)
    assert result["total"] == 0
    assert result["avg_margin"] == 0.0
    assert result["avg_roi"] == 0.0
    assert result["pct_profitable"] == 0.0
    assert result["rows"] == []
    assert result["year"] == 2000
    assert result["month"] == 1


# ---------------------------------------------------------------------------
# get_monthly_report — cálculo de KPIs
# ---------------------------------------------------------------------------

def test_get_monthly_report_avg_margin_and_roi(db):
    user = make_user(db, email="relsvc_kpi@test.com")
    _make_pricing(db, user.id, margin=20.0, roi=30.0, year=2026, month=3)
    _make_pricing(db, user.id, margin=10.0, roi=15.0, year=2026, month=3)

    result = get_monthly_report(user_id=user.id, year=2026, month=3)

    assert result["total"] == 2
    assert result["avg_margin"] == 15.0   # (20 + 10) / 2
    assert result["avg_roi"] == 22.5      # (30 + 15) / 2
    assert result["pct_profitable"] == 100.0
    assert len(result["rows"]) == 2


def test_get_monthly_report_partial_profitable(db):
    user = make_user(db, email="relsvc_pct@test.com")
    _make_pricing(db, user.id, margin=10.0, roi=5.0, year=2026, month=4)
    _make_pricing(db, user.id, margin=-5.0, roi=-2.0, year=2026, month=4)

    result = get_monthly_report(user_id=user.id, year=2026, month=4)

    assert result["total"] == 2
    assert result["pct_profitable"] == 50.0


def test_get_monthly_report_all_unprofitable(db):
    user = make_user(db, email="relsvc_loss@test.com")
    _make_pricing(db, user.id, margin=-10.0, roi=-5.0, year=2026, month=5)
    _make_pricing(db, user.id, margin=-3.0, roi=-1.0, year=2026, month=5)

    result = get_monthly_report(user_id=user.id, year=2026, month=5)

    assert result["pct_profitable"] == 0.0


def test_get_monthly_report_single_row(db):
    user = make_user(db, email="relsvc_single@test.com")
    _make_pricing(db, user.id, margin=25.0, roi=40.0, year=2026, month=6)

    result = get_monthly_report(user_id=user.id, year=2026, month=6)

    assert result["total"] == 1
    assert result["avg_margin"] == 25.0
    assert result["avg_roi"] == 40.0
    assert result["pct_profitable"] == 100.0


# ---------------------------------------------------------------------------
# get_monthly_report — isolamento por user e por mês
# ---------------------------------------------------------------------------

def test_get_monthly_report_isolates_by_user(db):
    user_a = make_user(db, email="relsvc_ua@test.com")
    user_b = make_user(db, email="relsvc_ub@test.com")
    _make_pricing(db, user_a.id, margin=20.0, roi=25.0, year=2026, month=7)
    _make_pricing(db, user_b.id, margin=30.0, roi=35.0, year=2026, month=7)

    result = get_monthly_report(user_id=user_a.id, year=2026, month=7)

    assert result["total"] == 1
    assert result["avg_margin"] == 20.0


def test_get_monthly_report_isolates_by_month(db):
    user = make_user(db, email="relsvc_months@test.com")
    _make_pricing(db, user.id, margin=20.0, roi=25.0, year=2026, month=1)
    _make_pricing(db, user.id, margin=30.0, roi=35.0, year=2026, month=2)

    result = get_monthly_report(user_id=user.id, year=2026, month=1)

    assert result["total"] == 1
    assert result["avg_margin"] == 20.0


def test_get_monthly_report_isolates_by_year(db):
    user = make_user(db, email="relsvc_years@test.com")
    _make_pricing(db, user.id, margin=10.0, roi=5.0, year=2025, month=1)
    _make_pricing(db, user.id, margin=20.0, roi=10.0, year=2026, month=1)

    result = get_monthly_report(user_id=user.id, year=2026, month=1)

    assert result["total"] == 1
    assert result["avg_margin"] == 20.0


# ---------------------------------------------------------------------------
# available_months
# ---------------------------------------------------------------------------

def test_available_months_empty(db):
    result = available_months(user_id=9999)
    assert result == []


def test_available_months_returns_distinct(db):
    user = make_user(db, email="avail_distinct@test.com")
    # Two rows in same month → should appear only once
    _make_pricing(db, user.id, margin=10.0, roi=5.0, year=2026, month=1)
    _make_pricing(db, user.id, margin=12.0, roi=6.0, year=2026, month=1)
    _make_pricing(db, user.id, margin=10.0, roi=5.0, year=2026, month=2)

    result = available_months(user_id=user.id)

    assert result.count((2026, 1)) == 1
    assert (2026, 2) in result


def test_available_months_descending_order(db):
    user = make_user(db, email="avail_order@test.com")
    _make_pricing(db, user.id, margin=10.0, roi=5.0, year=2025, month=12)
    _make_pricing(db, user.id, margin=10.0, roi=5.0, year=2026, month=1)
    _make_pricing(db, user.id, margin=10.0, roi=5.0, year=2026, month=2)

    result = available_months(user_id=user.id)

    assert result[0] == (2026, 2)
    assert result[1] == (2026, 1)
    assert result[2] == (2025, 12)


def test_available_months_isolates_by_user(db):
    user_a = make_user(db, email="avail_ua@test.com")
    user_b = make_user(db, email="avail_ub@test.com")
    _make_pricing(db, user_a.id, margin=10.0, roi=5.0, year=2026, month=6)
    _make_pricing(db, user_b.id, margin=10.0, roi=5.0, year=2026, month=7)

    result = available_months(user_id=user_a.id)

    months = list(result)
    assert (2026, 6) in months
    assert (2026, 7) not in months


def test_available_months_returns_tuples_of_ints(db):
    user = make_user(db, email="avail_types@test.com")
    _make_pricing(db, user.id, margin=10.0, roi=5.0, year=2026, month=3)

    result = available_months(user_id=user.id)

    assert len(result) == 1
    year, month = result[0]
    assert isinstance(year, int)
    assert isinstance(month, int)
