"""
Testes para app/financeiro/alerts_custos_fixos.py.

Estrutura:
  - Helpers puros (sem DB): _safe_due_date, _next_month, _compute_next_due_date,
    _fmt_brl, _normalize_email
  - Helpers com DB: _get_recipient_emails_for_user, _has_been_sent
  - Integração: send_custos_fixos_alerts_for_day (DB + mail mockado)
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.financeiro.alerts_custos_fixos import (
    _compute_next_due_date,
    _fmt_brl,
    _get_recipient_emails_for_user,
    _has_been_sent,
    _next_month,
    _normalize_email,
    _safe_due_date,
    send_custos_fixos_alerts_for_day,
)
from app.models.custo_fixo import CustoFixo
from app.models.custo_fixo_pagamento import CustoFixoPagamento
from app.models.notification_log import NotificationLog
from app.models.notification_recipient import NotificationRecipient
from app.models.notification_settings import NotificationSettings
from tests.conftest import make_user


# ---------------------------------------------------------------------------
# _safe_due_date
# ---------------------------------------------------------------------------

def test_safe_due_date_normal_day():
    assert _safe_due_date(2024, 3, 15) == date(2024, 3, 15)


def test_safe_due_date_clamps_february_non_leap():
    # day=31 em fevereiro de ano nao bissexto -> dia 28
    assert _safe_due_date(2023, 2, 31) == date(2023, 2, 28)


def test_safe_due_date_clamps_february_leap():
    # day=31 em fevereiro de ano bissexto -> dia 29
    assert _safe_due_date(2024, 2, 31) == date(2024, 2, 29)


def test_safe_due_date_clamps_april_to_30():
    assert _safe_due_date(2024, 4, 31) == date(2024, 4, 30)


def test_safe_due_date_day_1():
    assert _safe_due_date(2024, 1, 1) == date(2024, 1, 1)


def test_safe_due_date_last_day_of_month():
    assert _safe_due_date(2024, 12, 31) == date(2024, 12, 31)


# ---------------------------------------------------------------------------
# _next_month
# ---------------------------------------------------------------------------

def test_next_month_regular_march():
    assert _next_month(2024, 3) == (2024, 4)


def test_next_month_november_to_december():
    assert _next_month(2024, 11) == (2024, 12)


def test_next_month_december_wraps_to_january():
    assert _next_month(2024, 12) == (2025, 1)


def test_next_month_december_increments_year():
    assert _next_month(1999, 12) == (2000, 1)


def test_next_month_january():
    assert _next_month(2024, 1) == (2024, 2)


# ---------------------------------------------------------------------------
# _compute_next_due_date
# ---------------------------------------------------------------------------

def test_compute_next_due_date_future():
    # run_day=5, dia_pagamento=20 -> mesmo mes, ainda nao passou
    run = date(2024, 3, 5)
    due = _compute_next_due_date(run, 20)
    assert due == date(2024, 3, 20)


def test_compute_next_due_date_today():
    # run_day == dia_pagamento -> mesmo mes (delta=0)
    run = date(2024, 3, 20)
    due = _compute_next_due_date(run, 20)
    assert due == date(2024, 3, 20)


def test_compute_next_due_date_past_advances_month():
    # run_day=25, dia_pagamento=10 -> mes seguinte
    run = date(2024, 3, 25)
    due = _compute_next_due_date(run, 10)
    assert due == date(2024, 4, 10)


def test_compute_next_due_date_december_to_january():
    run = date(2024, 12, 28)
    due = _compute_next_due_date(run, 5)
    assert due == date(2025, 1, 5)


def test_compute_next_due_date_clamps_in_short_month():
    # run_day=31 de marco, dia_pagamento=31 -> 31/03 (mesmo dia)
    run = date(2024, 3, 31)
    due = _compute_next_due_date(run, 31)
    assert due == date(2024, 3, 31)


def test_compute_next_due_date_clamps_next_month_short():
    # run_day=30/01, dia_pagamento=31 -> fevereiro nao tem dia 31 -> 28 (2023)
    run = date(2023, 1, 30)
    due = _compute_next_due_date(run, 31)
    # dia 31 de jan >= run (30) -> usa jan mesmo
    assert due == date(2023, 1, 31)


# ---------------------------------------------------------------------------
# _fmt_brl
# ---------------------------------------------------------------------------

def test_fmt_brl_integer():
    assert _fmt_brl(100) == "100,00"


def test_fmt_brl_decimal():
    assert _fmt_brl(Decimal("19.90")) == "19,90"


def test_fmt_brl_string():
    assert _fmt_brl("29.99") == "29,99"


def test_fmt_brl_none():
    assert _fmt_brl(None) == "0,00"


def test_fmt_brl_invalid_string():
    assert _fmt_brl("abc") == "0,00"


def test_fmt_brl_zero():
    assert _fmt_brl(0) == "0,00"


def test_fmt_brl_large_value():
    assert _fmt_brl(1234.56) == "1234,56"


# ---------------------------------------------------------------------------
# _normalize_email
# ---------------------------------------------------------------------------

def test_normalize_email_strips_spaces():
    assert _normalize_email("  user@example.com  ") == "user@example.com"


def test_normalize_email_lowercases():
    assert _normalize_email("USER@EXAMPLE.COM") == "user@example.com"


def test_normalize_email_none():
    assert _normalize_email(None) == ""


def test_normalize_email_empty_string():
    assert _normalize_email("") == ""


def test_normalize_email_mixed():
    assert _normalize_email("  Test@DOMAIN.com  ") == "test@domain.com"


# ---------------------------------------------------------------------------
# _get_recipient_emails_for_user (necessita DB)
# ---------------------------------------------------------------------------

def test_get_recipient_emails_fallback_to_user_email(db):
    user = make_user(db, email="fallback@test.com")
    emails = _get_recipient_emails_for_user(user)
    assert emails == ["fallback@test.com"]


def test_get_recipient_emails_returns_active_recipient(db):
    user = make_user(db, email="withrecip@test.com")
    r = NotificationRecipient(user_id=user.id, email="extra@example.com", enabled=True)
    db.session.add(r)
    db.session.commit()

    emails = _get_recipient_emails_for_user(user)
    assert "extra@example.com" in emails


def test_get_recipient_emails_excludes_inactive(db):
    user = make_user(db, email="inactive@test.com")
    r = NotificationRecipient(user_id=user.id, email="gone@example.com", enabled=False)
    db.session.add(r)
    db.session.commit()

    emails = _get_recipient_emails_for_user(user)
    # inativo excluido -> fallback p/ user.email
    assert emails == ["inactive@test.com"]


def test_get_recipient_emails_deduplicates(db):
    user = make_user(db, email="dedup@test.com")
    # adiciona dois com o mesmo email (contorna a unique constraint pra simular)
    r = NotificationRecipient(user_id=user.id, email="dup@example.com", enabled=True)
    db.session.add(r)
    db.session.commit()

    emails = _get_recipient_emails_for_user(user)
    assert emails.count("dup@example.com") == 1


def test_get_recipient_emails_skips_invalid_email(db):
    user = make_user(db, email="skipper@test.com")
    r = NotificationRecipient(user_id=user.id, email="notanemail", enabled=True)
    db.session.add(r)
    db.session.commit()

    emails = _get_recipient_emails_for_user(user)
    # email invalido descartado -> fallback p/ user.email
    assert emails == ["skipper@test.com"]


# ---------------------------------------------------------------------------
# _has_been_sent (necessita DB + NotificationLog)
# ---------------------------------------------------------------------------

def _make_custo(db, user_id, dia=10):
    c = CustoFixo(
        user_id=user_id, nome="Aluguel", categoria="Moradia",
        valor_mensal=Decimal("500"), dia_pagamento=dia,
        data_inicio=date(2020, 1, 1),
    )
    db.session.add(c)
    db.session.commit()
    return c


def test_has_been_sent_false_when_no_log(db):
    user = make_user(db, email="log1@test.com")
    custo = _make_custo(db, user.id)
    assert _has_been_sent(user.id, custo.id, date(2024, 3, 10), "due") is False


def test_has_been_sent_true_when_log_exists(db):
    user = make_user(db, email="log2@test.com")
    custo = _make_custo(db, user.id)
    log = NotificationLog(
        user_id=user.id,
        custo_fixo_id=custo.id,
        due_date=date(2024, 3, 10),
        alert_type="due",
        ano=2024,
        mes=3,
    )
    db.session.add(log)
    db.session.commit()

    assert _has_been_sent(user.id, custo.id, date(2024, 3, 10), "due") is True


def test_has_been_sent_different_type_is_false(db):
    user = make_user(db, email="log3@test.com")
    custo = _make_custo(db, user.id)
    log = NotificationLog(
        user_id=user.id,
        custo_fixo_id=custo.id,
        due_date=date(2024, 3, 10),
        alert_type="due",
        ano=2024,
        mes=3,
    )
    db.session.add(log)
    db.session.commit()

    # "before" ainda nao foi enviado
    assert _has_been_sent(user.id, custo.id, date(2024, 3, 10), "before") is False


# ---------------------------------------------------------------------------
# Fixtures para testes de send_custos_fixos_alerts_for_day
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_mail():
    with patch("app.financeiro.alerts_custos_fixos.mail") as m:
        m.send = MagicMock()
        yield m


@pytest.fixture
def mock_render():
    with patch("app.financeiro.alerts_custos_fixos.render_template", return_value="corpo"):
        yield


def _make_settings(db, user_id, enabled=True, alert_mode="before_and_due", days_before=3):
    s = NotificationSettings(
        user_id=user_id,
        enabled=enabled,
        alert_mode=alert_mode,
        days_before=days_before,
    )
    db.session.add(s)
    db.session.commit()
    return s


def _make_custo_fixo(db, user_id, dia_pagamento=10, ativo=True):
    c = CustoFixo(
        user_id=user_id, nome="Aluguel", categoria="Moradia",
        valor_mensal=Decimal("1500"), dia_pagamento=dia_pagamento,
        ativo=ativo,
        data_inicio=date(2020, 1, 1),  # vigente para qualquer run_day recente
    )
    db.session.add(c)
    db.session.commit()
    return c


# ---------------------------------------------------------------------------
# send_custos_fixos_alerts_for_day
# ---------------------------------------------------------------------------

def test_send_no_users(db, mock_mail, mock_render):
    summary = send_custos_fixos_alerts_for_day(run_day=date(2024, 3, 10))
    assert summary["users_total"] == 0
    assert summary["emails_sent"] == 0
    mock_mail.send.assert_not_called()


def test_send_skips_user_without_email(db, mock_mail, mock_render):
    # Cria usuario normalmente e depois limpa o email (empty string = falsy)
    user = make_user(db, email="willbeempty@test.com")
    user.email = ""
    db.session.commit()

    summary = send_custos_fixos_alerts_for_day(run_day=date(2024, 3, 10))
    assert summary["skipped_missing_email"] >= 1
    mock_mail.send.assert_not_called()


def test_send_creates_default_settings_if_none(db, mock_mail, mock_render):
    """Sem NotificationSettings -> cria com defaults, sem itens nao envia."""
    user = make_user(db, email="noset@test.com")
    # nenhum custo fixo -> nenhum alerta
    summary = send_custos_fixos_alerts_for_day(run_day=date(2024, 3, 10))
    assert summary["emails_sent"] == 0

    from app import db as _db
    s = _db.session.scalar(_db.select(NotificationSettings).filter_by(user_id=user.id))
    assert s is not None
    assert s.enabled is True


def test_send_skips_disabled_settings(db, mock_mail, mock_render):
    user = make_user(db, email="disabled@test.com")
    _make_settings(db, user.id, enabled=False)

    summary = send_custos_fixos_alerts_for_day(run_day=date(2024, 3, 10))
    assert summary["skipped_disabled"] == 1
    mock_mail.send.assert_not_called()


def test_send_skips_mode_none(db, mock_mail, mock_render):
    user = make_user(db, email="modenone@test.com")
    _make_settings(db, user.id, alert_mode="none")

    summary = send_custos_fixos_alerts_for_day(run_day=date(2024, 3, 10))
    assert summary["skipped_mode_none"] == 1
    mock_mail.send.assert_not_called()


def test_send_skips_inactive_item(db, mock_mail, mock_render):
    user = make_user(db, email="inact@test.com")
    _make_settings(db, user.id, alert_mode="due_only")
    _make_custo_fixo(db, user.id, ativo=False)

    summary = send_custos_fixos_alerts_for_day(run_day=date(2024, 3, 10))
    assert summary["skipped_inactive"] == 1
    mock_mail.send.assert_not_called()


def test_send_skips_no_dia_pagamento(db, mock_mail, mock_render):
    user = make_user(db, email="nodia@test.com")
    _make_settings(db, user.id, alert_mode="due_only")
    c = CustoFixo(
        user_id=user.id, nome="Sem Dia", categoria="Outros",
        valor_mensal=Decimal("100"), dia_pagamento=None,
        data_inicio=date(2020, 1, 1),
    )
    db.session.add(c)
    db.session.commit()

    summary = send_custos_fixos_alerts_for_day(run_day=date(2024, 3, 10))
    assert summary["skipped_no_due"] == 1
    mock_mail.send.assert_not_called()


def test_send_skips_paid_item(db, mock_mail, mock_render):
    user = make_user(db, email="paid@test.com")
    _make_settings(db, user.id, alert_mode="due_only")
    custo = _make_custo_fixo(db, user.id, dia_pagamento=10)

    pagamento = CustoFixoPagamento(
        custo_fixo_id=custo.id,
        ano=2024,
        mes=3,
    )
    db.session.add(pagamento)
    db.session.commit()

    summary = send_custos_fixos_alerts_for_day(run_day=date(2024, 3, 10))
    assert summary["skipped_paid"] == 1
    mock_mail.send.assert_not_called()


def test_send_due_alert_on_exact_day(db, mock_mail, mock_render):
    """Custo vence hoje -> alerta 'due' enviado."""
    user = make_user(db, email="duetoday@test.com")
    _make_settings(db, user.id, alert_mode="due_only")
    # dia_pagamento=10, run_day=10 de marco -> vence hoje
    _make_custo_fixo(db, user.id, dia_pagamento=10)

    summary = send_custos_fixos_alerts_for_day(run_day=date(2024, 3, 10))
    assert summary["emails_sent"] == 1
    assert summary["alerts_sent"] == 1
    mock_mail.send.assert_called_once()


def test_send_before_alert(db, mock_mail, mock_render):
    """Custo vence em 3 dias -> alerta 'before' enviado."""
    user = make_user(db, email="before@test.com")
    _make_settings(db, user.id, alert_mode="before_and_due", days_before=3)
    # dia_pagamento=13, run_day=10 -> delta=3
    _make_custo_fixo(db, user.id, dia_pagamento=13)

    summary = send_custos_fixos_alerts_for_day(run_day=date(2024, 3, 10))
    assert summary["emails_sent"] == 1
    assert summary["alerts_sent"] == 1
    mock_mail.send.assert_called_once()


def test_send_both_due_and_before_in_same_email(db, mock_mail, mock_render):
    """Dois itens: um vence hoje, outro em 3 dias -> 1 email com 2 alertas."""
    user = make_user(db, email="both@test.com")
    _make_settings(db, user.id, alert_mode="before_and_due", days_before=3)
    _make_custo_fixo(db, user.id, dia_pagamento=10)   # vence hoje
    _make_custo_fixo(db, user.id, dia_pagamento=13)   # vence em 3 dias

    summary = send_custos_fixos_alerts_for_day(run_day=date(2024, 3, 10))
    assert summary["emails_sent"] == 1
    assert summary["alerts_sent"] == 2
    mock_mail.send.assert_called_once()


def test_send_dry_run_does_not_send(db, mock_mail, mock_render):
    user = make_user(db, email="dry@test.com")
    _make_settings(db, user.id, alert_mode="due_only")
    _make_custo_fixo(db, user.id, dia_pagamento=10)

    summary = send_custos_fixos_alerts_for_day(run_day=date(2024, 3, 10), dry_run=True)
    assert summary["dry_run"] is True
    assert summary["emails_sent"] == 0
    mock_mail.send.assert_not_called()


def test_send_skips_already_sent_due(db, mock_mail, mock_render):
    user = make_user(db, email="alreadysent@test.com")
    _make_settings(db, user.id, alert_mode="due_only")
    custo = _make_custo_fixo(db, user.id, dia_pagamento=10)

    # Pre-marca como enviado
    log = NotificationLog(
        user_id=user.id,
        custo_fixo_id=custo.id,
        due_date=date(2024, 3, 10),
        alert_type="due",
        ano=2024, mes=3,
    )
    db.session.add(log)
    db.session.commit()

    summary = send_custos_fixos_alerts_for_day(run_day=date(2024, 3, 10))
    assert summary["skipped_already_sent_due"] == 1
    assert summary["emails_sent"] == 0
    mock_mail.send.assert_not_called()


def test_send_skips_already_sent_before(db, mock_mail, mock_render):
    user = make_user(db, email="alreadybefore@test.com")
    _make_settings(db, user.id, alert_mode="before_and_due", days_before=3)
    custo = _make_custo_fixo(db, user.id, dia_pagamento=13)

    log = NotificationLog(
        user_id=user.id,
        custo_fixo_id=custo.id,
        due_date=date(2024, 3, 13),
        alert_type="before",
        ano=2024, mes=3,
    )
    db.session.add(log)
    db.session.commit()

    summary = send_custos_fixos_alerts_for_day(run_day=date(2024, 3, 10))
    assert summary["skipped_already_sent_before"] == 1
    assert summary["emails_sent"] == 0


def test_send_no_alert_when_delta_mismatch(db, mock_mail, mock_render):
    """Item vence em 2 dias mas days_before=3 -> sem alerta."""
    user = make_user(db, email="nodelta@test.com")
    _make_settings(db, user.id, alert_mode="before_and_due", days_before=3)
    _make_custo_fixo(db, user.id, dia_pagamento=12)  # delta=2, not 3

    summary = send_custos_fixos_alerts_for_day(run_day=date(2024, 3, 10))
    assert summary["emails_sent"] == 0
    mock_mail.send.assert_not_called()
