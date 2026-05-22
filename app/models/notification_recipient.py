# app/models/notification_recipient.py
from datetime import datetime, timezone
from app import db

class NotificationRecipient(db.Model):
    __tablename__ = "notification_recipients"

    id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    email = db.Column(db.String(255), nullable=False)
    enabled = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        # não deixa cadastrar o mesmo email duas vezes pro mesmo user
        db.UniqueConstraint("user_id", "email", name="uq_recipient_user_email"),
        db.Index("ix_recipients_user_enabled", "user_id", "enabled"),
    )

    def __repr__(self) -> str:
        return f"<NotificationRecipient user_id={self.user_id} email={self.email} enabled={self.enabled}>"
