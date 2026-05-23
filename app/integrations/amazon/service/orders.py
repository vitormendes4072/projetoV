# app/integrations/amazon/service/orders.py
"""
Funções de listagem e sincronização de pedidos Amazon.
"""
import logging
import time

from .client import DEFAULT_SLEEP, _safe_payload, _with_retry, make_orders_client


def list_orders(conn, created_after_iso: str):
    """Retorna lista completa de pedidos (paginação por NextToken)."""
    client = make_orders_client(conn)

    def first_page():
        return client.get_orders(CreatedAfter=created_after_iso)

    res = _with_retry(first_page, ctx=f"get_orders(CreatedAfter={created_after_iso})")
    payload = _safe_payload(res, f"get_orders(CreatedAfter={created_after_iso})")

    orders = payload.get("Orders", []) or []
    next_token = payload.get("NextToken")

    while next_token:
        time.sleep(DEFAULT_SLEEP)

        def next_page():
            return client.get_orders(NextToken=next_token)

        res2 = _with_retry(next_page, ctx=f"get_orders(NextToken={next_token})")
        p2 = _safe_payload(res2, f"get_orders(NextToken={next_token})")

        orders.extend(p2.get("Orders", []) or [])
        next_token = p2.get("NextToken")

    return orders


def list_order_items(conn, amazon_order_id: str):
    """Retorna itens de um pedido."""
    client = make_orders_client(conn)

    def call():
        return client.get_order_items(order_id=amazon_order_id)

    time.sleep(DEFAULT_SLEEP)
    res = _with_retry(call, ctx=f"get_order_items(order_id={amazon_order_id})")
    payload = _safe_payload(res, f"get_order_items(order_id={amazon_order_id})")

    return payload.get("OrderItems", []) or []


def sync_orders_and_items(conn, user_id: int, created_after_iso: str):
    """
    Faz upsert de orders + reinserção de items para o user_id dado.
    Retorna (orders_upserted, items_inserted, orders_returned_by_api).
    Não faz db.session.commit() — responsabilidade do chamador.
    """
    from app import db
    from app.models import AmazonOrder, AmazonOrderItem
    from app.integrations.amazon.utils import parse_iso_dt, to_sp

    orders = list_orders(conn, created_after_iso=created_after_iso)

    upserted_orders = 0
    inserted_items = 0

    for o in orders:
        amazon_order_id = o.get("AmazonOrderId")
        if not amazon_order_id:
            continue

        order = db.session.scalar(
            db.select(AmazonOrder).filter_by(user_id=user_id, amazon_order_id=amazon_order_id)
        )
        if not order:
            order = AmazonOrder(
                user_id=user_id,
                amazon_order_id=amazon_order_id,
                marketplace_id=conn.marketplace_id,
            )

        order.order_status = o.get("OrderStatus")

        dt = parse_iso_dt(o.get("PurchaseDate", ""))
        order.purchase_date = to_sp(dt)

        ot = o.get("OrderTotal") or {}
        order.currency = ot.get("CurrencyCode")
        order.order_total_amount = ot.get("Amount")

        order.raw_json = o
        db.session.add(order)
        upserted_orders += 1

        db.session.execute(
            db.delete(AmazonOrderItem)
            .where(AmazonOrderItem.user_id == user_id, AmazonOrderItem.amazon_order_id == amazon_order_id)
        )

        try:
            items = list_order_items(conn, amazon_order_id)
        except Exception as e:
            logging.getLogger(__name__).warning(
                "Falha ao buscar itens do pedido %s: %s", amazon_order_id, e
            )
            continue

        for it in items:
            ip = it.get("ItemPrice") or {}
            item = AmazonOrderItem(
                user_id=user_id,
                amazon_order_id=amazon_order_id,
                seller_sku=it.get("SellerSKU"),
                asin=it.get("ASIN"),
                quantity=it.get("QuantityOrdered"),
                item_price=ip.get("Amount"),
                currency=ip.get("CurrencyCode"),
                raw_json=it,
            )
            db.session.add(item)
            inserted_items += 1

    return upserted_orders, inserted_items, len(orders)
