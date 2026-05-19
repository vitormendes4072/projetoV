from app import db
from datetime import datetime, timezone
import sqlalchemy as sa

def utcnow():
    return datetime.now(timezone.utc)

class AmazonFinancialEvent(db.Model):
    __tablename__ = "amazon_financial_events"
    __table_args__ = (
        db.Index(
            "uq_amazon_financial_events_user_fp",
            "user_id",
            "fingerprint",
            unique=True,
            postgresql_where=sa.text("fingerprint IS NOT NULL"),
        ),
        {"schema": "public"},
    )

    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    posted_date = db.Column(db.DateTime(timezone=True), nullable=True)
    event_group_id = db.Column(db.String, nullable=True)
    amazon_order_id = db.Column(db.String, nullable=True)

    event_type = db.Column(db.String, nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=True)
    currency = db.Column(db.String, nullable=True)

    # sha256 truncado (64 chars) de campos estáveis do evento — garante idempotência cross-run
    fingerprint = db.Column(db.String(64), nullable=True)

    raw_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
