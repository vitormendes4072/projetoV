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
