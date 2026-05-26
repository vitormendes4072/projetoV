# app/financeiro/reports_weekly.py
"""Relatório semanal de simulações/pedidos com prejuízo.

Lógica:
  - Roda toda segunda-feira (ou sob demanda via CLI).
  - Para cada usuário com e-mail detecta, no período [week_start, run_date]:
      1. Simulações com margem negativa (PricingHistory.margin < 0)
      2. Pedidos reais Amazon com lucro líquido negativo
         (AmazonFinancialEvent ShipmentEventList — só PostgreSQL)
  - Envia e-mail apenas quando há itens negativos.
  - Dedupe via WeeklyReportLog(user_id, week_start) — 1 envio/semana.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from flask import current_app, render_template
from flask_mail import Message
from sqlalchemy.exc import IntegrityError

from app import db, mail
from app.models.user import User
from app.models.pricing import PricingHistory
from app.models.weekly_report_log import WeeklyReportLog
from app.models.notification_recipient import NotificationRecipient


# ---------------------------------------------------------------------------
# Helpers de data
# ---------------------------------------------------------------------------

def _week_start(d: date) -> date:
    """Retorna a segunda-feira da semana de `d`."""
    return d - timedelta(days=d.weekday())


def _normalize_email(s: str) -> str:
    return (s or "").strip().lower()


# ---------------------------------------------------------------------------
# Helpers de destinatários (padrão do projeto)
# ---------------------------------------------------------------------------

def _get_recipient_emails(user: User) -> list[str]:
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


# ---------------------------------------------------------------------------
# Detecção de negativos
# ---------------------------------------------------------------------------

def _negative_simulations(user_id: int, since: date) -> list[SimpleNamespace]:
    """PricingHistory com margin < 0 desde `since`."""
    since_dt = datetime(since.year, since.month, since.day)
    rows = db.session.scalars(
        db.select(PricingHistory)
        .where(
            PricingHistory.user_id == user_id,
            PricingHistory.margin < 0,
            PricingHistory.created_at >= since_dt,
        )
        .order_by(PricingHistory.margin.asc())
    ).all()

    return [
        SimpleNamespace(
            title=r.title or "Sem título",
            margin=float(r.margin),
            net_profit=float(r.net_profit),
            created_at=r.created_at,
        )
        for r in rows
    ]


def _negative_amazon_orders(user_id: int, since: date) -> list[SimpleNamespace]:
    """Pedidos reais Amazon com lucro líquido negativo desde `since`.

    Só consulta quando o dialeto é PostgreSQL — AmazonFinancialEvent usa
    schema="public" que não existe no SQLite.
    Retorna [] silenciosamente em outros dialetos.
    """
    if db.engine.dialect.name != "postgresql":
        return []

    try:
        from app.models.amazon_finances import AmazonFinancialEvent
        from app.models.amazon_sku_link import AmazonSkuLink
        from app.services.profit_calc import extract_net_from_shipment_events

        since_dt = datetime(since.year, since.month, since.day, tzinfo=timezone.utc)
        rows = db.session.scalars(
            db.select(AmazonFinancialEvent).where(
                AmazonFinancialEvent.user_id == user_id,
                AmazonFinancialEvent.event_type == "ShipmentEventList",
                AmazonFinancialEvent.posted_date >= since_dt,
            )
        ).all()

        if not rows:
            return []

        shipment_events = [r.raw_json for r in rows if r.raw_json]
        info = extract_net_from_shipment_events(shipment_events)

        # Produto → custo
        from app.models.product import Product
        skus = list(info["by_sku"].keys())
        cost_map: dict[str, tuple[float, float]] = {}
        for p in db.session.scalars(
            db.select(Product).where(
                Product.user_id == user_id,
                Product.sku.in_(skus),
            )
        ).all():
            cost_map[p.sku] = (float(p.cost or 0), float(p.packaging_cost or 0))

        # Links Amazon SKU → produto
        for lk in db.session.scalars(
            db.select(AmazonSkuLink).where(
                AmazonSkuLink.user_id == user_id,
                AmazonSkuLink.amazon_seller_sku.in_(skus),
            )
        ).all():
            if lk.product and lk.amazon_seller_sku not in cost_map:
                cost_map[lk.amazon_seller_sku] = (
                    float(lk.product.cost or 0),
                    float(lk.product.packaging_cost or 0),
                )

        from app.models.user import User as UserModel
        user_obj = db.session.get(UserModel, user_id)
        tax_rate = float(getattr(user_obj, "default_tax_rate", 0) or 0)

        negative: list[SimpleNamespace] = []
        for sku, v in info["by_sku"].items():
            revenue = float(v["revenue"])
            fees = float(v["fees"])
            qty = float(v["qty"])
            if qty <= 0 or revenue <= 0:
                continue

            net = revenue + fees
            imposto = revenue * (tax_rate / 100.0)
            cost, pack = cost_map.get(sku, (0.0, 0.0))
            lucro = net - imposto - (cost * qty) - (pack * qty)

            if lucro < 0:
                negative.append(
                    SimpleNamespace(
                        sku=sku,
                        revenue=round(revenue, 2),
                        fees=round(fees, 2),
                        net_profit=round(lucro, 2),
                        qty=int(qty),
                    )
                )

        negative.sort(key=lambda x: x.net_profit)
        return negative

    except Exception:
        current_app.logger.warning(
            "weekly_report: falha ao buscar pedidos Amazon para user_id=%s",
            user_id,
            exc_info=True,
        )
        return []


# ---------------------------------------------------------------------------
# Dedupe
# ---------------------------------------------------------------------------

def _already_sent(user_id: int, week_start: date) -> bool:
    return db.session.scalar(
        db.select(WeeklyReportLog).filter_by(
            user_id=user_id,
            week_start=week_start,
        )
    ) is not None


def _mark_sent(
    user_id: int,
    week_start: date,
    neg_simulations: int,
    neg_orders: int,
) -> None:
    row = WeeklyReportLog(
        user_id=user_id,
        week_start=week_start,
        neg_simulations=neg_simulations,
        neg_orders=neg_orders,
        sent_at=datetime.now(timezone.utc),
    )
    db.session.add(row)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------

def send_weekly_loss_report(
    run_date: date | None = None,
    dry_run: bool = False,
) -> dict:
    """Envia relatório semanal de prejuízo para todos os usuários.

    Só envia quando há simulações ou pedidos com resultado negativo.
    Dedupe por (user_id, week_start) — no máximo 1 e-mail por semana.
    """
    run_date = run_date or date.today()
    week_start = _week_start(run_date)

    users = db.session.scalars(db.select(User)).all()

    summary: dict = {
        "run_date":           run_date.isoformat(),
        "week_start":         week_start.isoformat(),
        "users_total":        len(users),
        "emails_sent":        0,
        "skipped_no_negatives":  0,
        "skipped_already_sent":  0,
        "skipped_missing_email": 0,
        "dry_run":            dry_run,
    }

    for user in users:
        if not user.email:
            summary["skipped_missing_email"] += 1
            continue

        if _already_sent(user.id, week_start):
            summary["skipped_already_sent"] += 1
            continue

        neg_sims   = _negative_simulations(user.id, week_start)
        neg_orders = _negative_amazon_orders(user.id, week_start)

        if not neg_sims and not neg_orders:
            summary["skipped_no_negatives"] += 1
            continue

        subject = (
            f"[VENTREGAZ] Relatório semanal de prejuízo — "
            f"semana de {week_start.strftime('%d/%m')}"
        )
        ctx = {
            "user_name":   user.name or user.email,
            "week_start":  week_start.strftime("%d/%m/%Y"),
            "run_date":    run_date.strftime("%d/%m/%Y"),
            "neg_sims":    neg_sims,
            "neg_orders":  neg_orders,
        }
        recipient_emails = _get_recipient_emails(user)

        if dry_run:
            current_app.logger.info(
                "DRY RUN weekly_report: enviaria para %s "
                "(sims=%s pedidos=%s) recipients=%s",
                user.email,
                len(neg_sims),
                len(neg_orders),
                recipient_emails,
            )
            continue

        msg = Message(subject=subject, recipients=recipient_emails)
        msg.body = render_template("emails/weekly_report.txt", **ctx)
        try:
            msg.html = render_template("emails/weekly_report.html", **ctx)
        except Exception:
            msg.html = None

        mail.send(msg)
        summary["emails_sent"] += 1

        _mark_sent(user.id, week_start, len(neg_sims), len(neg_orders))

    return summary
