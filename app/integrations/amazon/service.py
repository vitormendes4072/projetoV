# app/integrations/amazon/service.py
import time

from sp_api.api import Orders, Finances
from sp_api.base import Marketplaces
from sp_api.base.exceptions import SellingApiRequestThrottledException

# Quanto mais alto, menos chance de throttling/timeout
DEFAULT_SLEEP = 0.8


def _safe_payload(res, ctx: str):
    """
    Garante que temos um objeto response e payload.
    """
    if res is None:
        raise RuntimeError(f"SP-API retornou None em {ctx} (sem resposta).")
    payload = getattr(res, "payload", None)
    if payload is None:
        raise RuntimeError(f"SP-API sem payload em {ctx}. res={res!r}")
    return payload or {}


def marketplace_from_id(marketplace_id: str):
    # Brasil
    if marketplace_id == Marketplaces.BR.marketplace_id:
        return Marketplaces.BR
    return Marketplaces.BR


def _credentials(conn):
    creds = {
        "refresh_token": conn.lwa_refresh_token,
        "lwa_app_id": conn.lwa_client_id,
        "lwa_client_secret": conn.lwa_client_secret,
        "aws_access_key": conn.aws_access_key_id,
        "aws_secret_key": conn.aws_secret_access_key,
    }
    if getattr(conn, "role_arn", None):
        creds["role_arn"] = conn.role_arn
    return creds


def make_orders_client(conn):
    return Orders(
        marketplace=marketplace_from_id(conn.marketplace_id),
        credentials=_credentials(conn),
    )


def make_finances_client(conn):
    return Finances(
        marketplace=marketplace_from_id(conn.marketplace_id),
        credentials=_credentials(conn),
    )


def _with_retry(fn, *, max_retries=8, base_sleep=0.8, ctx=""):
    """
    Retry exponencial:
    - throttling (SellingApiRequestThrottledException)
    - falhas transitórias
    - e também quando a lib retorna None (timeout interno/sem resposta)
    """
    last_exc = None

    for i in range(max_retries):
        try:
            res = fn()

            # ✅ a lib às vezes retorna None. trate como retry.
            if res is None:
                time.sleep(base_sleep * (2 ** i))
                continue

            return res

        except SellingApiRequestThrottledException as e:
            last_exc = e
            time.sleep(base_sleep * (2 ** i))

        except Exception as e:
            last_exc = e
            time.sleep(base_sleep * (i + 1))
            continue

    if last_exc:
        raise last_exc

    raise RuntimeError(f"SP-API retornou None repetidamente {f'em {ctx}' if ctx else ''}.")


def list_orders(conn, created_after_iso: str):
    """
    Retorna lista completa (paginação por NextToken).
    """
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
    """
    Retorna itens de um pedido.
    """
    client = make_orders_client(conn)

    def call():
        return client.get_order_items(order_id=amazon_order_id)

    time.sleep(DEFAULT_SLEEP)
    res = _with_retry(call, ctx=f"get_order_items(order_id={amazon_order_id})")
    payload = _safe_payload(res, f"get_order_items(order_id={amazon_order_id})")

    return payload.get("OrderItems", []) or []


def list_financial_events(conn, posted_after_iso: str):
    """
    Puxa eventos financeiros (Finances API) com paginação (NextToken).
    Retorna (events_dict, first_payload).
    """
    client = make_finances_client(conn)

    def first_page():
        return client.list_financial_events(PostedAfter=posted_after_iso)

    res = _with_retry(first_page, ctx=f"list_financial_events(PostedAfter={posted_after_iso})")
    payload = _safe_payload(res, f"list_financial_events(PostedAfter={posted_after_iso})")

    events = payload.get("FinancialEvents", {}) or {}

    next_token = payload.get("NextToken")
    while next_token:
        time.sleep(DEFAULT_SLEEP)

        def next_page():
            return client.list_financial_events(NextToken=next_token)

        res2 = _with_retry(next_page, ctx=f"list_financial_events(NextToken={next_token})")
        p2 = _safe_payload(res2, f"list_financial_events(NextToken={next_token})")

        ev2 = p2.get("FinancialEvents", {}) or {}
        # merge simples por tipo
        for k, v in ev2.items():
            if isinstance(v, list):
                events.setdefault(k, [])
                events[k].extend(v)

        next_token = p2.get("NextToken")

    return events, payload

