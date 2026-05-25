# app/services/price_suggest.py
"""Sugestão de preço ótimo via regressão linear simples.

Usa apenas a stdlib do Python (statistics.linear_regression, disponível
desde Python 3.10) — sem numpy, scipy ou sklearn.

Modelo: margin = slope * price + intercept  (OLS)
Inversão: suggested_price = (target_margin - intercept) / slope

A regressão é estimada sobre o histórico de simulações (PricingHistory)
vinculadas ao produto via product_id.
"""
from __future__ import annotations

import statistics
from typing import Literal

from app import db
from app.models.pricing import PricingHistory

# Mínimo de pontos distintos de preço para fazer a regressão
_MIN_POINTS = 3

# Limiares de R² para classificação de confiança
_HIGH_R2 = 0.80
_MED_R2 = 0.50

Confidence = Literal["alta", "média", "baixa", "insuficiente"]


def _r2_score(y: list[float], y_hat: list[float]) -> float:
    """Coeficiente de determinação R²."""
    mean_y = statistics.mean(y)
    ss_tot = sum((yi - mean_y) ** 2 for yi in y)
    ss_res = sum((yi - yhi) ** 2 for yi, yhi in zip(y, y_hat))
    if ss_tot == 0:
        return 1.0 if ss_res == 0 else 0.0
    return 1.0 - ss_res / ss_tot


def _confidence(r2: float) -> Confidence:
    if r2 >= _HIGH_R2:
        return "alta"
    if r2 >= _MED_R2:
        return "média"
    return "baixa"


def suggest_price(
    product_id: int,
    target_margin: float = 20.0,
) -> dict | None:
    """Retorna sugestão de preço para atingir ``target_margin`` (%).

    Retorna ``None`` quando:
    - Há menos de ``_MIN_POINTS`` simulações distintas por preço
    - O slope estimado é ≤ 0 (relação inversa ou plana — sem sentido econômico)
    - O preço sugerido seria negativo ou zero

    Estrutura de retorno::

        {
            "suggested_price": 89.90,    # R$
            "target_margin":   20.0,     # %
            "slope":           0.45,     # Δmargem / Δpreço
            "intercept":      -18.5,
            "r2":              0.94,
            "n_points":        7,
            "confidence":      "alta",   # "alta" | "média" | "baixa"
        }
    """
    rows = db.session.scalars(
        db.select(PricingHistory)
        .where(PricingHistory.product_id == product_id)
        .order_by(PricingHistory.created_at.asc())
    ).all()

    if len(rows) < _MIN_POINTS:
        return None

    prices  = [float(r.price)  for r in rows]
    margins = [float(r.margin) for r in rows]

    # Se todos os preços são idênticos não há variância — regressão inválida
    if len(set(prices)) < 2:
        return None

    try:
        slope, intercept = statistics.linear_regression(prices, margins)
    except statistics.StatisticsError:
        return None

    # slope ≤ 0 significaria que aumentar preço reduz margem — não faz
    # sentido para o modelo FBA (margem cresce com preço dado custo fixo)
    if slope <= 0:
        return None

    suggested_price = (target_margin - intercept) / slope

    if suggested_price <= 0:
        return None

    # R²
    y_hat = [slope * p + intercept for p in prices]
    r2 = round(_r2_score(margins, y_hat), 4)

    return {
        "suggested_price": round(suggested_price, 2),
        "target_margin":   round(target_margin, 1),
        "slope":           round(slope, 4),
        "intercept":       round(intercept, 4),
        "r2":              r2,
        "n_points":        len(rows),
        "confidence":      _confidence(r2),
    }
