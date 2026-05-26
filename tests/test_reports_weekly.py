# tests/test_reports_weekly.py
"""Testes para app.financeiro.reports_weekly."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.financeiro.reports_weekly import (
    _negative_simulations,
    _already_sent,
    _week_start,
    send_weekly_loss_report,
)
from app.models.weekly_report_log import WeeklyReportLog

MODULE = "app.financeiro.reports_weekly"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def user(app, db):
    from app.models.user import User

    u = User(email="weekly@test.com", name="Weekly User", confirmed=True)
    u.set_password("pw")
    db.session.add(u)
    db.session.commit()
    return u


def _add_sim(db, user_id, margin, days_ago=0, product_id=None):
    from app.models.pricing import PricingHistory

    ph = PricingHistory(
        user_id=user_id,
        product_id=product_id,
        title=f"Sim margem {margin}",
        price=Decimal("80.00"),
        cost=Decimal("30.00"),
        fba_fee=Decimal("5.00"),
        referral_fee=Decimal("5.00"),
        tax_rate=Decimal("4.00"),
        marketing=Decimal("0.00"),
        net_profit=Decimal(str(80 * margin / 100)),
        margin=Decimal(str(margin)),
        roi=Decimal("20.00"),
        created_at=datetime.now() - timedelta(days=days_ago),
    )
    db.session.add(ph)
    db.session.commit()
    return ph


# ---------------------------------------------------------------------------
# Unit: _week_start
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("d,expected", [
    (date(2026, 5, 25), date(2026, 5, 25)),   # segunda-feira
    (date(2026, 5, 26), date(2026, 5, 25)),   # terça
    (date(2026, 5, 31), date(2026, 5, 25)),   # domingo
    (date(2026, 6, 1),  date(2026, 6, 1)),    # segunda seguinte
])
def test_week_start(d, expected):
    assert _week_start(d) == expected


# ---------------------------------------------------------------------------
# Unit: _negative_simulations
# ---------------------------------------------------------------------------

def test_negative_simulations_returns_only_negative(app, db, user):
    monday = _week_start(date.today())
    _add_sim(db, user.id, margin=-5.0,  days_ago=0)
    _add_sim(db, user.id, margin=-10.0, days_ago=0)
    _add_sim(db, user.id, margin=15.0,  days_ago=0)   # positivo — excluído

    result = _negative_simulations(user.id, monday)
    assert len(result) == 2
    assert all(s.margin < 0 for s in result)


def test_negative_simulations_excludes_old(app, db, user):
    """Simulação da semana passada não aparece."""
    monday = _week_start(date.today())
    _add_sim(db, user.id, margin=-5.0, days_ago=8)   # antes de week_start

    result = _negative_simulations(user.id, monday)
    assert result == []


# ---------------------------------------------------------------------------
# Unit: _already_sent / dedupe
# ---------------------------------------------------------------------------

def test_already_sent_false_initially(app, db, user):
    assert _already_sent(user.id, date.today()) is False


def test_already_sent_true_after_log(app, db, user):
    log = WeeklyReportLog(
        user_id=user.id,
        week_start=date.today(),
        neg_simulations=1,
        neg_orders=0,
    )
    db.session.add(log)
    db.session.commit()
    assert _already_sent(user.id, date.today()) is True


# ---------------------------------------------------------------------------
# Integration: send_weekly_loss_report
# ---------------------------------------------------------------------------

def test_send_report_when_negative_sims_exist(app, db, user):
    """Há simulação negativa → envia e-mail."""
    monday = _week_start(date.today())
    _add_sim(db, user.id, margin=-8.0)

    with patch(f"{MODULE}.mail") as mock_mail:
        summary = send_weekly_loss_report(run_date=date.today())

    assert summary["emails_sent"] == 1
    mock_mail.send.assert_called_once()

    # Log criado
    from app import db as _db
    log = _db.session.scalar(
        _db.select(WeeklyReportLog).filter_by(
            user_id=user.id,
            week_start=monday,
        )
    )
    assert log is not None
    assert log.neg_simulations == 1


def test_skip_when_no_negatives(app, db, user):
    """Nenhuma simulação negativa → skipped_no_negatives."""
    _add_sim(db, user.id, margin=20.0)

    with patch(f"{MODULE}.mail") as mock_mail:
        summary = send_weekly_loss_report(run_date=date.today())

    assert summary["emails_sent"] == 0
    assert summary["skipped_no_negatives"] == 1
    mock_mail.send.assert_not_called()


def test_skip_when_no_simulations_at_all(app, db, user):
    """Usuário sem simulações → skipped_no_negatives."""
    with patch(f"{MODULE}.mail") as mock_mail:
        summary = send_weekly_loss_report(run_date=date.today())

    assert summary["emails_sent"] == 0
    assert summary["skipped_no_negatives"] == 1
    mock_mail.send.assert_not_called()


def test_dedupe_same_week(app, db, user):
    """Segunda chamada na mesma semana → skipped_already_sent."""
    _add_sim(db, user.id, margin=-5.0)

    with patch(f"{MODULE}.mail"):
        send_weekly_loss_report(run_date=date.today())

    with patch(f"{MODULE}.mail") as mock_mail2:
        summary2 = send_weekly_loss_report(run_date=date.today())

    assert summary2["emails_sent"] == 0
    assert summary2["skipped_already_sent"] == 1
    mock_mail2.send.assert_not_called()


def test_different_week_sends_again(app, db, user):
    """Semana diferente → envia novamente (dedupe não bloqueia)."""
    _add_sim(db, user.id, margin=-5.0, days_ago=8)   # semana passada

    last_monday = _week_start(date.today() - timedelta(days=7))

    with patch(f"{MODULE}.mail"):
        send_weekly_loss_report(run_date=last_monday)

    # Agora adiciona negativo nesta semana e roda para hoje
    _add_sim(db, user.id, margin=-3.0, days_ago=0)

    with patch(f"{MODULE}.mail") as mock_mail:
        summary = send_weekly_loss_report(run_date=date.today())

    assert summary["emails_sent"] == 1
    mock_mail.send.assert_called_once()


def test_dry_run_no_email_no_log(app, db, user):
    """dry_run=True não envia e-mail nem cria log."""
    _add_sim(db, user.id, margin=-7.0)

    with patch(f"{MODULE}.mail") as mock_mail:
        summary = send_weekly_loss_report(run_date=date.today(), dry_run=True)

    assert summary["dry_run"] is True
    assert summary["emails_sent"] == 0
    mock_mail.send.assert_not_called()

    from app import db as _db
    count = _db.session.scalar(
        _db.select(_db.func.count(WeeklyReportLog.id)).where(
            WeeklyReportLog.user_id == user.id
        )
    )
    assert count == 0


def test_summary_keys_present(app, db, user):
    """Estrutura do summary contém todas as chaves esperadas."""
    with patch(f"{MODULE}.mail"):
        summary = send_weekly_loss_report(run_date=date.today())

    expected = {
        "run_date", "week_start", "users_total",
        "emails_sent", "skipped_no_negatives",
        "skipped_already_sent", "skipped_missing_email", "dry_run",
    }
    assert expected.issubset(set(summary.keys()))
