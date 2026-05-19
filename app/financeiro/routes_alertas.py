from __future__ import annotations

import re

from flask import request, redirect, url_for, flash, jsonify, render_template
from flask_login import login_required, current_user

from app import db
from app.models.notification_settings import NotificationSettings
from app.models.notification_recipient import NotificationRecipient

from app.financeiro.routes_custos import financeiro_bp


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _norm_email(s: str) -> str:
    return (s or "").strip().lower()


@financeiro_bp.route("/alertas", methods=["GET", "POST"])
@login_required
def alertas():
    settings = db.session.scalar(db.select(NotificationSettings).filter_by(user_id=current_user.id))
    if not settings:
        settings = NotificationSettings(user_id=current_user.id)
        db.session.add(settings)
        db.session.commit()

    if request.method == "POST":
        alert_mode = (request.form.get("alert_mode") or "before_and_due").strip()
        days_before_raw = (request.form.get("days_before") or "").strip()

        allowed_modes = {"none", "due_only", "before_and_due"}
        if alert_mode not in allowed_modes:
            flash("Modo de alerta inválido.", "danger")
            return redirect(url_for("financeiro.alertas"))

        days_before = settings.days_before or 3

        if alert_mode == "before_and_due":
            try:
                days_before = int(days_before_raw or days_before)
                days_before = max(1, min(10, days_before))
            except Exception:
                flash("Dias antes inválido. Use um número de 1 a 10.", "danger")
                return redirect(url_for("financeiro.alertas"))

        settings.alert_mode = alert_mode
        settings.days_before = days_before
        db.session.commit()
        flash("Configuração de alertas atualizada.", "success")
        return redirect(url_for("financeiro.alertas"))

    recipients = db.session.scalars(
        db.select(NotificationRecipient)
        .filter_by(user_id=current_user.id)
        .order_by(NotificationRecipient.created_at.asc())
    ).all()

    return render_template("financeiro/alertas.html", settings=settings, recipients=recipients)


@financeiro_bp.route("/alertas/enabled", methods=["POST"])
@login_required
def alertas_enabled():
    settings = db.session.scalar(db.select(NotificationSettings).filter_by(user_id=current_user.id))
    if not settings:
        settings = NotificationSettings(user_id=current_user.id)
        db.session.add(settings)
        db.session.commit()

    enabled_raw = (request.form.get("enabled") or "").lower().strip()
    settings.enabled = enabled_raw in ("1", "true", "on", "yes")
    db.session.commit()
    return jsonify({"ok": True, "enabled": settings.enabled})


@financeiro_bp.route("/alertas/recipients", methods=["POST"])
@login_required
def alertas_recipients_add():
    email = _norm_email(request.form.get("email") or "")
    if not _EMAIL_RE.match(email):
        return jsonify({"ok": False, "error": "Email inválido."}), 400

    row = db.session.scalar(db.select(NotificationRecipient).filter_by(user_id=current_user.id, email=email))
    if row:
        row.enabled = True
    else:
        row = NotificationRecipient(user_id=current_user.id, email=email, enabled=True)
        db.session.add(row)

    db.session.commit()
    return jsonify({"ok": True, "id": int(row.id), "email": row.email, "enabled": bool(row.enabled)})


@financeiro_bp.route("/alertas/recipients/<int:rid>/toggle", methods=["POST"])
@login_required
def alertas_recipients_toggle(rid: int):
    row = db.first_or_404(db.select(NotificationRecipient).filter_by(id=rid, user_id=current_user.id))
    enabled_raw = (request.form.get("enabled") or "").lower().strip()
    row.enabled = enabled_raw in ("1", "true", "on", "yes")
    db.session.commit()
    return jsonify({"ok": True, "id": int(row.id), "enabled": bool(row.enabled)})


@financeiro_bp.route("/alertas/recipients/<int:rid>", methods=["DELETE", "POST"])
@login_required
def alertas_recipients_delete(rid: int):
    row = db.first_or_404(db.select(NotificationRecipient).filter_by(id=rid, user_id=current_user.id))
    db.session.delete(row)
    db.session.commit()
    return jsonify({"ok": True})
