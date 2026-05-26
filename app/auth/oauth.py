"""
app/auth/oauth.py
─────────────────
OAuth 2.0 via Authlib — Google e GitHub.

Fluxo por provider:
  GET /auth/login/<provider>      → redireciona para o provider
  GET /auth/callback/<provider>   → troca code por token, busca/cria user, loga

Lógica de _get_or_create_user():
  1. OAuthAccount já existe → login direto
  2. Email já existe como User local → vincula OAuthAccount, loga
  3. Nenhum dos dois → cria User (sem senha, confirmed=True) + OAuthAccount, loga
"""
from __future__ import annotations

import logging

from authlib.integrations.flask_client import OAuth
from flask import Blueprint, current_app, flash, redirect, url_for
from flask_login import login_user

from app import db
from app.models.oauth_account import OAuthAccount
from app.models.user import User

logger = logging.getLogger(__name__)

oauth_bp = Blueprint("oauth", __name__, url_prefix="/auth")

# Instância global — init_app() chamado em create_app()
oauth = OAuth()


def init_oauth(app):
    """Registra os providers no objeto OAuth e vincula ao app."""
    oauth.init_app(app)

    oauth.register(
        name="google",
        client_id=app.config.get("GOOGLE_CLIENT_ID"),
        client_secret=app.config.get("GOOGLE_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

    oauth.register(
        name="github",
        client_id=app.config.get("GITHUB_CLIENT_ID"),
        client_secret=app.config.get("GITHUB_CLIENT_SECRET"),
        access_token_url="https://github.com/login/oauth/access_token",
        authorize_url="https://github.com/login/oauth/authorize",
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "read:user user:email"},
    )


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------

@oauth_bp.get("/login/<provider>")
def oauth_login(provider: str):
    if provider not in ("google", "github"):
        flash("Provider OAuth inválido.", "danger")
        return redirect(url_for("auth.login"))

    client = oauth.create_client(provider)
    if client is None:
        flash("OAuth não configurado para este provider.", "danger")
        return redirect(url_for("auth.login"))

    redirect_uri = url_for("oauth.oauth_callback", provider=provider, _external=True)
    return client.authorize_redirect(redirect_uri)


@oauth_bp.get("/callback/<provider>")
def oauth_callback(provider: str):
    if provider not in ("google", "github"):
        flash("Provider OAuth inválido.", "danger")
        return redirect(url_for("auth.login"))

    client = oauth.create_client(provider)
    if client is None:
        flash("OAuth não configurado.", "danger")
        return redirect(url_for("auth.login"))

    try:
        token = client.authorize_access_token()
    except Exception:
        logger.exception("Falha ao trocar code por token OAuth (%s)", provider)
        flash("Autenticação cancelada ou expirada. Tente novamente.", "warning")
        return redirect(url_for("auth.login"))

    # Extrai dados do usuário do provider
    provider_user_id, email, name = _extract_user_info(provider, client, token)

    if not email:
        flash("Não foi possível obter o e-mail da sua conta. Verifique as permissões.", "danger")
        return redirect(url_for("auth.login"))

    user = _get_or_create_user(provider, provider_user_id, email, name)
    login_user(user)
    return redirect(url_for("main.dashboard"))


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------

def _extract_user_info(
    provider: str, client, token: dict
) -> tuple[str, str | None, str | None]:
    """Retorna (provider_user_id, email, name) para cada provider."""
    if provider == "google":
        userinfo = token.get("userinfo") or client.userinfo()
        provider_user_id = str(userinfo["sub"])
        email = userinfo.get("email")
        name = userinfo.get("name")
        return provider_user_id, email, name

    if provider == "github":
        resp = client.get("user", token=token)
        data = resp.json()
        provider_user_id = str(data["id"])
        name = data.get("name") or data.get("login")
        email = data.get("email")

        # GitHub pode omitir o e-mail público — busca na endpoint de emails
        if not email:
            emails_resp = client.get("user/emails", token=token)
            for entry in emails_resp.json():
                if entry.get("primary") and entry.get("verified"):
                    email = entry["email"]
                    break

        return provider_user_id, email, name

    return "", None, None


def _get_or_create_user(
    provider: str, provider_user_id: str, email: str, name: str | None
) -> User:
    """
    Busca ou cria um User local com base nas credenciais OAuth.

    Ordem de resolução:
      1. OAuthAccount existente → retorna user vinculado
      2. User com mesmo e-mail → vincula OAuthAccount, retorna user
      3. Nenhum → cria User + OAuthAccount
    """
    # 1. OAuthAccount já existe
    account = db.session.scalar(
        db.select(OAuthAccount).filter_by(
            provider=provider, provider_user_id=provider_user_id
        )
    )
    if account:
        return account.user

    # 2. Usuário com mesmo e-mail já existe — vincula silenciosamente
    email_lower = email.strip().lower()
    user = db.session.scalar(db.select(User).filter_by(email=email_lower))

    if user:
        new_account = OAuthAccount(
            user_id=user.id,
            provider=provider,
            provider_user_id=provider_user_id,
        )
        db.session.add(new_account)
        # Garante que a conta esteja confirmada (pode ter sido criada sem confirmar)
        user.confirmed = True
        db.session.commit()
        return user

    # 3. Novo usuário
    user = User(
        email=email_lower,
        name=name or email_lower.split("@")[0],
        confirmed=True,         # OAuth garante que o e-mail foi verificado pelo provider
        password_hash=None,     # sem senha local
    )
    db.session.add(user)
    db.session.flush()          # obtém user.id antes do commit

    new_account = OAuthAccount(
        user_id=user.id,
        provider=provider,
        provider_user_id=provider_user_id,
    )
    db.session.add(new_account)
    db.session.commit()
    return user
