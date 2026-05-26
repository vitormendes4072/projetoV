# app/models/margin_alert_log.py
from __future__ import annotations

from datetime import datetime, timezone

from app import db


class MarginAlertLog(db.Model):
    """Registro de alertas de margem enviados.

    Dedupe por (user_id, product_id, alert_date) — no máximo 1 alerta por
    produto por dia, independentemente de quantas vezes o cron rodar.
    """

    __tablename__ = "margin_alert_log"

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

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Data em que o alerta foi (ou deveria ter sido) enviado
    alert_date = db.Column(db.Date, nullable=False, index=True)

    # Margem registrada no momento do alerta (para histórico/debug)
    margin_value = db.Column(db.Numeric(7, 2), nullable=True)

    sent_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "product_id",
            "alert_date",
            name="uq_margin_alert_dedupe",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<MarginAlertLog user_id={self.user_id} "
            f"product_id={self.product_id} alert_date={self.alert_date}>"
        )
