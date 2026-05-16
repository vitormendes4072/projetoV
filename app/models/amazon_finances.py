from app import db
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime, timezone

def utcnow():
    return datetime.now(timezone.utc)

class AmazonFinancialEvent(db.Model):
    __tablename__ = "amazon_financial_events"
    __table_args__ = {"schema": "public"}

    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(db.String, nullable=False)

    posted_date = db.Column(db.DateTime(timezone=True), nullable=True)
    event_group_id = db.Column(db.String, nullable=True)
    amazon_order_id = db.Column(db.String, nullable=True)

    event_type = db.Column(db.String, nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=True)
    currency = db.Column(db.String, nullable=True)

    raw_json = db.Column(JSONB, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
