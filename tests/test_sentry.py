# tests/test_sentry.py
"""Testes para app/sentry.py — inicialização condicional do Sentry SDK."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, call, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app(debug: bool = False, testing: bool = False):
    from flask import Flask
    app = Flask(__name__)
    app.config.update(
        DEBUG=debug,
        TESTING=testing,
        SECRET_KEY="test",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        WTF_CSRF_ENABLED=False,
    )
    return app


# ---------------------------------------------------------------------------
# Sem DSN — no-op
# ---------------------------------------------------------------------------

class TestNoSentryDsn:
    def test_no_dsn_sentry_not_called(self):
        """Sem SENTRY_DSN, sentry_sdk.init() nunca é chamado."""
        from app.sentry import init_sentry

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SENTRY_DSN", None)
            with patch("sentry_sdk.init") as mock_init:
                init_sentry(_make_app())

        mock_init.assert_not_called()

    def test_empty_dsn_sentry_not_called(self):
        """DSN vazio (string) também é no-op."""
        from app.sentry import init_sentry

        with patch.dict(os.environ, {"SENTRY_DSN": "  "}, clear=False):
            with patch("sentry_sdk.init") as mock_init:
                init_sentry(_make_app())

        mock_init.assert_not_called()

    def test_app_starts_without_dsn(self, app):
        """A app sobe normalmente mesmo sem SENTRY_DSN configurado."""
        # O fixture app do conftest já sobe sem DSN — se chegou aqui, passou.
        assert app is not None


# ---------------------------------------------------------------------------
# Com DSN — init chamado com parâmetros corretos
# ---------------------------------------------------------------------------

class TestWithSentryDsn:
    def test_init_called_with_dsn(self):
        """Com SENTRY_DSN, sentry_sdk.init() é chamado."""
        from app.sentry import init_sentry

        fake_dsn = "https://key@o123.ingest.sentry.io/456"
        with patch.dict(os.environ, {"SENTRY_DSN": fake_dsn}, clear=False):
            with patch("sentry_sdk.init") as mock_init:
                init_sentry(_make_app())

        mock_init.assert_called_once()
        kwargs = mock_init.call_args.kwargs
        assert kwargs["dsn"] == fake_dsn

    def test_send_default_pii_is_false(self):
        """send_default_pii deve ser False para conformidade LGPD."""
        from app.sentry import init_sentry

        with patch.dict(os.environ, {"SENTRY_DSN": "https://x@o1.sentry.io/1"}):
            with patch("sentry_sdk.init") as mock_init:
                init_sentry(_make_app())

        kwargs = mock_init.call_args.kwargs
        assert kwargs.get("send_default_pii") is False

    def test_traces_sample_rate_is_low(self):
        """traces_sample_rate deve ser ≤ 0.5 para não esgotar cota."""
        from app.sentry import init_sentry

        with patch.dict(os.environ, {"SENTRY_DSN": "https://x@o1.sentry.io/1"}):
            with patch("sentry_sdk.init") as mock_init:
                init_sentry(_make_app())

        rate = mock_init.call_args.kwargs.get("traces_sample_rate", 1.0)
        assert rate <= 0.5, f"traces_sample_rate={rate} muito alto para produção"

    def test_environment_passed_correctly(self):
        """environment deve refletir APP_ENV."""
        from app.sentry import init_sentry

        with patch.dict(os.environ, {
            "SENTRY_DSN": "https://x@o1.sentry.io/1",
            "APP_ENV": "production",
        }):
            with patch("sentry_sdk.init") as mock_init:
                init_sentry(_make_app())

        assert mock_init.call_args.kwargs.get("environment") == "production"

    def test_flask_integration_included(self):
        """FlaskIntegration deve estar na lista de integrações."""
        from sentry_sdk.integrations.flask import FlaskIntegration

        from app.sentry import init_sentry

        with patch.dict(os.environ, {"SENTRY_DSN": "https://x@o1.sentry.io/1"}):
            with patch("sentry_sdk.init") as mock_init:
                init_sentry(_make_app())

        integrations = mock_init.call_args.kwargs.get("integrations", [])
        types = [type(i) for i in integrations]
        assert FlaskIntegration in types

    def test_rq_integration_included(self):
        """RqIntegration deve estar na lista (captura falhas nos jobs)."""
        from sentry_sdk.integrations.rq import RqIntegration

        from app.sentry import init_sentry

        with patch.dict(os.environ, {"SENTRY_DSN": "https://x@o1.sentry.io/1"}):
            with patch("sentry_sdk.init") as mock_init:
                init_sentry(_make_app())

        integrations = mock_init.call_args.kwargs.get("integrations", [])
        types = [type(i) for i in integrations]
        assert RqIntegration in types


# ---------------------------------------------------------------------------
# Fallback sem biblioteca
# ---------------------------------------------------------------------------

def test_missing_sentry_sdk_does_not_crash():
    """Se sentry-sdk não estiver instalado, init_sentry não deve lançar exceção."""
    from app.sentry import init_sentry

    with patch.dict(os.environ, {"SENTRY_DSN": "https://x@o1.sentry.io/1"}):
        with patch.dict(__import__("sys").modules, {
            "sentry_sdk": None,
            "sentry_sdk.integrations": None,
            "sentry_sdk.integrations.flask": None,
            "sentry_sdk.integrations.sqlalchemy": None,
            "sentry_sdk.integrations.rq": None,
        }):
            # Não deve lançar exceção — apenas loga warning
            init_sentry(_make_app())
