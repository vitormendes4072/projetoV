# tests/test_webhook.py
"""Testes para app/notifications/webhook.py."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_resp(status_code: int = 204) -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    return r


# ---------------------------------------------------------------------------
# _is_discord / _is_slack
# ---------------------------------------------------------------------------

def test_is_discord_true():
    from app.notifications.webhook import _is_discord
    assert _is_discord("https://discord.com/api/webhooks/123/abc")
    assert _is_discord("https://discordapp.com/api/webhooks/456/xyz")


def test_is_discord_false():
    from app.notifications.webhook import _is_discord
    assert not _is_discord("https://hooks.slack.com/services/X/Y/Z")


def test_is_slack_true():
    from app.notifications.webhook import _is_slack
    assert _is_slack("https://hooks.slack.com/services/T/B/TOKEN")


def test_is_slack_false():
    from app.notifications.webhook import _is_slack
    assert not _is_slack("https://discord.com/api/webhooks/1/2")


# ---------------------------------------------------------------------------
# _discord_payload / _slack_payload / _generic_payload
# ---------------------------------------------------------------------------

def test_discord_payload_structure():
    from app.notifications.webhook import _discord_payload
    payload = _discord_payload("Título", "Descrição", 15158332)
    assert "embeds" in payload
    embed = payload["embeds"][0]
    assert embed["title"] == "Título"
    assert embed["description"] == "Descrição"
    assert embed["color"] == 15158332
    assert "timestamp" in embed
    assert embed["footer"]["text"] == "VEntregaz"


def test_slack_payload_structure():
    from app.notifications.webhook import _slack_payload
    payload = _slack_payload("Alerta", "Produto XYZ")
    assert "*Alerta*" in payload["text"]
    assert "Produto XYZ" in payload["text"]
    assert payload["blocks"][0]["type"] == "section"


def test_generic_payload_structure():
    from app.notifications.webhook import _generic_payload
    payload = _generic_payload("test", 42, "msg", {"extra_key": "v"})
    assert payload["event"] == "test"
    assert payload["user_id"] == 42
    assert payload["message"] == "msg"
    assert payload["extra_key"] == "v"
    assert "timestamp" in payload


# ---------------------------------------------------------------------------
# dispatch — HTTPS guard
# ---------------------------------------------------------------------------

def test_dispatch_rejects_http():
    from app.notifications.webhook import dispatch
    result = dispatch(
        url="http://example.com/hook",
        event="test",
        title="T",
        description="D",
        user_id=1,
    )
    assert result is False


def test_dispatch_rejects_empty_url():
    from app.notifications.webhook import dispatch
    assert dispatch(url="", event="test", title="T", description="D", user_id=1) is False


def test_dispatch_rejects_none_url():
    from app.notifications.webhook import dispatch
    assert dispatch(url=None, event="test", title="T", description="D", user_id=1) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# dispatch — sucesso Discord / Slack / genérico
# ---------------------------------------------------------------------------

def test_dispatch_discord_success():
    from app.notifications.webhook import dispatch
    with patch("requests.post", return_value=_make_resp(204)) as mock_post:
        ok = dispatch(
            url="https://discord.com/api/webhooks/1/token",
            event="sync_failure",
            title="Falha",
            description="Erro",
            user_id=99,
        )
    assert ok is True
    call_kwargs = mock_post.call_args
    payload = call_kwargs[1]["json"]
    assert "embeds" in payload          # Discord embed


def test_dispatch_slack_success():
    from app.notifications.webhook import dispatch
    with patch("requests.post", return_value=_make_resp(200)) as mock_post:
        ok = dispatch(
            url="https://hooks.slack.com/services/T/B/K",
            event="margin_alert",
            title="Margem",
            description="SKU baixou",
            user_id=7,
        )
    assert ok is True
    payload = mock_post.call_args[1]["json"]
    assert "blocks" in payload          # Slack blocks


def test_dispatch_generic_success():
    from app.notifications.webhook import dispatch
    with patch("requests.post", return_value=_make_resp(200)) as mock_post:
        ok = dispatch(
            url="https://example.com/webhook",
            event="test",
            title="T",
            description="D",
            user_id=5,
            extra={"foo": "bar"},
        )
    assert ok is True
    payload = mock_post.call_args[1]["json"]
    assert payload["event"] == "test"
    assert payload["foo"] == "bar"


# ---------------------------------------------------------------------------
# dispatch — falhas HTTP e exceção de rede
# ---------------------------------------------------------------------------

def test_dispatch_http_4xx_returns_false():
    from app.notifications.webhook import dispatch
    with patch("requests.post", return_value=_make_resp(400)):
        ok = dispatch(
            url="https://example.com/hook",
            event="test",
            title="T",
            description="D",
            user_id=1,
        )
    assert ok is False


def test_dispatch_network_exception_returns_false():
    from app.notifications.webhook import dispatch
    with patch("requests.post", side_effect=ConnectionError("timeout")):
        ok = dispatch(
            url="https://example.com/hook",
            event="test",
            title="T",
            description="D",
            user_id=1,
        )
    assert ok is False


# ---------------------------------------------------------------------------
# notify_sync_failure
# ---------------------------------------------------------------------------

def test_notify_sync_failure_no_webhook_url(app, db):
    """Retorna False quando user não tem webhook_url."""
    from app.notifications.webhook import notify_sync_failure
    from tests.conftest import make_user

    with app.app_context():
        user = make_user(db)           # webhook_url=None por padrão
        result = notify_sync_failure(user_id=user.id, error_msg="boom")

    assert result is False


def test_notify_sync_failure_dispatches(app, db):
    """Chama dispatch quando user tem webhook_url."""
    from app.notifications.webhook import notify_sync_failure
    from tests.conftest import make_user

    with app.app_context():
        user = make_user(db)
        user.webhook_url = "https://discord.com/api/webhooks/1/token"
        db.session.commit()

        with patch("requests.post", return_value=_make_resp(204)):
            result = notify_sync_failure(user_id=user.id, error_msg="SP-API timeout")

    assert result is True


# ---------------------------------------------------------------------------
# notify_margin_alert
# ---------------------------------------------------------------------------

def test_notify_margin_alert_dispatches(app, db):
    from app.notifications.webhook import notify_margin_alert
    from tests.conftest import make_user

    products = [
        {"name": "Produto A", "sku": "SKU-01", "margin": 5.0, "threshold": 10.0},
    ]

    with app.app_context():
        user = make_user(db)
        user.webhook_url = "https://hooks.slack.com/services/T/B/K"
        db.session.commit()

        with patch("requests.post", return_value=_make_resp(200)):
            result = notify_margin_alert(user_id=user.id, products=products)

    assert result is True


# ---------------------------------------------------------------------------
# send_test_webhook
# ---------------------------------------------------------------------------

def test_send_test_webhook_https():
    from app.notifications.webhook import send_test_webhook
    with patch("requests.post", return_value=_make_resp(204)) as mock_post:
        ok = send_test_webhook(url="https://discord.com/api/webhooks/1/t", user_id=3)
    assert ok is True
    payload = mock_post.call_args[1]["json"]
    # color OK = verde
    assert payload["embeds"][0]["color"] == 3066993


def test_send_test_webhook_http_rejected():
    from app.notifications.webhook import send_test_webhook
    with patch("requests.post") as mock_post:
        ok = send_test_webhook(url="http://not-secure.example.com/hook", user_id=3)
    assert ok is False
    mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# /settings/webhook/test route
# ---------------------------------------------------------------------------

def test_route_test_webhook_no_url(client, db):
    """Retorna 400 quando user não tem webhook_url."""
    from tests.conftest import auth_client
    ac = auth_client(client, db)
    resp = ac.post("/settings/webhook/test")
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_route_test_webhook_success(client, db):
    """Retorna 200 quando dispatch bem-sucedido."""
    from app.models.user import User
    from app import db as _db
    from tests.conftest import auth_client

    ac = auth_client(client, db)

    # Definir webhook_url para o usuário já logado
    user = db.session.scalar(_db.select(User).filter_by(email="user@test.com"))
    user.webhook_url = "https://discord.com/api/webhooks/9/token"
    db.session.commit()

    with patch("requests.post", return_value=_make_resp(204)):
        resp = ac.post("/settings/webhook/test")

    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
