# config.py
import os
from dotenv import load_dotenv

# Carrega variáveis do .env (útil para dev local)
load_dotenv()

SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "").replace("postgres://", "postgresql://")


class Config:

    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER") or os.environ.get("MAIL_USERNAME")

    """
    Configurações base (comuns a todos os ambientes)
    """
    # ⚠️ Em produção, esta chave DEVE existir.
    # O fallback é apenas para evitar crash em dev.
    SECRET_KEY = os.environ.get("SECRET_KEY") or "voce-esqueceu-de-configurar-a-chave"

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # -------------------------------------------------
    # Flask-Limiter (Rate limit)
    # -------------------------------------------------
    # Em dev: memória
    # Em prod: Redis (se REDIS_URL existir)
    RATELIMIT_STORAGE_URI = os.environ.get("REDIS_URL", "memory://")
    RATELIMIT_DEFAULT = "200 per day;50 per hour"

    # -------------------------------------------------
    # Email (Flask-Mail)
    # -------------------------------------------------
    MAIL_SERVER = os.environ.get("MAIL_SERVER")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USE_SSL = os.environ.get("MAIL_USE_SSL", "false").lower() == "true"
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")


class DevelopmentConfig(Config):
    """
    Configurações para desenvolvimento local
    """
    DEBUG = True
    SESSION_COOKIE_SECURE = False

    # SQLite local por padrão (não quebra o projeto)
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DATABASE_URL", "")
        .replace("postgres://", "postgresql://")
        or "sqlite:///dev.db"
    )


class ProductionConfig(Config):
    """
    Configurações para produção
    """
    DEBUG = False

    # Em produção, não faz sentido rodar sem banco
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DATABASE_URL", "")
        .replace("postgres://", "postgresql://")
    )

    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_HTTPONLY = True


class TestingConfig(Config):
    TESTING = True
    # URI compartilhada: múltiplas conexões veem o mesmo banco em memória
    SQLALCHEMY_DATABASE_URI = "sqlite:///file:testdb?mode=memory&cache=shared&uri=true"
    SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"check_same_thread": False}}
    WTF_CSRF_ENABLED = False
    MAIL_SUPPRESS_SEND = True
    SECRET_KEY = "test-secret-key"
    RATELIMIT_ENABLED = False


# Mapeamento de ambientes
config_options = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
