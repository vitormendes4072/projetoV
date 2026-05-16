# app/__init__.py
import os
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from flask_migrate import Migrate

from config import config_options  # seu dicionário do config.py


db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()
migrate = Migrate()
limiter = Limiter(key_func=get_remote_address)  # storage será definido no create_app


def _configure_security(app: Flask) -> None:
    """
    Configura Talisman/CSP.
    Em debug: desliga CSP/HTTPS forçado para não atrapalhar desenvolvimento.
    Em produção: aplica CSP.
    """
    csp = {
        "default-src": ["'self'"],
        "script-src": [
            "'self'",
            "https://cdn.jsdelivr.net",
            "https://cdnjs.cloudflare.com",
        ],
        "style-src": [
            "'self'",
            "'unsafe-inline'",
            "https://fonts.googleapis.com",
            "https://cdn.jsdelivr.net",
            "https://cdnjs.cloudflare.com",
        ],
        "font-src": ["'self'", "https://fonts.gstatic.com"],
        "img-src": ["'self'", "data:"],
    }

    if app.debug or app.testing:
        Talisman(app, force_https=False, content_security_policy=None)
    else:
        Talisman(app, content_security_policy=csp)


def create_app(config_name: str | None = None) -> Flask:
    """
    App factory.
    - Usa APP_ENV se definido, senão 'development' (ou 'default' se preferir manter).
    - Não roda db.create_all(); usa Flask-Migrate.
    """
    # Preferir APP_ENV (mais moderno). Mantém fallback para FLASK_ENV por compatibilidade.
    env_name = config_name or os.environ.get("APP_ENV") or os.environ.get("FLASK_ENV") or "development"

    app = Flask(__name__)
    if env_name not in config_options:
        raise RuntimeError(f"Ambiente '{env_name}' inválido. Opções: {list(config_options.keys())}")

    app.config.from_object(config_options[env_name])

    # Validações obrigatórias em produção (aqui o env já é conhecido)
    if env_name == "production":
        if not os.environ.get("SECRET_KEY"):
            raise RuntimeError("SECRET_KEY não configurada no ambiente de produção.")
        if not os.environ.get("CREDENTIALS_ENCRYPTION_KEY"):
            raise RuntimeError("CREDENTIALS_ENCRYPTION_KEY não configurada em produção.")

    # ---------------------------------------
    # Extensões
    # ---------------------------------------
    db.init_app(app)
    mail.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    # garante que todos models sejam carregados antes do migrate
    from app.models import notification_settings, notification_log  # noqa: F401


    # Limiter: em dev usa memória; em prod tente Redis (se existir), senão cai pra memória
    # (ideal: setar REDIS_URL no .env de produção)
    storage_uri = "memory://"
    if not app.debug:
        storage_uri = os.environ.get("REDIS_URL", "memory://")
    limiter.storage_uri = storage_uri
    limiter.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Por favor, faça login para acessar."

    # ---------------------------------------
    # Segurança (Talisman)
    # ---------------------------------------
    _configure_security(app)

    # ---------------------------------------
    # Blueprints
    # ---------------------------------------
    from app.auth.routes import auth
    from app.main.routes import main
    from app.precificacao.routes import pricing
    from app.settings.routes import settings_bp
    from app.produtos.routes import produtos_bp
    from app.financeiro.routes import financeiro_bp
    from app.integrations.amazon.routes import amazon
    from app.commands import register_commands

    app.register_blueprint(auth)
    app.register_blueprint(main)
    app.register_blueprint(pricing)
    app.register_blueprint(settings_bp)
    app.register_blueprint(produtos_bp)
    app.register_blueprint(financeiro_bp)
    app.register_blueprint(amazon)

    # ---------------------------------------
    # Erros
    # ---------------------------------------
    @app.errorhandler(429)
    def ratelimit_handler(e):
        return render_template("429.html", error=e), 429

    # ---------------------------------------
    # CLI Commands
    # ---------------------------------------
    register_commands(app)

    return app
