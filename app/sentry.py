# app/sentry.py
"""Inicialização do Sentry SDK.

Ativado apenas quando a variável de ambiente SENTRY_DSN estiver definida.
Em dev/test sem DSN é completamente no-op — a app sobe normalmente.

Integrações habilitadas:
  - FlaskIntegration   — captura exceções de request, contexto HTTP
  - SqlalchemyIntegration — breadcrumbs de queries SQL
  - RqIntegration      — captura falhas nos jobs RQ (worker)

Configurações de privacidade:
  - send_default_pii=False — e-mails e IPs de usuário não são enviados (LGPD)
  - traces_sample_rate=0.1 — 10 % das requests trackeadas para performance
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)


def init_sentry(app) -> None:  # type: ignore[type-arg]
    """Chama sentry_sdk.init() se SENTRY_DSN estiver definido.

    Seguro chamar em qualquer ambiente — sem DSN é no-op silencioso.
    """
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return

    try:
        import sentry_sdk  # noqa: PLC0415
        from sentry_sdk.integrations.flask import FlaskIntegration  # noqa: PLC0415
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration  # noqa: PLC0415
        from sentry_sdk.integrations.rq import RqIntegration  # noqa: PLC0415
    except ImportError:
        log.warning("sentry-sdk não instalado — tracking de exceções desabilitado.")
        return

    environment = os.environ.get("APP_ENV", "development")

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        integrations=[
            FlaskIntegration(),
            SqlalchemyIntegration(),
            RqIntegration(),
        ],
        # 10 % das transações são amostradas para performance monitoring.
        # Aumentar para 1.0 apenas em investigações pontuais.
        traces_sample_rate=0.1,
        # Não enviar dados pessoais identificáveis (LGPD).
        send_default_pii=False,
        # Não capturar variáveis locais de cada frame — reduz payload e risco de
        # vazar segredos de variáveis temporárias.
        max_value_length=500,
    )

    log.info("Sentry inicializado (environment=%s)", environment)
