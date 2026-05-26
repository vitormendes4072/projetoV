"""
Testes para app/auth/oauth.py — OAuth 2.0 (Google + GitHub).

Estratégia:
  - oauth_login() e oauth_callback() são mockados via patch do objeto oauth.
  - _get_or_create_user() e _extract_user_info() são testados diretamente
    usando o SQLite de testes (sem tocar em providers externos).
  - User.check_password() com password_hash=None testado em user.py indiretamente.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.models.oauth_account import OAuthAccount
from app.models.user import User
from app.auth.oauth import _get_or_create_user, _extract_user_info
from tests.conftest import auth_client, make_user


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def logged_client(client, db):
    return auth_client(client, db)


# ---------------------------------------------------------------------------
# Rotas — guard de provider inválido
# ---------------------------------------------------------------------------

def test_oauth_login_invalid_provider(logged_client):
    resp = logged_client.get("/auth/login/twitter")
    assert resp.status_code in (302, 400)
    # Deve redirecionar para login (não crashar)
    if resp.status_code == 302:
        assert "login" in resp.headers["Location"]


def test_oauth_callback_invalid_provider(logged_client):
    resp = logged_client.get("/auth/callback/twitter")
    assert resp.status_code in (302, 400)


# ---------------------------------------------------------------------------
# Rotas — provider sem configuração (client_id=None)
# ---------------------------------------------------------------------------

def test_oauth_login_unconfigured_provider(client, db):
    auth_client(client, db)
    with patch("app.auth.oauth.oauth") as mock_oauth:
        mock_oauth.create_client.return_value = None
        resp = client.get("/auth/login/google")
    assert resp.status_code == 302
    assert "login" in resp.headers["Location"]


# ---------------------------------------------------------------------------
# Rota /auth/login/<provider> — redireciona para provider
# ---------------------------------------------------------------------------

def test_oauth_login_google_redirects(client, db):
    auth_client(client, db)
    mock_client = MagicMock()
    mock_client.authorize_redirect.return_value = \
        MagicMock(status_code=302, headers={"Location": "https://accounts.google.com/o/oauth2/auth"})
    with patch("app.auth.oauth.oauth") as mock_oauth:
        mock_oauth.create_client.return_value = mock_client
        client.get("/auth/login/google")
    mock_client.authorize_redirect.assert_called_once()


def test_oauth_login_github_redirects(client, db):
    auth_client(client, db)
    mock_client = MagicMock()
    mock_client.authorize_redirect.return_value = \
        MagicMock(status_code=302, headers={"Location": "https://github.com/login/oauth/authorize"})
    with patch("app.auth.oauth.oauth") as mock_oauth:
        mock_oauth.create_client.return_value = mock_client
        client.get("/auth/login/github")
    mock_client.authorize_redirect.assert_called_once()


# ---------------------------------------------------------------------------
# Callback — falha ao trocar code por token
# ---------------------------------------------------------------------------

def test_oauth_callback_token_exchange_failure(client, db):
    auth_client(client, db)
    mock_client = MagicMock()
    mock_client.authorize_access_token.side_effect = Exception("OAuth error")
    with patch("app.auth.oauth.oauth") as mock_oauth:
        mock_oauth.create_client.return_value = mock_client
        resp = client.get("/auth/callback/google")
    assert resp.status_code == 302
    assert "login" in resp.headers["Location"]


# ---------------------------------------------------------------------------
# _get_or_create_user — testa com SQLite real
# ---------------------------------------------------------------------------

def test_get_or_create_creates_new_user(app, db):
    with app.app_context():
        user = _get_or_create_user("google", "google-uid-999", "new@oauth.com", "Novo User")
        db.session.refresh(user)

        assert user.id is not None
        assert user.email == "new@oauth.com"
        assert user.confirmed is True
        assert user.password_hash is None

        account = db.session.scalar(
            db.select(OAuthAccount).filter_by(provider="google", provider_user_id="google-uid-999")
        )
        assert account is not None
        assert account.user_id == user.id


def test_get_or_create_returns_existing_account(app, db):
    with app.app_context():
        # Primeira chamada cria
        user1 = _get_or_create_user("github", "gh-uid-42", "repeat@oauth.com", "Repeat")
        # Segunda chamada retorna o mesmo user
        user2 = _get_or_create_user("github", "gh-uid-42", "repeat@oauth.com", "Repeat")
        assert user1.id == user2.id

        # Só um OAuthAccount deve existir
        count = db.session.scalar(
            db.select(db.func.count(OAuthAccount.id)).filter_by(
                provider="github", provider_user_id="gh-uid-42"
            )
        )
        assert count == 1


def test_get_or_create_links_existing_email_user(app, db):
    """Email já cadastrado via email/senha → vincula OAuthAccount, não duplica User."""
    with app.app_context():
        existing = make_user(db, email="link@test.com")
        original_id = existing.id

        user = _get_or_create_user("google", "google-link-uid", "link@test.com", "Link User")

        assert user.id == original_id
        assert user.confirmed is True

        account = db.session.scalar(
            db.select(OAuthAccount).filter_by(provider="google", provider_user_id="google-link-uid")
        )
        assert account is not None
        assert account.user_id == original_id

        # Não duplicou o user
        count = db.session.scalar(
            db.select(db.func.count(User.id)).filter_by(email="link@test.com")
        )
        assert count == 1


# ---------------------------------------------------------------------------
# _extract_user_info — testa extração de dados por provider
# ---------------------------------------------------------------------------

def test_extract_user_info_google():
    mock_client = MagicMock()
    token = {
        "userinfo": {
            "sub": "google-123",
            "email": "google@test.com",
            "name": "Google User",
        }
    }
    uid, email, name = _extract_user_info("google", mock_client, token)
    assert uid == "google-123"
    assert email == "google@test.com"
    assert name == "Google User"


def test_extract_user_info_github():
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "id": 99999,
        "name": "GitHub User",
        "email": "github@test.com",
        "login": "ghuser",
    }
    mock_client.get.return_value = mock_resp
    token = {}
    uid, email, name = _extract_user_info("github", mock_client, token)
    assert uid == "99999"
    assert email == "github@test.com"
    assert name == "GitHub User"


def test_extract_user_info_github_fetches_email_from_endpoint():
    """GitHub retorna email=None no perfil → busca na endpoint /user/emails."""
    mock_client = MagicMock()

    profile_resp = MagicMock()
    profile_resp.json.return_value = {"id": 88888, "name": "GH", "email": None, "login": "gh"}

    emails_resp = MagicMock()
    emails_resp.json.return_value = [
        {"email": "primary@gh.com", "primary": True, "verified": True},
        {"email": "other@gh.com",   "primary": False, "verified": True},
    ]

    mock_client.get.side_effect = [profile_resp, emails_resp]
    uid, email, name = _extract_user_info("github", mock_client, {})
    assert email == "primary@gh.com"


# ---------------------------------------------------------------------------
# User.check_password com password_hash=None (OAuth-only)
# ---------------------------------------------------------------------------

def test_check_password_returns_false_for_oauth_user(app, db):
    with app.app_context():
        user = _get_or_create_user("google", "no-pass-uid", "nopass@test.com", "No Pass")
        assert user.password_hash is None
        assert user.check_password("qualquercoisa") is False
