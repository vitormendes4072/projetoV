# app/models/amazon.py
from app import db
from sqlalchemy import Uuid
from datetime import datetime, timezone
import uuid

from app.utils.crypto import encrypt, decrypt

class AmazonConnection(db.Model):
    __tablename__ = "amazon_connections"
    __table_args__ = {"schema": "public"}  # <- força schema certo

    id = db.Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)

    marketplace_id = db.Column(db.String, nullable=False)
    seller_id = db.Column(db.String, nullable=True)

    lwa_client_id = db.Column(db.String, nullable=False)
    lwa_client_secret_enc = db.Column(db.Text, nullable=True)
    lwa_refresh_token_enc = db.Column(db.Text, nullable=True)

    aws_access_key_id = db.Column(db.String, nullable=False)
    aws_secret_access_key_enc = db.Column(db.Text, nullable=True)
    aws_region = db.Column(db.String, nullable=False, default="us-east-1")
    role_arn = db.Column(db.String, nullable=True)

    last_sync_at = db.Column(db.DateTime(timezone=True), nullable=True)

    @property
    def lwa_client_secret(self) -> str | None:
        return decrypt(self.lwa_client_secret_enc)

    @lwa_client_secret.setter
    def lwa_client_secret(self, value: str | None) -> None:
        self.lwa_client_secret_enc = encrypt(value)

    @property
    def lwa_refresh_token(self) -> str | None:
        return decrypt(self.lwa_refresh_token_enc)

    @lwa_refresh_token.setter
    def lwa_refresh_token(self, value: str | None) -> None:
        self.lwa_refresh_token_enc = encrypt(value)

    @property
    def aws_secret_access_key(self) -> str | None:
        return decrypt(self.aws_secret_access_key_enc)

    @aws_secret_access_key.setter
    def aws_secret_access_key(self, value: str | None) -> None:
        self.aws_secret_access_key_enc = encrypt(value)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class AmazonOrder(db.Model):
    __tablename__ = "amazon_orders"
    __table_args__ = (
        db.UniqueConstraint("user_id", "amazon_order_id", name="uq_amazon_orders_user_order"),
        {"schema": "public"},
    )

    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    amazon_order_id = db.Column(db.String, nullable=False, index=True)
    marketplace_id = db.Column(db.String, nullable=False)

    purchase_date = db.Column(db.DateTime(timezone=True), nullable=True)
    order_status = db.Column(db.String, nullable=True)

    currency = db.Column(db.String, nullable=True)
    order_total_amount = db.Column(db.Numeric(12, 2), nullable=True)

    raw_json = db.Column(db.JSON, nullable=False, default=dict)

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class AmazonOrderItem(db.Model):
    __tablename__ = "amazon_order_items"
    __table_args__ = {"schema": "public"}
    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    amazon_order_id = db.Column(db.String, nullable=False, index=True)
    seller_sku = db.Column(db.String, nullable=True)
    asin = db.Column(db.String, nullable=True)
    quantity = db.Column(db.Integer, nullable=True)

    item_price = db.Column(db.Numeric(12, 2), nullable=True)
    currency = db.Column(db.String, nullable=True)

    raw_json = db.Column(db.JSON, nullable=False, default=dict)

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


