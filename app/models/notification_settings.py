from app import db

class NotificationSettings(db.Model):
    __tablename__ = "notification_settings"

    id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)

    # none | due_only | before_and_due
    alert_mode = db.Column(db.String(32), nullable=False, default="before_and_due")

    # quantos dias antes do vencimento
    days_before = db.Column(db.Integer, nullable=False, default=3)

    enabled = db.Column(db.Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<NotificationSettings user_id={self.user_id} enabled={self.enabled} mode={self.alert_mode} days_before={self.days_before}>"
