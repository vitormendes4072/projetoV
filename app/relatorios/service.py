from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import extract

from app import db
from app.models.pricing import PricingHistory


def get_monthly_report(user_id: int, year: int, month: int) -> dict[str, Any]:
    """Agrega simulações de precificação de um mês e retorna KPIs + linhas."""
    rows = db.session.scalars(
        db.select(PricingHistory)
        .where(
            PricingHistory.user_id == user_id,
            extract("year", PricingHistory.created_at) == year,
            extract("month", PricingHistory.created_at) == month,
        )
        .order_by(PricingHistory.created_at.desc())
    ).all()

    total = len(rows)
    if total == 0:
        return {
            "rows": [],
            "total": 0,
            "avg_margin": 0.0,
            "avg_roi": 0.0,
            "pct_profitable": 0.0,
            "year": year,
            "month": month,
        }

    margins = [float(r.margin) for r in rows]
    rois = [float(r.roi) for r in rows]
    profitable = sum(1 for m in margins if m > 0)

    return {
        "rows": rows,
        "total": total,
        "avg_margin": round(sum(margins) / total, 2),
        "avg_roi": round(sum(rois) / total, 2),
        "pct_profitable": round(profitable / total * 100, 1),
        "year": year,
        "month": month,
    }


def available_months(user_id: int) -> list[tuple[int, int]]:
    """Retorna lista de (year, month) distintos com dados, ordem decrescente."""
    rows = db.session.execute(
        db.select(
            extract("year", PricingHistory.created_at).label("y"),
            extract("month", PricingHistory.created_at).label("m"),
        )
        .where(PricingHistory.user_id == user_id)
        .distinct()
        .order_by(db.text("y DESC, m DESC"))
    ).all()
    return [(int(r.y), int(r.m)) for r in rows]
