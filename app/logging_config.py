# app/logging_config.py
"""Configuração centralizada de logging.

Em produção (APP_ENV=production):
  - Todos os handlers emitem JSON newline-delimited para stdout.
  - Campos fixos: asctime, levelname, name, message.
  - Campos extras passados via extra={...} aparecem automaticamente.
  - request_id (UUID4 curto) é injetado em cada request via before_request.

Em desenvolvimento / testes:
  - Formato texto plano — sem mudança de DX.
  - python-json-logger NÃO é importado para não ser dependência obrigatória
    em ambientes sem o pacote.
"""
from __future__ import annotations

import logging
import sys
import uuid

_NOISY_LOGGERS = (
    "werkzeug",
    "sqlalchemy.engine",
    "sqlalchemy.pool",
    "urllib3",
    "botocore",
)


def _silence_noisy_loggers(level: int = logging.WARNING) -> None:
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(level)


def _install_json_handler(root_logger: logging.Logger, level: int) -> None:
    """Instala JsonFormatter em um StreamHandler para stdout."""
    try:
        from pythonjsonlogger.jsonlogger import JsonFormatter  # type: ignore[import-untyped]
    except ImportError:
        # Fallback seguro: se a lib não estiver instalada, usa texto plano.
        root_logger.setLevel(level)
        if not root_logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(
                logging.Formatter("%(levelname)s %(name)s: %(message)s")
            )
            root_logger.addHandler(handler)
        logging.getLogger(__name__).warning(
            "python-json-logger não instalado — usando texto plano."
        )
        return

    # Formato: inclui os campos que queremos no JSON.
    # pythonjsonlogger 2.0.x extrai campos do fmt string e os coloca no dict JSON.
    fmt = JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
        json_ensure_ascii=False,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(fmt)

    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)


def configure_logging(app) -> None:  # type: ignore[type-arg]
    """Ponto de entrada chamado por create_app().

    Em produção instala JSON handler; em dev/test usa texto plano.
    """
    is_production = app.config.get("ENV") == "production" or (
        not app.debug and not app.testing
    )

    if is_production:
        root = logging.getLogger()
        _install_json_handler(root, logging.INFO)
        _silence_noisy_loggers(logging.WARNING)

        # Injeta request_id em cada requisição HTTP
        @app.before_request
        def _set_request_id() -> None:
            from flask import g, request  # noqa: PLC0415
            g.request_id = request.headers.get(
                "X-Request-ID", uuid.uuid4().hex[:8]
            )

        @app.after_request
        def _add_request_id_header(response):  # type: ignore[type-arg]
            from flask import g  # noqa: PLC0415
            rid = getattr(g, "request_id", None)
            if rid:
                response.headers["X-Request-ID"] = rid
            return response

    else:
        log_level = logging.DEBUG if app.debug else logging.WARNING
        # Definir explicitamente — basicConfig é no-op se handlers já existem (ex: pytest)
        logging.root.setLevel(log_level)
        if not logging.root.handlers:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(
                logging.Formatter("%(levelname)s %(name)s: %(message)s")
            )
            logging.root.addHandler(handler)
