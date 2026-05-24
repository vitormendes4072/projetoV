"""
Background jobs para sincronização SP-API.

Todas as funções recebem apenas primitivos (user_id, conn_id) para que o RQ
consiga serializá-las com pickle sem depender de instâncias SQLAlchemy.
Cada job reconstrói o contexto de DB internamente.
"""
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)


def job_sync_orders(user_id: int, conn_id: int, days: int = 30) -> dict:
    """Sincroniza pedidos + itens para user_id."""
    from app import db
    from app.models import AmazonConnection
    from app.integrations.amazon.service import sync_orders_and_items
    from app.integrations.amazon.utils import utcnow, iso_z, compute_sync_start

    conn = db.session.get(AmazonConnection, conn_id)
    if not conn or conn.user_id != user_id:
        raise ValueError(f"AmazonConnection {conn_id} não encontrada para user {user_id}")

    start = compute_sync_start(conn, days_default=days)
    start_iso = iso_z(start)

    orders_upserted, items_inserted, returned = sync_orders_and_items(
        conn, user_id=user_id, created_after_iso=start_iso
    )
    conn.last_sync_at = utcnow()
    db.session.add(conn)
    db.session.commit()

    logger.info("job_sync_orders user=%s orders=%s items=%s", user_id, orders_upserted, items_inserted)
    return {"from": start_iso, "orders": orders_upserted, "items": items_inserted, "returned": returned}


def job_sync_finances(user_id: int, conn_id: int, days: int = 7) -> dict:
    """Sincroniza eventos financeiros para user_id (wipe + reimport no range)."""
    from app import db
    from app.models import AmazonConnection
    from app.models.amazon_finances import AmazonFinancialEvent
    from app.integrations.amazon.service import sync_financial_events
    from app.integrations.amazon.utils import utcnow, iso_z, compute_sync_start

    conn = db.session.get(AmazonConnection, conn_id)
    if not conn or conn.user_id != user_id:
        raise ValueError(f"AmazonConnection {conn_id} não encontrada para user {user_id}")

    start = compute_sync_start(conn, days_default=days)
    start_iso = iso_z(start)

    db.session.execute(
        db.delete(AmazonFinancialEvent)
        .where(
            AmazonFinancialEvent.user_id == user_id,
            AmazonFinancialEvent.posted_date >= start,
        )
    )
    db.session.flush()

    events_count = sync_financial_events(conn, user_id=user_id, posted_after_iso=start_iso)
    conn.last_sync_at = utcnow()
    db.session.add(conn)
    db.session.commit()

    # Finance events mudaram — invalida todo o cache de profit do usuário.
    from app.integrations.amazon.profit_service import invalidate_user_profit_cache
    invalidate_user_profit_cache(user_id)

    logger.info("job_sync_finances user=%s events=%s", user_id, events_count)
    return {"from": start_iso, "financial_events": events_count}


def job_sync_full(user_id: int, conn_id: int, days: int = 30) -> dict:
    """Sync completo: pedidos + itens + eventos financeiros."""
    from app import db
    from app.models import AmazonConnection
    from app.models.amazon_finances import AmazonFinancialEvent
    from app.integrations.amazon.service import sync_orders_and_items, sync_financial_events
    from app.integrations.amazon.utils import utcnow, iso_z, compute_sync_start

    conn = db.session.get(AmazonConnection, conn_id)
    if not conn or conn.user_id != user_id:
        raise ValueError(f"AmazonConnection {conn_id} não encontrada para user {user_id}")

    now = utcnow()
    start = compute_sync_start(conn, days_default=days)
    start_iso = iso_z(start)

    orders_count, items_count, returned = sync_orders_and_items(
        conn, user_id=user_id, created_after_iso=start_iso
    )

    db.session.execute(
        db.delete(AmazonFinancialEvent)
        .where(
            AmazonFinancialEvent.user_id == user_id,
            AmazonFinancialEvent.posted_date >= start,
        )
    )
    db.session.flush()

    events_count = sync_financial_events(conn, user_id=user_id, posted_after_iso=start_iso)

    conn.last_sync_at = now
    db.session.add(conn)
    db.session.commit()

    # Finance events mudaram — invalida todo o cache de profit do usuário.
    from app.integrations.amazon.profit_service import invalidate_user_profit_cache
    invalidate_user_profit_cache(user_id)

    logger.info("job_sync_full user=%s orders=%s items=%s events=%s", user_id, orders_count, items_count, events_count)
    return {
        "from": start_iso,
        "orders": orders_count,
        "items": items_count,
        "returned_orders": returned,
        "financial_events": events_count,
    }
