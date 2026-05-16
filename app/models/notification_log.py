# app/models/notification_log.py
from datetime import datetime
from app import db


class NotificationLog(db.Model):
    __tablename__ = "notification_log"

    id = db.Column(db.BigInteger, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    custo_fixo_id = db.Column(
        db.BigInteger,
        db.ForeignKey("custos_fixos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # chave real de dedupe: data do vencimento + tipo do alerta
    due_date = db.Column(db.Date, nullable=False, index=True)

    # opcionais (não usados pra dedupe, mas úteis pra filtros/relatórios)
    ano = db.Column(db.Integer, nullable=True)
    mes = db.Column(db.Integer, nullable=True)

    # "due" | "before"
    alert_type = db.Column(db.String(16), nullable=False)

    sent_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "custo_fixo_id",
            "due_date",
            "alert_type",
            name="uq_notification_dedupe",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<NotificationLog user_id={self.user_id} "
            f"custo_fixo_id={self.custo_fixo_id} "
            f"due_date={self.due_date} alert_type={self.alert_type}>"
        )
