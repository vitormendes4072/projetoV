from app import db
from datetime import datetime

class AmazonInventorySnapshot(db.Model):
    __tablename__ = "amazon_inventory_snapshots"
    __table_args__ = {"schema": "public"}

    id = db.Column(db.BigInteger, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    marketplace_id = db.Column(db.String, nullable=False)

    seller_sku = db.Column(db.String, nullable=False)
    asin = db.Column(db.String, nullable=True)

    fulfillable_qty = db.Column(db.Integer, nullable=False, default=0)
    reserved_qty = db.Column(db.Integer, nullable=False, default=0)
    inbound_working_qty = db.Column(db.Integer, nullable=False, default=0)
    inbound_shipped_qty = db.Column(db.Integer, nullable=False, default=0)
    inbound_receiving_qty = db.Column(db.Integer, nullable=False, default=0)

    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
