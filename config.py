# config.py
import os
from dotenv import load_dotenv

# Carrega variáveis do .env (útil para dev local)
load_dotenv()

SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "").replace("postgres://", "postgresql://")


class Config:
    """Configurações base (comuns a todos os ambientes)."""

    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER") or os.environ.get("MAIL_USERNAME")

    # -------------------------------------------------
    # Flask-Smorest / OpenAPI
    # -------------------------------------------------
    API_TITLE = "VEntregaz API"
    API_VERSION = "v1"
    OPENAPI_VERSION = "3.0.3"
    OPENAPI_URL_PREFIX = "/api"
    OPENAPI_SWAGGER_UI_PATH = "/docs"
    OPENAPI_SWAGGER_UI_URL = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"
    API_SPEC_OPTIONS = {
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key",
                    "description": "Chave de API gerada em Configurações → API Key. Envie no header `X-API-Key: <sua-chave>`.",
                }
            }
        },
        "security": [{"ApiKeyAuth": []}],
    }
    SECRET_KEY = os.environ.get("SECRET_KEY")

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # -------------------------------------------------
    # Flask-Limiter (Rate limit)
    # -------------------------------------------------
    # Em dev: memória
    # Em prod: Redis (se REDIS_URL existir)
    RATELIMIT_STORAGE_URI = os.environ.get("REDIS_URL", "memory://")
    RATELIMIT_DEFAULT = "200 per day;50 per hour"

    # -------------------------------------------------
    # Flask-Caching
    # -------------------------------------------------
    CACHE_DEFAULT_TIMEOUT = 60

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
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-only-nao-usar-em-producao"

    # SQLite local por padrão (não quebra o projeto)
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DATABASE_URL", "")
        .replace("postgres://", "postgresql://")
        or "sqlite:///dev.db"
    )

    CACHE_TYPE = "SimpleCache"


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

    CACHE_TYPE = "RedisCache"
    CACHE_REDIS_URL = os.environ.get("REDIS_URL")

    # -------------------------------------------------
    # SQLAlchemy connection pool (PostgreSQL / Supabase)
    # -------------------------------------------------
    # pool_pre_ping: testa cada conexão com SELECT 1 antes de usar —
    #   essencial com Supabase/PgBouncer que fecha conexões ociosas em ~10 min.
    # pool_recycle: descarta conexões mais antigas que 30 min, complementando
    #   o pre_ping e evitando erros de timeout silenciosos em horários de baixo uso.
    # pool_size / max_overflow: 10 conexões persistentes + 20 em pico de tráfego;
    #   adequado para Gunicorn com 2–4 workers num plano Supabase padrão.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 10,
        "max_overflow": 20,
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }


class TestingConfig(Config):
    TESTING = True
    CACHE_TYPE = "NullCache"
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
