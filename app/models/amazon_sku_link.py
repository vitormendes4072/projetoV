from app import db
from datetime import datetime

class AmazonSkuLink(db.Model):
    __tablename__ = "amazon_sku_links"
    __table_args__ = {"schema": "public"}

    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    marketplace_id = db.Column(db.String, nullable=True)
    amazon_seller_sku = db.Column(db.String, nullable=False)
    asin = db.Column(db.String, nullable=True)

    product_id = db.Column(db.BigInteger, db.ForeignKey("products.id"), nullable=False)
    product = db.relationship("Product")

    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
