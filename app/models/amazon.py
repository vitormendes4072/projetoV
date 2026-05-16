# app/models/amazon.py
from app import db
from sqlalchemy import Uuid
from datetime import datetime, timezone
import uuid

def utcnow():
    return datetime.now(timezone.utc)

class AmazonConnection(db.Model):
    __tablename__ = "amazon_connections"
    __table_args__ = {"schema": "public"}  # <- força schema certo

    id = db.Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    user_id = db.Column(db.String, nullable=False, unique=True)

    marketplace_id = db.Column(db.String, nullable=False)
    seller_id = db.Column(db.String, nullable=True)

    lwa_client_id = db.Column(db.String, nullable=False)
    lwa_client_secret = db.Column(db.String, nullable=False)
    lwa_refresh_token = db.Column(db.String, nullable=False)

    aws_access_key_id = db.Column(db.String, nullable=False)
    aws_secret_access_key = db.Column(db.String, nullable=False)
    aws_region = db.Column(db.String, nullable=False, default="us-east-1")
    role_arn = db.Column(db.String, nullable=True)

    last_sync_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class AmazonOrder(db.Model):
    __tablename__ = "amazon_orders"
    __table_args__ = (
        db.UniqueConstraint("user_id", "amazon_order_id", name="uq_amazon_orders_user_order"),
        {"schema": "public"},
    )

    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(db.String, nullable=False)

    amazon_order_id = db.Column(db.String, nullable=False)
    marketplace_id = db.Column(db.String, nullable=False)

    purchase_date = db.Column(db.DateTime(timezone=True), nullable=True)
    order_status = db.Column(db.String, nullable=True)

    currency = db.Column(db.String, nullable=True)
    order_total_amount = db.Column(db.Numeric(12, 2), nullable=True)

    raw_json = db.Column(db.JSON, nullable=False, default=dict)

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AmazonOrderItem(db.Model):
    __tablename__ = "amazon_order_items"
    __table_args__ = {"schema": "public"}
    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(db.String, nullable=False)

    amazon_order_id = db.Column(db.String, nullable=False)
    seller_sku = db.Column(db.String, nullable=True)
    asin = db.Column(db.String, nullable=True)
    quantity = db.Column(db.Integer, nullable=True)

    item_price = db.Column(db.Numeric(12, 2), nullable=True)
    currency = db.Column(db.String, nullable=True)

    raw_json = db.Column(db.JSON, nullable=False, default=dict)

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)


