# app/integrations/amazon/service/finances.py
"""
Funções de listagem e sincronização de eventos financeiros Amazon.
"""
import time

from .client import DEFAULT_SLEEP, _safe_payload, _with_retry, make_finances_client


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
        for k, v in ev2.items():
            if isinstance(v, list):
                events.setdefault(k, [])
                events[k].extend(v)

        next_token = p2.get("NextToken")

    return events, payload


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

            if fp_tuple in seen:
                continue
            seen.add(fp_tuple)

            fingerprint = _compute_fingerprint(user_id, fp_tuple)

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
