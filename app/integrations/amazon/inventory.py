# app/services/amazon_inventory.py

from sqlalchemy.orm import joinedload

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


def get_min_stock_map(user_id: int, seller_skus: list[str]) -> dict[str, int]:
    """Retorna {seller_sku: min_stock} para SKUs com produto vinculado via AmazonSkuLink.

    Usa 2 queries fixas — sem N+1:
      1. AmazonSkuLink WHERE user_id AND seller_sku IN (...) com joinedload(product)
      2. (zero — Product já vem eager-loaded)

    SKUs sem link ou sem produto são omitidos; o chamador trata ausência
    como "sem threshold definido".
    """
    if not seller_skus:
        return {}

    links = db.session.scalars(
        db.select(AmazonSkuLink)
        .options(joinedload(AmazonSkuLink.product))
        .filter(
            AmazonSkuLink.user_id == user_id,
            AmazonSkuLink.amazon_seller_sku.in_(seller_skus),
        )
    ).all()

    result: dict[str, int] = {}
    for link in links:
        if link.product and link.product.min_stock is not None:
            result[link.amazon_seller_sku] = link.product.min_stock
    return result
