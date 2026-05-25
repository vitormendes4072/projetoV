# app/relatorios/fiscal_export.py
"""Export contábil (projeção fiscal) em CSV.

Agrega PricingHistory por mês e calcula os tributos estimados de acordo
com o regime tributário configurado no perfil do usuário.

Regimes suportados
------------------
simples / mei
    DAS = receita_bruta × aliquota_usuario
presumido
    Comércio/varejo (presunção 8% IRPJ, 12% CSLL):
    IRPJ  = base_irpj  × 15%   (adicional: 10% sobre excedente de R$ 20 k/mês)
    CSLL  = base_csll  × 9%
    PIS   = receita_bruta × 0,65%   (regime cumulativo)
    COFINS= receita_bruta × 3,00%   (regime cumulativo)
real
    IRPJ  = lucro_bruto × 15%   (simplificado; sem adições/exclusões reais)
    CSLL  = lucro_bruto × 9%
    PIS   = receita_bruta × 1,65%  (regime não-cumulativo, simplificado)
    COFINS= receita_bruta × 7,60%  (regime não-cumulativo, simplificado)

Todos os valores são PROJEÇÕES baseadas em simulações de precificação.
Consulte um contador para declarações oficiais.
"""
from __future__ import annotations

import csv
import io
from datetime import date
from typing import TYPE_CHECKING, Generator

from sqlalchemy import extract

from app import db
from app.models.pricing import PricingHistory

if TYPE_CHECKING:
    from app.models.user import User

_MONTH_PT = [
    "", "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez",
]

# Alíquotas Lucro Presumido — comércio (regime cumulativo)
_PRESUMIDO_IRPJ_PRESUNCAO = 0.08   # 8 % de presunção IRPJ
_PRESUMIDO_CSLL_PRESUNCAO = 0.12   # 12% de presunção CSLL
_PRESUMIDO_IRPJ_ALIQ      = 0.15   # 15%
_PRESUMIDO_IRPJ_ADIC      = 0.10   # adicional 10% acima de R$ 20 k/mês
_PRESUMIDO_IRPJ_ADIC_BASE = 20_000.0
_PRESUMIDO_CSLL_ALIQ      = 0.09   # 9%
_PRESUMIDO_PIS            = 0.0065 # 0,65%
_PRESUMIDO_COFINS         = 0.03   # 3,00%

# Alíquotas Lucro Real — simplificado (não-cumulativo)
_REAL_IRPJ   = 0.15
_REAL_CSLL   = 0.09
_REAL_PIS    = 0.0165
_REAL_COFINS = 0.076


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _r2(v: float) -> str:
    """Formata float com 2 casas decimais e vírgula decimal (padrão BR)."""
    return f"{v:.2f}".replace(".", ",")


def _competencia(year: int, month: int) -> str:
    return f"{month:02d}/{year}"


# ---------------------------------------------------------------------------
# Cálculos por regime
# ---------------------------------------------------------------------------

def _row_simples(year: int, month: int, receita: float, custo: float, aliq_pct: float) -> list[str]:
    base = receita
    das = base * (aliq_pct / 100.0)
    lucro = receita - custo - das
    return [
        _competencia(year, month),
        _r2(receita),
        _r2(0.0),            # deduções (simplificado — sem)
        _r2(base),           # base de cálculo = receita bruta
        _r2(aliq_pct),       # alíquota %
        _r2(das),            # DAS devido
        _r2(lucro),          # lucro estimado após DAS
        "Projeção baseada em simulações",
    ]


_HEADERS_SIMPLES = [
    "competencia", "receita_bruta", "deducoes", "base_calculo",
    "aliquota_pct", "das_devido", "lucro_estimado", "observacao",
]


def _row_presumido(year: int, month: int, receita: float, custo: float) -> list[str]:
    base_irpj = receita * _PRESUMIDO_IRPJ_PRESUNCAO
    base_csll  = receita * _PRESUMIDO_CSLL_PRESUNCAO

    irpj = base_irpj * _PRESUMIDO_IRPJ_ALIQ
    # adicional de 10% sobre o excedente mensal
    excedente = max(0.0, base_irpj - _PRESUMIDO_IRPJ_ADIC_BASE)
    irpj += excedente * _PRESUMIDO_IRPJ_ADIC

    csll    = base_csll  * _PRESUMIDO_CSLL_ALIQ
    pis     = receita    * _PRESUMIDO_PIS
    cofins  = receita    * _PRESUMIDO_COFINS
    total   = irpj + csll + pis + cofins
    lucro   = receita - custo - total
    return [
        _competencia(year, month),
        _r2(receita),
        _r2(custo),
        _r2(_PRESUMIDO_IRPJ_PRESUNCAO * 100),  # 8,00
        _r2(base_irpj),
        _r2(irpj),
        _r2(csll),
        _r2(pis),
        _r2(cofins),
        _r2(total),
        _r2(lucro),
        "Projeção baseada em simulações",
    ]


