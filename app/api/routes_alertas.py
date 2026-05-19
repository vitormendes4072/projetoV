from flask_login import current_user

from app import db
from app.api import blp
from app.api.schemas import (
    AlertaEnabledBodySchema,
    AlertaEnabledResultSchema,
    AlertaRecipientBodySchema,
    AlertaRecipientResultSchema,
)
from app.models.notification_settings import NotificationSettings
from app.models.notification_recipient import NotificationRecipient


def _get_or_create_settings():
    settings = db.session.scalar(db.select(NotificationSettings).filter_by(user_id=current_user.id))
    if not settings:
        settings = NotificationSettings(user_id=current_user.id)
        db.session.add(settings)
        db.session.commit()
    return settings


@blp.post("/financeiro/alertas/toggle")
@blp.arguments(AlertaEnabledBodySchema, location="json")
@blp.response(200, AlertaEnabledResultSchema, description="Estado atualizado dos alertas")
def api_alertas_toggle(args):
    """Ativa ou desativa os alertas de vencimento de custos fixos."""
    settings = _get_or_create_settings()
    settings.enabled = args["enabled"]
    db.session.commit()
    return {"ok": True, "enabled": bool(settings.enabled)}


@blp.post("/financeiro/alertas/recipients")
@blp.arguments(AlertaRecipientBodySchema, location="json")
@blp.response(201, AlertaRecipientResultSchema, description="Destinatário adicionado ou reativado")
def api_alertas_add_recipient(args):
    """Adiciona um destinatário para receber alertas de vencimento de custos fixos.

    Se o email já existir, reativa o destinatário (sets `enabled=true`).
    """
    email = args["email"].strip().lower()
    row = db.session.scalar(db.select(NotificationRecipient).filter_by(user_id=current_user.id, email=email))
    if row:
        row.enabled = True
    else:
        row = NotificationRecipient(user_id=current_user.id, email=email, enabled=True)
        db.session.add(row)
    db.session.commit()
    return {"ok": True, "id": int(row.id), "email": row.email, "enabled": bool(row.enabled)}, 201
