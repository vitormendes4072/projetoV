# tests/test_alerts_margin.py
"""Testes para app.financeiro.alerts_margin."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.financeiro.alerts_margin import (
    _already_sent,
    _latest_margin,
    _products_with_threshold,
    send_margin_alerts,
)
from app.models.margin_alert_log import MarginAlertLog

MODULE = "app.financeiro.alerts_margin"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def user(app, db):
    from app.models.user import User

    u = User(email="margin@test.com", name="Margin User", confirmed=True)
    u.set_password("pw")
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture()
def product_with_threshold(app, db, user):
    from app.models.product import Product

    p = Product(
        name="Produto Teste",
        sku="SKU-TEST-01",
        cost=Decimal("10.00"),
        price=Decimal("30.00"),
        packaging_cost=Decimal("0.00"),
        user_id=user.id,
        margin_alert_threshold=Decimal("20.00"),
    )
    db.session.add(p)
    db.session.commit()
    return p


@pytest.fixture()
def product_no_threshold(app, db, user):
    from app.models.product import Product

    p = Product(
        name="Sem Threshold",
        sku="SKU-NO-THR",
        cost=Decimal("10.00"),
        price=Decimal("30.00"),
        packaging_cost=Decimal("0.00"),
        user_id=user.id,
        margin_alert_threshold=None,
    )
    db.session.add(p)
    db.session.commit()
    return p


def _add_pricing(db, user_id, product_id, margin, days_ago=0):
    from app.models.pricing import PricingHistory

    ph = PricingHistory(
        user_id=user_id,
        product_id=product_id,
        title="Teste",
        price=Decimal("30.00"),
        cost=Decimal("10.00"),
        fba_fee=Decimal("2.00"),
        referral_fee=Decimal("2.00"),
        tax_rate=Decimal("4.00"),
        marketing=Decimal("0.00"),
        net_profit=Decimal("5.00"),
        margin=Decimal(str(margin)),
        roi=Decimal("20.00"),
        created_at=datetime.now() - timedelta(days=days_ago),
    )
    db.session.add(ph)
    db.session.commit()
    return ph


# ---------------------------------------------------------------------------
# Unit: _latest_margin
# ---------------------------------------------------------------------------

def test_latest_margin_returns_most_recent(app, db, user, product_with_threshold):
    _add_pricing(db, user.id, product_with_threshold.id, margin="25.00", days_ago=5)
    _add_pricing(db, user.id, product_with_threshold.id, margin="12.00", days_ago=0)

    result = _latest_margin(product_with_threshold.id)
    assert result is not None
    assert float(result) == pytest.approx(12.0)


def test_latest_margin_none_when_no_simulation(app, db, user, product_with_threshold):
    result = _latest_margin(product_with_threshold.id)
    assert result is None


# ---------------------------------------------------------------------------
# Unit: _products_with_threshold
# ---------------------------------------------------------------------------

def test_products_with_threshold_excludes_null(app, db, user, product_with_threshold, product_no_threshold):
    products = _products_with_threshold(user.id)
    ids = [p.id for p in products]
    assert product_with_threshold.id in ids
    assert product_no_threshold.id not in ids


# ---------------------------------------------------------------------------
# Unit: _already_sent / dedupe
# ---------------------------------------------------------------------------

def test_already_sent_false_when_no_log(app, db, user, product_with_threshold):
    assert _already_sent(user.id, product_with_threshold.id, date.today()) is False


def test_already_sent_true_after_mark(app, db, user, product_with_threshold):
    log = MarginAlertLog(
        user_id=user.id,
        product_id=product_with_threshold.id,
        alert_date=date.today(),
        margin_value=Decimal("10.00"),
    )
    db.session.add(log)
    db.session.commit()

    assert _already_sent(user.id, product_with_threshold.id, date.today()) is True


# ---------------------------------------------------------------------------
# Integration: send_margin_alerts
# ---------------------------------------------------------------------------

def test_send_margin_alerts_sends_when_below_threshold(app, db, user, product_with_threshold):
    """Margem 10% < threshold 20% → envia e-mail."""
    _add_pricing(db, user.id, product_with_threshold.id, margin="10.00")

    with patch(f"{MODULE}.mail") as mock_mail:
        summary = send_margin_alerts(run_day=date.today())

    assert summary["emails_sent"] == 1
    assert summary["alerts_sent"] == 1
    mock_mail.send.assert_called_once()

    from app import db as _db
    log = _db.session.scalar(
        _db.select(MarginAlertLog).filter_by(
            user_id=user.id,
            product_id=product_with_threshold.id,
            alert_date=date.today(),
        )
    )
    assert log is not None


def test_send_margin_alerts_skips_when_above_threshold(app, db, user, product_with_threshold):
    """Margem 25% >= threshold 20% → não envia."""
    _add_pricing(db, user.id, product_with_threshold.id, margin="25.00")

    with patch(f"{MODULE}.mail") as mock_mail:
        summary = send_margin_alerts(run_day=date.today())

    assert summary["emails_sent"] == 0
    assert summary["skipped_above_threshold"] == 1
    mock_mail.send.assert_not_called()


def test_send_margin_alerts_skips_when_no_simulation(app, db, user, product_with_threshold):
    """Sem simulação vinculada → skipped_no_simulation."""
    with patch(f"{MODULE}.mail") as mock_mail:
        summary = send_margin_alerts(run_day=date.today())

    assert summary["emails_sent"] == 0
    assert summary["skipped_no_simulation"] == 1
    mock_mail.send.assert_not_called()


def test_send_margin_alerts_dedupe_same_day(app, db, user, product_with_threshold):
    """Segunda chamada no mesmo dia não envia novamente."""
    _add_pricing(db, user.id, product_with_threshold.id, margin="10.00")

    with patch(f"{MODULE}.mail"):
        send_margin_alerts(run_day=date.today())

    with patch(f"{MODULE}.mail") as mock_mail2:
        summary2 = send_margin_alerts(run_day=date.today())

    assert summary2["emails_sent"] == 0
    assert summary2["skipped_already_sent"] == 1
    mock_mail2.send.assert_not_called()


def test_send_margin_alerts_dry_run(app, db, user, product_with_threshold):
    """dry_run=True não envia e-mail nem cria log."""
    _add_pricing(db, user.id, product_with_threshold.id, margin="5.00")

    with patch(f"{MODULE}.mail") as mock_mail:
        summary = send_margin_alerts(run_day=date.today(), dry_run=True)

    assert summary["dry_run"] is True
    assert summary["emails_sent"] == 0
    mock_mail.send.assert_not_called()

    from app import db as _db
    count = _db.session.scalar(
        _db.select(_db.func.count(MarginAlertLog.id)).where(
            MarginAlertLog.user_id == user.id
        )
    )
    assert count == 0


def test_send_margin_alerts_skips_product_without_threshold(app, db, user, product_no_threshold):
    """Produto sem threshold não gera alerta mesmo com margem baixa."""
    _add_pricing(db, user.id, product_no_threshold.id, margin="1.00")

    with patch(f"{MODULE}.mail") as mock_mail:
        summary = send_margin_alerts(run_day=date.today())

    assert summary["emails_sent"] == 0
    mock_mail.send.assert_not_called()
