# app/integrations/amazon/service/inventory.py
"""
Funções de inventário FBA: cliente, listagem e upsert de snapshots.
"""
from .client import _safe_payload, _with_retry, marketplace_from_id, _credentials


def make_inventory_client(conn):
    """Inventories API (FBA Inventory)."""
    from sp_api.api import Inventories
    return Inventories(
        marketplace=marketplace_from_id(conn.marketplace_id),
        credentials=_credentials(conn),
    )


def get_inventory_summaries(conn, marketplace_id: str):
    """Retorna lista de inventory summaries."""
    client = make_inventory_client(conn)

    def call():
        return client.get_inventory_summary_marketplace(
            granularityType="Marketplace",
            granularityId=marketplace_id,
            marketplaceIds=[marketplace_id],
        )

    def call_alt():
        return client.get_inventory_summaries(
            granularityType="Marketplace",
            granularityId=marketplace_id,
            marketplaceIds=[marketplace_id],
        )

    try:
        res = _with_retry(call, ctx="inventories.get_inventory_summary_marketplace")
    except AttributeError:
        res = _with_retry(call_alt, ctx="inventories.get_inventory_summaries")

    payload = _safe_payload(res, "inventories payload")
    return payload.get("inventorySummaries") or payload.get("InventorySummaries") or []


def upsert_inventory_snapshots(user_id: int, marketplace_id: str, summaries: list):
    """
    Faz upsert de AmazonInventorySnapshot.
    Não faz db.session.commit() — responsabilidade do chamador.
    Retorna (inserted, updated).
    """
    from app import db
    from app.models.amazon_inventory import AmazonInventorySnapshot

    inserted = 0
    updated = 0

    for s in summaries:
        seller_sku = (
            s.get("sellerSku") or s.get("SellerSku")
            or s.get("sellerSKU") or s.get("SellerSKU")
        )
        asin = s.get("asin") or s.get("ASIN")

        if not seller_sku:
            continue

        total_qty = s.get("totalQuantity") or s.get("TotalQuantity") or 0
        details = s.get("inventoryDetails") or s.get("InventoryDetails") or {}

        reserved = details.get("reservedQuantity") or details.get("ReservedQuantity") or 0
        inbound_working = details.get("inboundWorkingQuantity") or details.get("InboundWorkingQuantity") or 0
        inbound_shipped = details.get("inboundShippedQuantity") or details.get("InboundShippedQuantity") or 0
        inbound_receiving = details.get("inboundReceivingQuantity") or details.get("InboundReceivingQuantity") or 0

        row = db.session.scalar(
            db.select(AmazonInventorySnapshot).filter_by(user_id=user_id, seller_sku=seller_sku)
        )

        if not row:
            row = AmazonInventorySnapshot(
                user_id=user_id,
                marketplace_id=marketplace_id,
                seller_sku=seller_sku,
            )
            inserted += 1
        else:
            updated += 1

        row.asin = asin
        row.fulfillable_qty = int(total_qty or 0)
        row.reserved_qty = int(reserved or 0)
        row.inbound_working_qty = int(inbound_working or 0)
        row.inbound_shipped_qty = int(inbound_shipped or 0)
        row.inbound_receiving_qty = int(inbound_receiving or 0)

        db.session.add(row)

    return inserted, updated
