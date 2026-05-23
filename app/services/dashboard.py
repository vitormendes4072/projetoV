from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import joinedload

from app import cache, db
from app.models.pricing import PricingHistory
from app.models.product import Product, ProductHistory


def _get_amazon_conn_status(user_id: int) -> tuple[bool, bool]:
    """Retorna (has_conn, has_sync) para o usuário.

    Apenas consulta o BD quando o dialeto é PostgreSQL — AmazonConnection
    usa schema="public" que não existe no SQLite.  Para outros dialetos
    retorna (False, False) explicitamente, sem engolir exceções genéricas.
    """
    if db.engine.dialect.name != "postgresql":
        return False, False

    from app.models.amazon import AmazonConnection

    conn = db.session.scalar(
        db.select(AmazonConnection).filter_by(user_id=user_id)
    )
    has_conn = conn is not None
    has_sync = has_conn and conn.last_sync_at is not None
    return has_conn, has_sync

_PERIOD_DAYS = {"7d": 7, "30d": 30, "90d": 90}


@cache.memoize(timeout=60)
def get_dashboard_kpis(user_id: int, period: str = "30d") -> dict:
    """
    Retorna todos os KPIs e dados do dashboard para um usuário.
    Resultado cacheado por 60s por (user_id, period) — ORM objects são
    serializados para SimpleNamespace antes do cache (pickle-safe).
    """
    date_from = None
    if period in _PERIOD_DAYS:
        date_from = datetime.now() - timedelta(days=_PERIOD_DAYS[period])

    def _ph_where(*extra: Any) -> list[Any]:
        clauses: list[Any] = [PricingHistory.user_id == user_id]
        if date_from:
            clauses.append(PricingHistory.created_at >= date_from)
        return clauses + list(extra)

    total_products = db.session.scalar(
        db.select(db.func.count(Product.id)).where(Product.user_id == user_id)
    )
    total_simulations = db.session.scalar(
        db.select(db.func.count(PricingHistory.id)).where(*_ph_where())
    )
    avg_margin = db.session.scalar(
        db.select(db.func.avg(PricingHistory.margin)).where(*_ph_where())
    ) or 0
    avg_roi = db.session.scalar(
        db.select(db.func.avg(PricingHistory.roi)).where(*_ph_where())
    ) or 0

    recent_sims_raw = db.session.scalars(
        db.select(PricingHistory)
        .where(*_ph_where())
        .order_by(PricingHistory.created_at.desc())
        .limit(5)
    ).all()
    recent_simulations = [
        SimpleNamespace(
            title=s.title,
            created_at=s.created_at,
            net_profit=float(s.net_profit),
            margin=float(s.margin),
        )
        for s in recent_sims_raw
    ]

    recent_changes_raw = db.session.scalars(
        db.select(ProductHistory)
        .options(joinedload(ProductHistory.product))
        .where(ProductHistory.user_id == user_id)
        .order_by(ProductHistory.changed_at.desc())
        .limit(5)
    ).all()
    recent_changes = [
        SimpleNamespace(
            product_id=c.product_id,
            product=SimpleNamespace(name=c.product.name) if c.product else None,
            action_type=c.action_type,
            changed_at=c.changed_at,
        )
        for c in recent_changes_raw
    ]

    low_stock_raw = db.session.scalars(
        db.select(Product)
        .where(
            Product.user_id == user_id,
            Product.stock_quantity <= Product.min_stock,
        )
        .order_by(Product.stock_quantity.asc())
        .limit(5)
    ).all()
    low_stock = [
        SimpleNamespace(id=p.id, name=p.name, stock_quantity=p.stock_quantity, min_stock=p.min_stock)
        for p in low_stock_raw
    ]

    chart_sims = db.session.scalars(
        db.select(PricingHistory)
        .where(*_ph_where())
        .order_by(PricingHistory.created_at.asc())
        .limit(50)
    ).all()
    chart_labels = [s.created_at.strftime("%d/%b") for s in chart_sims]
    chart_margins = [float(s.margin) for s in chart_sims]

    dist_q = db.session.execute(
        db.select(
            db.func.sum(sa.case((PricingHistory.margin < 0, 1), else_=0)).label("negative"),
            db.func.sum(sa.case((sa.and_(PricingHistory.margin >= 0, PricingHistory.margin < 10), 1), else_=0)).label("low"),
            db.func.sum(sa.case((sa.and_(PricingHistory.margin >= 10, PricingHistory.margin < 20), 1), else_=0)).label("medium"),
            db.func.sum(sa.case((PricingHistory.margin >= 20, 1), else_=0)).label("good"),
        ).where(*_ph_where())
    ).one()
    margin_dist = [
        int(dist_q.negative or 0),
        int(dist_q.low or 0),
        int(dist_q.medium or 0),
        int(dist_q.good or 0),
    ]

    # ------------------------------------------------------------------
    # Onboarding — detecta conclusão de cada etapa de setup
    # _get_amazon_conn_status verifica o dialeto antes de consultar,
    # evitando exceção em SQLite (AmazonConnection usa schema="public").
    # ------------------------------------------------------------------
    _has_conn, _has_sync = _get_amazon_conn_status(user_id)

    _has_products = total_products > 0
    onboarding = {
        "has_products":    _has_products,
        "has_amazon_conn": _has_conn,
        "has_amazon_sync": _has_sync,
        "complete":        _has_products and _has_conn and _has_sync,
    }

    return {
        "total_products": total_products,
        "total_simulations": total_simulations,
        "avg_margin": avg_margin,
        "avg_roi": avg_roi,
        "recent_simulations": recent_simulations,
        "recent_changes": recent_changes,
        "low_stock": low_stock,
        "chart_labels": chart_labels,
        "chart_margins": chart_margins,
        "margin_dist": margin_dist,
        "onboarding": onboarding,
    }
