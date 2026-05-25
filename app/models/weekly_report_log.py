# app/models/weekly_report_log.py
from __future__ import annotations

from datetime import datetime, timezone

from app import db


class WeeklyReportLog(db.Model):
    """Registro de relatórios semanais de prejuízo enviados.

    Dedupe por (user_id, week_start) — no máximo 1 envio por usuário por semana,
    independentemente de quantas vezes o cron rodar.
    """

    __tablename__ = "weekly_report_log"

    id = db.Column(
        db.BigInteger().with_variant(db.Integer, "sqlite"),
        primary_key=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Segunda-feira da semana reportada (chave de dedupe)
    week_start = db.Column(db.Date, nullable=False, index=True)

    # Quantidade de itens negativos incluídos no relatório
    neg_simulations = db.Column(db.Integer, nullable=False, default=0)
    neg_orders      = db.Column(db.Integer, nullable=False, default=0)

    sent_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "week_start",
            name="uq_weekly_report_dedupe",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<WeeklyReportLog user_id={self.user_id} "
            f"week_start={self.week_start}>"
        )