def make_inventory_client(conn):
    """
    Inventories API (FBA Inventory). Pode variar por versão do pacote.
    """
    from sp_api.api import Inventories  # pode lançar ImportError se não existir
    return Inventories(
        marketplace=marketplace_from_id(conn.marketplace_id),
        credentials=_credentials(conn),
    )


# ---------------------------
# Sync / upsert helpers
# ---------------------------

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

        order = AmazonOrder.query.filter_by(user_id=user_id, amazon_order_id=amazon_order_id).first()
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

        AmazonOrderItem.query.filter_by(user_id=user_id, amazon_order_id=amazon_order_id).delete()

        try:
            items = list_order_items(conn, amazon_order_id)
        except Exception as e:
            import logging
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


def _compute_fingerprint(user_id: int, fp_tuple: tuple) -> str:
    """sha256 dos campos estáveis do evento, truncado a 64 chars."""
    import hashlib
    import json
    raw = json.dumps([user_id, *[str(x) for x in fp_tuple]], sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


def sync_financial_events(conn, user_id: int, posted_after_iso: str) -> int:
    """
    Faz insert de AmazonFinancialEvent com dedupe garantida em dois níveis:
      1. In-memory (seen set) — evita inserts desnecessários dentro do mesmo run.
      2. ON CONFLICT DO NOTHING no índice único (user_id, fingerprint) — garante
         idempotência cross-run independente de wipe prévio.
    Não faz db.session.commit() — responsabilidade do chamador.
    Retorna total de eventos inseridos.
    """
    from app import db
    from app.models.amazon_finances import AmazonFinancialEvent
    from app.integrations.amazon.utils import extract_amount_currency, parse_iso_dt, to_sp
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    events, _payload = list_financial_events(conn, posted_after_iso=posted_after_iso)
    inserted_events = 0
    seen = set()

    for event_type, items in events.items():
        if not isinstance(items, list):
            continue

        for ev in items:
            if not isinstance(ev, dict):
                ev = {"value": ev}

            posted_dt = to_sp(parse_iso_dt(ev.get("PostedDate", "")))
            amazon_order_id = ev.get("AmazonOrderId") or ev.get("OrderId")
            amount, currency = extract_amount_currency(ev)

            fp_tuple = (
                event_type,
                amazon_order_id,
                ev.get("FinancialEventGroupId"),
                ev.get("PostedDate"),
                amount,
                currency,
                ev.get("ShipmentItemId") or ev.get("SellerSKU") or ev.get("ASIN") or ev.get("value"),
            )

            # nível 1: dedupe in-memory (evita round-trips desnecessários)
            if fp_tuple in seen:
                continue
            seen.add(fp_tuple)

            fingerprint = _compute_fingerprint(user_id, fp_tuple)

            # nível 2: INSERT ... ON CONFLICT DO NOTHING — idempotência cross-run
            stmt = (
                pg_insert(AmazonFinancialEvent)
                .values(
                    user_id=user_id,
                    posted_date=posted_dt,
                    event_group_id=ev.get("FinancialEventGroupId"),
                    amazon_order_id=amazon_order_id,
                    event_type=event_type,
                    amount=amount,
                    currency=currency,
                    fingerprint=fingerprint,
                    raw_json=ev,
                )
                .on_conflict_do_nothing(
                    index_elements=["user_id", "fingerprint"],
                )
            )
            result = db.session.execute(stmt)
            if result.rowcount:
                inserted_events += 1

    return inserted_events


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

        row = AmazonInventorySnapshot.query.filter_by(
            user_id=user_id,
            seller_sku=seller_sku
        ).first()

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


def get_inventory_summaries(conn, marketplace_id: str):
    """
    Retorna lista de inventory summaries.
    """
    client = make_inventory_client(conn)

    def call():
        # assinatura comum da SP-API Inventories:
        # granularityType=Marketplace, granularityId=<marketplace_id>
        return client.get_inventory_summary_marketplace(
            granularityType="Marketplace",
            granularityId=marketplace_id,
            marketplaceIds=[marketplace_id],
        )

    # algumas versões usam get_inventory_summaries em vez de get_inventory_summary_marketplace
    def call_alt():
        return client.get_inventory_summaries(
            granularityType="Marketplace",
            granularityId=marketplace_id,
            marketplaceIds=[marketplace_id],
        )

    try:
        res = _with_retry(call, ctx="inventories.get_inventory_summary_marketplace")
    except Exception:
        res = _with_retry(call_alt, ctx="inventories.get_inventory_summaries")

    payload = _safe_payload(res, "inventories payload")
    summaries = payload.get("inventorySummaries") or payload.get("InventorySummaries") or []
    return summaries
