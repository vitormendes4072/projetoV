# app/notifications/webhook.py
"""Dispatcher de webhooks outbound para Discord, Slack e URLs genéricas.

Eventos suportados
------------------
sync_failure
    Disparado quando um job RQ de sync Amazon lança exceção.
margin_alert
    Disparado quando a margem de um produto cai abaixo do threshold
    configurado (complementar ao e-mail já existente).

Segurança
---------
- Apenas URLs https:// são aceitas.
- Timeout fixo de 5 s em requests.post.
- Exceções do HTTP nunca propagam — são apenas logadas.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

_TIMEOUT = 5  # segundos

# Cores para embeds Discord (decimal)
_COLOR_ERROR   = 15158332   # vermelho
_COLOR_WARNING = 16776960   # amarelo
_COLOR_OK      = 3066993    # verde


# ---------------------------------------------------------------------------
# Detecção de destino e formatação de payload
# ---------------------------------------------------------------------------

def _is_discord(url: str) -> bool:
    return "discord.com/api/webhooks" in url or "discordapp.com/api/webhooks" in url


def _is_slack(url: str) -> bool:
    return "hooks.slack.com" in url


def _discord_payload(title: str, description: str, color: int) -> dict:
    return {
        "embeds": [
            {
                "title": title,
                "description": description,
                "color": color,
                "footer": {"text": "VEntregaz"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ]
    }


def _slack_payload(title: str, description: str) -> dict:
    return {
        "text": f"*{title}*\n{description}",
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{title}*\n{description}"},
            }
        ],
    }


def _generic_payload(event: str, user_id: int, message: str, extra: dict | None = None) -> dict:
    payload: dict[str, Any] = {
        "event":     event,
        "user_id":   user_id,
        "message":   message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        payload.update(extra)
    return payload


# ---------------------------------------------------------------------------
# Dispatcher central
# ---------------------------------------------------------------------------

def dispatch(
    url: str,
    event: str,
    title: str,
    description: str,
    user_id: int,
    color: int = _COLOR_WARNING,
    extra: dict | None = None,
) -> bool:
    """Envia um webhook para `url`. Retorna True em sucesso, False em falha.

    Aceita apenas URLs https://. Timeout de 5 s. Nunca propaga exceções.
    """
    if not url or not url.startswith("https://"):
        log.warning("webhook: URL inválida ou não-HTTPS ignorada: %r", url)
        return False

    try:
        import requests  # noqa: PLC0415

        if _is_discord(url):
            payload = _discord_payload(title, description, color)
        elif _is_slack(url):
            payload = _slack_payload(title, description)
        else:
            payload = _generic_payload(event, user_id, description, extra)

        resp = requests.post(
            url,
            json=payload,
            timeout=_TIMEOUT,
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code >= 400:
            log.warning(
                "webhook: destino retornou HTTP %s para user_id=%s event=%s",
                resp.status_code, user_id, event,
            )
            return False

        log.info("webhook: enviado user_id=%s event=%s status=%s", user_id, event, resp.status_code)
        return True

    except Exception:
        log.warning("webhook: falha ao enviar para user_id=%s event=%s", user_id, event, exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Helpers de evento
# ---------------------------------------------------------------------------

def notify_sync_failure(user_id: int, error_msg: str) -> bool:
    """Notifica falha no sync Amazon (chamado pelos jobs RQ)."""
    from app import db
    from app.models.user import User

    try:
        user = db.session.get(User, user_id)
        if not user or not user.webhook_url:
            return False
    except Exception:
        log.warning("webhook notify_sync_failure: erro ao buscar user_id=%s", user_id, exc_info=True)
        return False

    title       = "⚠️ Falha no Sync Amazon"
    description = (
        f"O sync da Amazon falhou para a conta **{user.email}**.\n"
        f"Erro: `{error_msg[:300]}`"
    )
    return dispatch(
        url=user.webhook_url,
        event="sync_failure",
        title=title,
        description=description,
        user_id=user_id,
        color=_COLOR_ERROR,
        extra={"error": error_msg[:300]},
    )


def notify_margin_alert(user_id: int, products: list[dict]) -> bool:
    """Notifica queda de margem abaixo do threshold (complementar ao e-mail).

    `products` é a lista de dicts com keys: name, sku, margin, threshold.
    """
    from app import db
    from app.models.user import User

    try:
        user = db.session.get(User, user_id)
        if not user or not user.webhook_url:
            return False
    except Exception:
        log.warning("webhook notify_margin_alert: erro ao buscar user_id=%s", user_id, exc_info=True)
        return False

    lines = "\n".join(
        f"• **{p['name']}** ({p['sku']}): {p['margin']:.1f}% < {p['threshold']:.1f}%"
        for p in products
    )
    title       = f"📉 Margem abaixo do limite ({len(products)} produto(s))"
    description = lines or "Nenhum detalhe disponível."

    return dispatch(
        url=user.webhook_url,
        event="margin_alert",
        title=title,
        description=description,
        user_id=user_id,
        color=_COLOR_WARNING,
        extra={"products": products},
    )


def send_test_webhook(url: str, user_id: int) -> bool:
    """Envia payload de teste para validar a URL configurada."""
    return dispatch(
        url=url,
        event="test",
        title="✅ Webhook VEntregaz — Teste",
        description="Webhook configurado com sucesso! Você receberá alertas neste canal.",
        user_id=user_id,
        color=_COLOR_OK,
    )