_HEADERS_PRESUMIDO = [
    "competencia", "receita_bruta", "custo_mercadoria",
    "presuncao_irpj_pct", "base_irpj", "irpj",
    "csll", "pis", "cofins", "total_tributos",
    "lucro_estimado", "observacao",
]


def _row_real(year: int, month: int, receita: float, custo: float) -> list[str]:
    lucro_bruto = receita - custo
    base_ir = max(0.0, lucro_bruto)
    irpj    = base_ir * _REAL_IRPJ
    csll    = base_ir * _REAL_CSLL
    pis     = receita * _REAL_PIS
    cofins  = receita * _REAL_COFINS
    total   = irpj + csll + pis + cofins
    lucro   = lucro_bruto - total
    return [
        _competencia(year, month),
        _r2(receita),
        _r2(custo),
        _r2(lucro_bruto),
        _r2(irpj),
        _r2(csll),
        _r2(pis),
        _r2(cofins),
        _r2(total),
        _r2(lucro),
        "Projeção baseada em simulações (simplificado)",
    ]


_HEADERS_REAL = [
    "competencia", "receita_bruta", "custo_total", "lucro_bruto",
    "irpj", "csll", "pis", "cofins", "total_tributos",
    "lucro_estimado", "observacao",
]


# ---------------------------------------------------------------------------
# Agregação mensal
# ---------------------------------------------------------------------------

def _monthly_aggregates(user_id: int, year: int) -> dict[int, dict]:
    """Retorna {month: {receita, custo}} para todos os meses do ano."""
    rows = db.session.execute(
        db.select(
            extract("month", PricingHistory.created_at).label("m"),
            db.func.sum(PricingHistory.price).label("receita"),
            db.func.sum(PricingHistory.cost + PricingHistory.fba_fee
                        + PricingHistory.price * PricingHistory.referral_fee / 100
                        + PricingHistory.price * PricingHistory.tax_rate / 100
                        + PricingHistory.marketing).label("custo"),
        )
        .where(
            PricingHistory.user_id == user_id,
            extract("year", PricingHistory.created_at) == year,
        )
        .group_by(db.text("m"))
        .order_by(db.text("m"))
    ).all()

    result: dict[int, dict] = {}
    for r in rows:
        m = int(r.m)
        result[m] = {
            "receita": float(r.receita or 0),
            "custo":   float(r.custo   or 0),
        }
    return result


# ---------------------------------------------------------------------------
# Gerador CSV (streaming)
# ---------------------------------------------------------------------------

def iter_fiscal_csv(user: "User", year: int) -> Generator[str, None, None]:
    """Gera o CSV fiscal linha a linha (compatível com stream_with_context).

    Seleciona colunas e cálculos conforme user.tax_regime.
    Meses sem simulações são omitidos.
    """
    regime   = (user.tax_regime or "simples").lower()
    aliq_pct = float(user.default_tax_rate or 6.0)

    if regime in ("simples", "mei"):
        headers  = _HEADERS_SIMPLES
        make_row = lambda y, m, rec, cst: _row_simples(y, m, rec, cst, aliq_pct)
    elif regime == "presumido":
        headers  = _HEADERS_PRESUMIDO
        make_row = _row_presumido
    else:
        # real e qualquer outro
        headers  = _HEADERS_REAL
        make_row = _row_real

    buf    = io.StringIO()
    writer = csv.writer(buf, delimiter=";")

    # BOM UTF-8 para compatibilidade com Excel BR
    yield "﻿"

    # Metadados
    writer.writerow([f"# Export Fiscal — {year}"])
    writer.writerow([f"# Regime: {regime.upper()}"])
    writer.writerow([f"# Gerado em: {date.today().isoformat()}"])
    writer.writerow([f"# PROJECAO baseada em simulacoes de precificacao"])
    writer.writerow([])
    yield buf.getvalue(); buf.seek(0); buf.truncate()

    writer.writerow(headers)
    yield buf.getvalue(); buf.seek(0); buf.truncate()

    agg = _monthly_aggregates(user.id, year)
    for month in range(1, 13):
        if month not in agg:
            continue
        receita = agg[month]["receita"]
        custo   = agg[month]["custo"]
        writer.writerow(make_row(year, month, receita, custo))
        yield buf.getvalue(); buf.seek(0); buf.truncate()
