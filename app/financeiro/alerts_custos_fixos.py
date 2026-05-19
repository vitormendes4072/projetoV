# app/financeiro/alerts_custos_fixos.py
from __future__ import annotations

from datetime import date, datetime
import calendar
from decimal import Decimal

from flask import current_app, render_template
from flask_mail import Message
from sqlalchemy.exc import IntegrityError

from app import db, mail
from app.models.user import User
from app.models.custo_fixo import CustoFixo
from app.models.custo_fixo_pagamento import CustoFixoPagamento
from app.models.notification_settings import NotificationSettings
from app.models.notification_log import NotificationLog
from app.models.notification_recipient import NotificationRecipient


# ----------------------------
# Helpers de data / formatação
# ----------------------------

def _safe_due_date(year: int, month: int, day: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    day = min(int(day), last_day)
    return date(year, month, day)


def _next_month(y: int, m: int) -> tuple[int, int]:
    m += 1
    if m == 13:
        return y + 1, 1
    return y, m


def _compute_next_due_date(run_day: date, dia_pagamento: int) -> date:
    """
    Próximo vencimento real considerando run_day:
    - se vencimento do mês atual ainda não passou (>= run_day), usa ele
    - se já passou, usa o do próximo mês
    """
    y, m = run_day.year, run_day.month
    due = _safe_due_date(y, m, dia_pagamento)
    if due < run_day:
        y2, m2 = _next_month(y, m)
        due = _safe_due_date(y2, m2, dia_pagamento)
    return due


def _fmt_brl(v) -> str:
    try:
        x = Decimal(str(v or "0"))
    except Exception:
        x = Decimal("0")
    s = f"{x:.2f}"
    return s.replace(".", ",")


def _normalize_email(s: str) -> str:
    return (s or "").strip().lower()


# ----------------------------
# Helpers de dedupe do envio
# ----------------------------

def _has_been_sent(user_id: int, custo_fixo_id: int, due_date: date, alert_type: str) -> bool:
    return db.session.scalar(
        db.select(NotificationLog).filter_by(
            user_id=user_id,
            custo_fixo_id=custo_fixo_id,
            due_date=due_date,
            alert_type=alert_type,
        )
    ) is not None


def _mark_sent_nocommit(
    user_id: int,
    custo_fixo_id: int,
    due_date: date,
    alert_type: str,
    *,
    ano: int | None = None,
    mes: int | None = None,
) -> None:
    """
    Só adiciona o registro no session. O commit é feito em lote.
    Dedupe: (user_id, custo_fixo_id, due_date, alert_type)
    """
    row = NotificationLog(
        user_id=user_id,
        custo_fixo_id=custo_fixo_id,
        due_date=due_date,
        alert_type=alert_type,
        ano=ano,
        mes=mes,
        sent_at=datetime.utcnow(),
    )
    db.session.add(row)


def _get_recipient_emails_for_user(user: User) -> list[str]:
    """
    Retorna a lista de destinatários ativos do usuário.
    Se estiver vazia, retorna [user.email] como fallback.
    Deduplica e normaliza.
    """
    recipients = db.session.scalars(
        db.select(NotificationRecipient)
        .filter_by(user_id=user.id, enabled=True)
        .order_by(NotificationRecipient.created_at.asc())
    ).all()

    emails: list[str] = []
    seen = set()

    for r in recipients:
        e = _normalize_email(r.email)
        if not e:
            continue
        if "@" not in e or "." not in e:
            # validação simples (sem regex pesada)
            continue
        if e in seen:
            continue
        seen.add(e)
        emails.append(e)

    if not emails:
        # fallback pro email principal do usuário
        emails = [_normalize_email(user.email)]

    return emails


# ----------------------------
# Função principal
# ----------------------------

def send_custos_fixos_alerts_for_day(run_day: date | None = None, dry_run: bool = False) -> dict:
    """
    Envia alertas de custos fixos (antes do vencimento e/ou no vencimento),
    respeitando NotificationSettings e evitando duplicar envios via NotificationLog.

    Dedupe por due_date (data real do vencimento) + alert_type.
    """
    run_day = run_day or date.today()
    ano, mes = run_day.year, run_day.month

    users = db.session.scalars(db.select(User)).all()

    summary: dict = {
        "date": run_day.isoformat(),
        "users_total": len(users),

        # emails_sent = quantidade de envios (um send = um e-mail com N recipients)
        "emails_sent": 0,

        # alerts_sent = quantidade de alertas marcados no log (due/before por item)
        "alerts_sent": 0,

        "skipped_paid": 0,
        "skipped_no_due": 0,
        "skipped_not_vigente": 0,
        "skipped_inactive": 0,
        "skipped_disabled": 0,
        "skipped_mode_none": 0,
        "skipped_missing_email": 0,
        "skipped_already_sent_due": 0,
        "skipped_already_sent_before": 0,
        "dry_run": dry_run,
    }

    for user in users:
        if not user.email:
            summary["skipped_missing_email"] += 1
            continue

        settings = db.session.scalar(db.select(NotificationSettings).filter_by(user_id=user.id))
        if not settings:
            settings = NotificationSettings(user_id=user.id)
            db.session.add(settings)
            db.session.commit()

        if not settings.enabled:
            summary["skipped_disabled"] += 1
            continue

        if settings.alert_mode == "none":
            summary["skipped_mode_none"] += 1
            continue

        days_before = int(settings.days_before or 3)
        days_before = max(1, min(10, days_before))

        itens = db.session.scalars(db.select(CustoFixo).filter_by(user_id=user.id)).all()

        # pagos do mês corrente (controle mensal)
        pagos = db.session.scalars(
            db.select(CustoFixoPagamento)
            .join(CustoFixo, CustoFixoPagamento.custo_fixo_id == CustoFixo.id)
            .where(CustoFixo.user_id == user.id,
                   CustoFixoPagamento.ano == ano,
                   CustoFixoPagamento.mes == mes)
        ).all()
        pagos_ids = {p.custo_fixo_id for p in pagos}

        due_alerts: list[tuple[CustoFixo, date]] = []
        before_alerts: list[tuple[CustoFixo, date]] = []

        for item in itens:
            if not item.ativo:
                summary["skipped_inactive"] += 1
                continue

            if not item.vigente_em(ano, mes):
                summary["skipped_not_vigente"] += 1
                continue

            if not item.dia_pagamento:
                summary["skipped_no_due"] += 1
                continue

            if item.id in pagos_ids:
                summary["skipped_paid"] += 1
                continue

            due_date = _compute_next_due_date(run_day, int(item.dia_pagamento))
            delta_days = (due_date - run_day).days

            # alerta no dia
            if delta_days == 0 and settings.alert_mode in ("due_only", "before_and_due"):
                if _has_been_sent(user.id, item.id, due_date, "due"):
                    summary["skipped_already_sent_due"] += 1
                else:
                    due_alerts.append((item, due_date))

            # alerta antes
            if settings.alert_mode == "before_and_due" and delta_days == days_before:
                if _has_been_sent(user.id, item.id, due_date, "before"):
                    summary["skipped_already_sent_before"] += 1
                else:
                    before_alerts.append((item, due_date))

        if not due_alerts and not before_alerts:
            continue

        subject_parts: list[str] = []
        if due_alerts:
            subject_parts.append(f"{len(due_alerts)} vencendo hoje")
        if before_alerts:
            subject_parts.append(f"{len(before_alerts)} vencendo em {days_before} dia(s)")
        subject = f"[VENTREGAZ] Alertas de custos fixos — {' | '.join(subject_parts)}"

        def _row(item: CustoFixo, d: date) -> dict:
            return {
                "id": item.id,
                "nome": item.nome,
                "categoria": item.categoria,
                "valor_mensal": _fmt_brl(item.valor_mensal),
                "dia_pagamento": item.dia_pagamento,
                "vencimento": d.strftime("%d/%m/%Y"),
            }

        ctx = {
            "user_name": user.name or user.email,
            "run_day": run_day.strftime("%d/%m/%Y"),
            "days_before": days_before,
            "due_items": [_row(i, d) for (i, d) in due_alerts],
            "before_items": [_row(i, d) for (i, d) in before_alerts],
        }

        recipient_emails = _get_recipient_emails_for_user(user)

        if dry_run:
            current_app.logger.info(
                "DRY RUN: enviaria para %s: due=%s before=%s recipients=%s",
                user.email,
                len(due_alerts),
                len(before_alerts),
                recipient_emails,
            )
            continue

        # 1) Envia e-mail (1 envio, N recipients)
        msg = Message(subject=subject, recipients=recipient_emails)
        msg.body = render_template("emails/custos_fixos_alerta.txt", **ctx)

        try:
            msg.html = render_template("emails/custos_fixos_alerta.html", **ctx)
        except Exception:
            msg.html = None

        mail.send(msg)
        summary["emails_sent"] += 1

        # 2) Marca logs em lote (1 commit)
        to_mark: list[tuple[int, date, str]] = []
        for item, d in due_alerts:
            to_mark.append((item.id, d, "due"))
        for item, d in before_alerts:
            to_mark.append((item.id, d, "before"))

        sent_count = 0
        try:
            for custo_id, d, t in to_mark:
                _mark_sent_nocommit(user.id, custo_id, d, t, ano=ano, mes=mes)
            db.session.commit()
            sent_count = len(to_mark)
        except IntegrityError:
            # se bater duplicidade por corrida/executou duas vezes, tenta individual
            db.session.rollback()
            for custo_id, d, t in to_mark:
                try:
                    _mark_sent_nocommit(user.id, custo_id, d, t, ano=ano, mes=mes)
                    db.session.commit()
                    sent_count += 1
                except IntegrityError:
                    db.session.rollback()

        summary["alerts_sent"] += sent_count

    return summary
