# app/financeiro/alerts_margin.py
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from flask import current_app, render_template
from flask_mail import Message
from sqlalchemy.exc import IntegrityError

from app import db, mail
from app.models.user import User
from app.models.product import Product
from app.models.pricing import PricingHistory
from app.models.margin_alert_log import MarginAlertLog
from app.models.notification_recipient import NotificationRecipient


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _normalize_email(s: str) -> str:
    return (s or "").strip().lower()


def _get_recipient_emails(user: User) -> list[str]:
    """Destinatários ativos do usuário; fallback para user.email."""
    recipients = db.session.scalars(
        db.select(NotificationRecipient)
        .filter_by(user_id=user.id, enabled=True)
        .order_by(NotificationRecipient.created_at.asc())
    ).all()

    emails: list[str] = []
    seen: set[str] = set()
    for r in recipients:
        e = _normalize_email(r.email)
        if not e or "@" not in e or "." not in e or e in seen:
            continue
        seen.add(e)
        emails.append(e)

    return emails or [_normalize_email(user.email)]


def _already_sent(user_id: int, product_id: int, alert_date: date) -> bool:
    return db.session.scalar(
        db.select(MarginAlertLog).filter_by(
            user_id=user_id,
            product_id=product_id,
            alert_date=alert_date,
        )
    ) is not None


def _mark_sent(
    user_id: int,
    product_id: int,
    alert_date: date,
    margin_value: Decimal | float | None,
) -> None:
    """Registra o envio; ignora IntegrityError (corrida de processos)."""
    row = MarginAlertLog(
        user_id=user_id,
        product_id=product_id,
        alert_date=alert_date,
        margin_value=margin_value,
        sent_at=datetime.now(timezone.utc),
    )
    db.session.add(row)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()


def _latest_margin(product_id: int) -> Decimal | None:
    """Retorna a margem da simulação mais recente vinculada ao produto."""
    row = db.session.scalar(
        db.select(PricingHistory)
        .where(PricingHistory.product_id == product_id)
        .order_by(PricingHistory.created_at.desc())
        .limit(1)
    )
    return row.margin if row is not None else None


def _products_with_threshold(user_id: int) -> list[Product]:
    """Produtos do usuário que têm threshold de margem configurado."""
    return db.session.scalars(
        db.select(Product).where(
            Product.user_id == user_id,
            Product.margin_alert_threshold.is_not(None),
        )
    ).all()


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------

def send_margin_alerts(run_day: date | None = None, dry_run: bool = False) -> dict:
    """Envia alertas de margem baixa para todos os usuários.

    Para cada produto com ``margin_alert_threshold`` definido:
    - Obtém a margem da última simulação vinculada (``PricingHistory.product_id``).
    - Se ``margin < threshold`` e ainda não enviou hoje → envia e-mail.

    Dedupe via ``MarginAlertLog(user_id, product_id, alert_date)``.
    """
    run_day = run_day or date.today()

    users = db.session.scalars(db.select(User)).all()

    summary: dict = {
        "date": run_day.isoformat(),
        "users_total": len(users),
        "emails_sent": 0,
        "alerts_sent": 0,
        "skipped_no_threshold": 0,
        "skipped_no_simulation": 0,
        "skipped_above_threshold": 0,
        "skipped_already_sent": 0,
        "skipped_missing_email": 0,
        "dry_run": dry_run,
    }

    for user in users:
        if not user.email:
            summary["skipped_missing_email"] += 1
            continue

        products = _products_with_threshold(user.id)
        if not products:
            summary["skipped_no_threshold"] += len(
                db.session.scalars(
                    db.select(Product).where(Product.user_id == user.id)
                ).all()
            )
            continue

        breach_products: list[dict] = []

        for product in products:
            margin = _latest_margin(product.id)

            if margin is None:
                summary["skipped_no_simulation"] += 1
                continue

            threshold = Decimal(str(product.margin_alert_threshold))

            if Decimal(str(margin)) >= threshold:
                summary["skipped_above_threshold"] += 1
                continue

            if _already_sent(user.id, product.id, run_day):
                summary["skipped_already_sent"] += 1
                continue

            breach_products.append(
                {
                    "id": product.id,
                    "name": product.name,
                    "sku": product.sku,
                    "threshold": float(threshold),
                    "margin": float(margin),
                }
            )

        if not breach_products:
            continue

        subject = (
            f"[VENTREGAZ] Alerta de margem baixa — "
            f"{len(breach_products)} produto(s) abaixo do limite"
        )
        ctx = {
            "user_name": user.name or user.email,
            "run_day": run_day.strftime("%d/%m/%Y"),
            "products": breach_products,
        }
        recipient_emails = _get_recipient_emails(user)

        if dry_run:
            current_app.logger.info(
                "DRY RUN: enviaria para %s: %s produto(s) com margem baixa %s",
                user.email,
                len(breach_products),
                [p["sku"] for p in breach_products],
            )
            continue

        msg = Message(subject=subject, recipients=recipient_emails)
        msg.body = render_template("emails/margin_alerta.txt", **ctx)
        try:
            msg.html = render_template("emails/margin_alerta.html", **ctx)
        except Exception:
            msg.html = None

        mail.send(msg)
        summary["emails_sent"] += 1

        for p in breach_products:
            _mark_sent(user.id, p["id"], run_day, p["margin"])
            summary["alerts_sent"] += 1

    return summary
