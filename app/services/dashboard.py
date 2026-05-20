from types import SimpleNamespace

import sqlalchemy as sa
from sqlalchemy.orm import joinedload

from app import cache, db
from app.models.pricing import PricingHistory
from app.models.product import Product, ProductHistory


@cache.memoize(timeout=60)
def get_dashboard_kpis(user_id: int) -> dict:
    """
    Retorna todos os KPIs e dados do dashboard para um usuário.
    Resultado cacheado por 60s — ORM objects são serializados para
    SimpleNamespace antes do cache (pickle-safe, dot-access compatível
    com o template).
    """
    total_products = db.session.scalar(
        db.select(db.func.count(Product.id)).where(Product.user_id == user_id)
    )
    total_simulations = db.session.scalar(
        db.select(db.func.count(PricingHistory.id)).where(PricingHistory.user_id == user_id)
    )
    avg_margin = db.session.scalar(
        db.select(db.func.avg(PricingHistory.margin)).where(PricingHistory.user_id == user_id)
    ) or 0
    avg_roi = db.session.scalar(
        db.select(db.func.avg(PricingHistory.roi)).where(PricingHistory.user_id == user_id)
    ) or 0

    recent_sims_raw = db.session.scalars(
        db.select(PricingHistory)
        .where(PricingHistory.user_id == user_id)
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
        .where(Product.user_id == user_id, Product.stock_quantity <= 5)
        .order_by(Product.stock_quantity.asc())
        .limit(5)
    ).all()
    low_stock = [
        SimpleNamespace(id=p.id, name=p.name, stock_quantity=p.stock_quantity)
        for p in low_stock_raw
    ]

    chart_sims = db.session.scalars(
        db.select(PricingHistory)
        .where(PricingHistory.user_id == user_id)
        .order_by(PricingHistory.created_at.asc())
        .limit(20)
    ).all()
    chart_labels = [s.created_at.strftime("%d/%b") for s in chart_sims]
    chart_margins = [float(s.margin) for s in chart_sims]

    dist_q = db.session.execute(
        db.select(
            db.func.sum(sa.case((PricingHistory.margin < 0, 1), else_=0)).label("negative"),
            db.func.sum(sa.case((sa.and_(PricingHistory.margin >= 0, PricingHistory.margin < 10), 1), else_=0)).label("low"),
            db.func.sum(sa.case((sa.and_(PricingHistory.margin >= 10, PricingHistory.margin < 20), 1), else_=0)).label("medium"),
            db.func.sum(sa.case((PricingHistory.margin >= 20, 1), else_=0)).label("good"),
        ).where(PricingHistory.user_id == user_id)
    ).one()
    margin_dist = [
        int(dist_q.negative or 0),
        int(dist_q.low or 0),
        int(dist_q.medium or 0),
        int(dist_q.good or 0),
    ]

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
    }
