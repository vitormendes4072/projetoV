# app/__init__.py
import os
import logging
from flask import Flask, render_template, request, g
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from flask_migrate import Migrate
from flask_smorest import Api
from flask_wtf.csrf import CSRFProtect
from flask_caching import Cache

from config import config_options  # seu dicionário do config.py


db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()
migrate = Migrate()
limiter = Limiter(key_func=get_remote_address)  # storage será definido no create_app
smorest = Api()
csrf = CSRFProtect()
cache = Cache()


def _init_rq(app: Flask) -> None:
    """Registra fila RQ em app.extensions['rq_queue']. Em testes usa fakeredis."""
    from redis import Redis
    from rq import Queue

    if app.testing:
        from fakeredis import FakeRedis
        redis_conn = FakeRedis()
    else:
        redis_url = app.config.get("REDIS_URL", "redis://localhost:6379/0")
        redis_conn = Redis.from_url(redis_url)

    app.extensions["rq_queue"] = Queue("amazon-sync", connection=redis_conn)


def _configure_security(app: Flask) -> None:
    """
    Configura Talisman/CSP com nonces.
    Em debug: desliga CSP/HTTPS forçado para não atrapalhar desenvolvimento.
    Em produção: aplica CSP com nonce único por request em script-src e style-src.
    Os templates usam {{ csp_nonce() }} nos blocos <script> e <style> inline.
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
        Talisman(
            app,
            content_security_policy=csp,
            content_security_policy_nonce_in=["script-src", "style-src"],
        )


def create_app(config_name: str | None = None, test_config: dict | None = None) -> Flask:
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

    # test_config allows conftest.py to inject the real PostgreSQL URI BEFORE
    # db.init_app() creates the engine — Flask-SQLAlchemy creates it eagerly.
    if test_config:
        app.config.update(test_config)

    # Validações obrigatórias em produção (aqui o env já é conhecido)
    if env_name == "production":
        if not os.environ.get("SECRET_KEY"):
            raise RuntimeError("SECRET_KEY não configurada no ambiente de produção.")
        if not os.environ.get("CREDENTIALS_ENCRYPTION_KEY"):
            raise RuntimeError("CREDENTIALS_ENCRYPTION_KEY não configurada em produção.")

    # ---------------------------------------
    # Logging
    # ---------------------------------------
    from app.logging_config import configure_logging  # noqa: PLC0415
    configure_logging(app)

    # ---------------------------------------
    # Extensões
    # ---------------------------------------
    db.init_app(app)
    mail.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    cache.init_app(app)

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
    # API Key — request_loader (X-API-Key header)
    # ---------------------------------------
    @login_manager.request_loader
    def _load_user_from_api_key(req):
        key = req.headers.get("X-API-Key", "").strip()
        if not key:
            return None
        from app.models import User
        return db.session.scalar(db.select(User).filter_by(api_key=key))

    # ---------------------------------------
    # Fila assíncrona (RQ)
    # ---------------------------------------
    _init_rq(app)

    # Relaxa CSP nas rotas do Swagger UI (registrado antes do Talisman para
    # que o after_request execute depois do hook do Talisman — LIFO order).
    @app.after_request
    def _relax_csp_for_swagger(response):
        if request.path.startswith("/api/docs") or request.path == "/api/openapi.json":
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net "
                "https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "img-src 'self' data: https://cdn.jsdelivr.net"
            )
        return response

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
    from app.integrations.amazon import amazon
    from app.commands import register_commands
    from app.api import blp as api_blp
    from app.relatorios.routes import relatorios_bp

    app.register_blueprint(auth)
    app.register_blueprint(main)
    app.register_blueprint(pricing)
    app.register_blueprint(settings_bp)
    app.register_blueprint(produtos_bp)
    app.register_blueprint(financeiro_bp)
    # Rotas de desenvolvimento: importadas ANTES de register_blueprint para que
    # os decoradores @amazon.post() sejam aplicados enquanto o blueprint ainda
    # aceita novas rotas. Em produção as URLs /integrations/amazon/dev/* não existem.
    if app.debug:
        from app.integrations.amazon import routes_dev  # noqa: F401

    app.register_blueprint(amazon)
    app.register_blueprint(relatorios_bp)

    # REST API documentada (Flask-Smorest → Swagger UI em /api/docs)
    smorest.init_app(app)
    smorest.register_blueprint(api_blp)
    csrf.exempt(api_blp)  # API REST usa auth por sessão; Swagger UI não envia CSRF token

    # ---------------------------------------
    # Monitoring (livez / readyz / metrics)
    # ---------------------------------------
    from app.monitoring import init_monitoring
    init_monitoring(app)

    # ---------------------------------------
    # Erros
    # ---------------------------------------
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(429)
    def ratelimit_handler(e):
        return render_template("429.html", error=e), 429

    # ---------------------------------------
    # Demo flag — disponível em g.is_demo para templates e rotas
    # ---------------------------------------
    from app.commands import DEMO_EMAIL as _DEMO_EMAIL

    @app.before_request
    def _set_demo_flag() -> None:
        from flask_login import current_user
        g.is_demo = (
            current_user.is_authenticated
            and current_user.email == _DEMO_EMAIL
        )

    # ---------------------------------------
    # CLI Commands
    # ---------------------------------------
    register_commands(app)

    return app
