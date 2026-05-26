# tests/test_logging_config.py
"""Testes para app/logging_config.py."""
from __future__ import annotations

import json
import logging
import sys
from io import StringIO
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_prod_app():
    """Cria uma app Flask mínima em modo produção para testar o logging."""
    from flask import Flask

    app = Flask(__name__)
    app.config.update(
        TESTING=False,
        DEBUG=False,
        ENV="production",
        SECRET_KEY="test-secret",
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
    )
    return app


def _make_dev_app():
    """Cria uma app Flask mínima em modo desenvolvimento."""
    from flask import Flask

    app = Flask(__name__)
    app.config.update(
        TESTING=False,
        DEBUG=True,
        ENV="development",
        SECRET_KEY="test-secret",
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
    )
    return app


# ---------------------------------------------------------------------------
# Modo produção — JsonFormatter instalado
# ---------------------------------------------------------------------------

class TestProductionLogging:
    def setup_method(self):
        # Salva e reseta o root logger para isolamento entre testes
        self._orig_handlers = logging.root.handlers[:]
        self._orig_level = logging.root.level
        logging.root.handlers.clear()

    def teardown_method(self):
        logging.root.handlers.clear()
        logging.root.handlers.extend(self._orig_handlers)
        logging.root.setLevel(self._orig_level)

    def test_json_handler_installed(self):
        """Em produção, root logger recebe StreamHandler com JsonFormatter."""
        from pythonjsonlogger.jsonlogger import JsonFormatter

        from app.logging_config import _install_json_handler

        root = logging.getLogger()
        _install_json_handler(root, logging.INFO)

        assert len(root.handlers) == 1
        handler = root.handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        assert isinstance(handler.formatter, JsonFormatter)

    def test_json_output_is_valid_json(self):
        """Cada linha emitida deve ser JSON válido."""
        from app.logging_config import _install_json_handler

        buf = StringIO()
        root = logging.getLogger()
        _install_json_handler(root, logging.INFO)
        # Redireciona o handler para nosso buffer
        root.handlers[0].stream = buf

        log = logging.getLogger("test.json_output")
        log.info("mensagem de teste")

        output = buf.getvalue().strip()
        assert output, "Nenhuma saída gerada"
        data = json.loads(output)
        assert isinstance(data, dict)

    def test_json_contains_required_fields(self):
        """JSON deve ter os campos: levelname, name, message."""
        from app.logging_config import _install_json_handler

        buf = StringIO()
        root = logging.getLogger()
        _install_json_handler(root, logging.INFO)
        root.handlers[0].stream = buf

        log = logging.getLogger("test.fields")
        log.warning("campo obrigatório")

        data = json.loads(buf.getvalue().strip())
        assert "message" in data
        assert "levelname" in data
        assert data.get("message") == "campo obrigatório"

    def test_json_includes_extra_kwargs(self):
        """Campos extras passados via extra={} devem aparecer no JSON."""
        from app.logging_config import _install_json_handler

        buf = StringIO()
        root = logging.getLogger()
        _install_json_handler(root, logging.INFO)
        root.handlers[0].stream = buf

        log = logging.getLogger("test.extra")
        log.info("com extra", extra={"user_id": 42, "sync_event": "failure"})

        data = json.loads(buf.getvalue().strip())
        assert data.get("user_id") == 42
        assert data.get("sync_event") == "failure"

    def test_noisy_loggers_silenced(self):
        """Loggers ruidosos devem ficar em WARNING ou acima."""
        from app.logging_config import _silence_noisy_loggers

        _silence_noisy_loggers(logging.WARNING)

        for name in ("werkzeug", "sqlalchemy.engine", "urllib3"):
            assert logging.getLogger(name).level == logging.WARNING

    def test_configure_logging_prod_installs_json(self):
        """configure_logging() em produção instala JsonFormatter."""
        from pythonjsonlogger.jsonlogger import JsonFormatter

        from app.logging_config import configure_logging

        app = _make_prod_app()
        configure_logging(app)

        root = logging.getLogger()
        assert any(
            isinstance(h.formatter, JsonFormatter)
            for h in root.handlers
        ), "Nenhum handler com JsonFormatter encontrado"


# ---------------------------------------------------------------------------
# Modo desenvolvimento — texto plano
# ---------------------------------------------------------------------------

class TestDevelopmentLogging:
    def setup_method(self):
        self._orig_handlers = logging.root.handlers[:]
        self._orig_level = logging.root.level
        logging.root.handlers.clear()

    def teardown_method(self):
        logging.root.handlers.clear()
        logging.root.handlers.extend(self._orig_handlers)
        logging.root.setLevel(self._orig_level)

    def test_configure_logging_dev_no_json_formatter(self):
        """Em dev, NÃO deve instalar JsonFormatter."""
        from pythonjsonlogger.jsonlogger import JsonFormatter

        from app.logging_config import configure_logging

        app = _make_dev_app()
        configure_logging(app)

        root = logging.getLogger()
        has_json = any(
            isinstance(h.formatter, JsonFormatter)
            for h in root.handlers
            if h.formatter is not None
        )
        assert not has_json, "JsonFormatter não deveria estar instalado em dev"

    def test_configure_logging_dev_level_is_debug(self):
        """Em dev (DEBUG=True), o root logger deve ser DEBUG."""
        from app.logging_config import configure_logging

        app = _make_dev_app()
        configure_logging(app)

        assert logging.root.level == logging.DEBUG


# ---------------------------------------------------------------------------
# Fallback sem biblioteca
# ---------------------------------------------------------------------------

def test_fallback_when_library_missing():
    """Se pythonjsonlogger não estiver instalado, usa texto plano sem crash."""
    orig_handlers = logging.root.handlers[:]
    orig_level = logging.root.level
    logging.root.handlers.clear()

    try:
        from app.logging_config import _install_json_handler

        with patch.dict(sys.modules, {"pythonjsonlogger": None, "pythonjsonlogger.jsonlogger": None}):
            # Não deve lançar exceção
            _install_json_handler(logging.getLogger(), logging.INFO)
    finally:
        logging.root.handlers.clear()
        logging.root.handlers.extend(orig_handlers)
        logging.root.setLevel(orig_level)
