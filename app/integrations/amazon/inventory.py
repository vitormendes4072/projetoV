# app/services/amazon_inventory.py

from app import db
from app.models import AmazonSkuLink, AmazonInventorySnapshot


def get_amazon_stock_by_product(*, user_id: str, product_id: int) -> int:
    """
    Soma o estoque FBA (fulfillable_quantity) de todos os SellerSKU
    da Amazon vinculados a um produto interno.
    """
    links = db.session.scalars(
        db.select(AmazonSkuLink).filter_by(user_id=user_id, product_id=product_id)
    ).all()

    total = 0

    for link in links:
        snap = db.session.scalar(
            db.select(AmazonInventorySnapshot)
            .filter_by(user_id=user_id, seller_sku=link.amazon_seller_sku)
            .order_by(AmazonInventorySnapshot.updated_at.desc())
        )

        if snap and snap.fulfillable_qty:
            total += snap.fulfillable_qty

    return total
