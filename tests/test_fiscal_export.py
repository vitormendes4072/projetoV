# tests/test_fiscal_export.py
"""Testes para app.relatorios.fiscal_export e rota /relatorios/exportar-fiscal."""
from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal

import pytest

from app.relatorios.fiscal_export import (
    _competencia,
    _monthly_aggregates,
    _row_presumido,
    _row_real,
    _row_simples,
    iter_fiscal_csv,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def user_simples(app, db):
    from app.models.user import User

    u = User(
        email="simples@test.com",
        name="Simples User",
        confirmed=True,
        tax_regime="simples",
        default_tax_rate=6.0,
    )
    u.set_password("pw")
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture()
def user_presumido(app, db):
    from app.models.user import User

    u = User(
        email="presumido@test.com",
        name="Presumido User",
        confirmed=True,
        tax_regime="presumido",
        default_tax_rate=0.0,
    )
    u.set_password("pw")
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture()
def user_real(app, db):
    from app.models.user import User

    u = User(
        email="real@test.com",
        name="Real User",
        confirmed=True,
        tax_regime="real",
        default_tax_rate=0.0,
    )
    u.set_password("pw")
    db.session.add(u)
    db.session.commit()
    return u


def _add_sim(db, user_id, price, cost, month=1, year=2026):
    from app.models.pricing import PricingHistory

    ph = PricingHistory(
        user_id=user_id,
        title="Test",
        price=Decimal(str(price)),
        cost=Decimal(str(cost)),
        fba_fee=Decimal("0.00"),
        referral_fee=Decimal("0.00"),
        tax_rate=Decimal("0.00"),
        marketing=Decimal("0.00"),
        net_profit=Decimal(str(price - cost)),
        margin=Decimal("20.00"),
        roi=Decimal("20.00"),
        created_at=datetime(year, month, 15),
    )
    db.session.add(ph)
    db.session.commit()
    return ph


# ---------------------------------------------------------------------------
# Unit: helpers
# ---------------------------------------------------------------------------

def test_competencia_format():
    assert _competencia(2026, 1) == "01/2026"
    assert _competencia(2026, 12) == "12/2026"


# ---------------------------------------------------------------------------
# Unit: _row_simples
# ---------------------------------------------------------------------------

def test_row_simples_das_calculation():
    """DAS = receita × 6%; lucro = receita - custo - DAS."""
    row = _row_simples(2026, 1, receita=10_000.0, custo=6_000.0, aliq_pct=6.0)
    # base_calculo = 10000, das = 600, lucro = 10000 - 6000 - 600 = 3400
    assert row[0] == "01/2026"      # competencia
    assert row[1] == "10000,00"     # receita_bruta
    assert row[4] == "6,00"         # aliquota_pct
    assert row[5] == "600,00"       # das_devido
    assert row[6] == "3400,00"      # lucro_estimado


# ---------------------------------------------------------------------------
# Unit: _row_presumido
# ---------------------------------------------------------------------------

def test_row_presumido_calculations():
    """Verifica IRPJ, CSLL, PIS, COFINS para receita R$ 10.000."""
    row = _row_presumido(2026, 3, receita=10_000.0, custo=6_000.0)
    # base_irpj = 10000 × 8% = 800 → irpj = 800 × 15% = 120
    # base_csll = 10000 × 12% = 1200 → csll = 1200 × 9% = 108
    # pis  = 10000 × 0,65% = 65
    # cofins = 10000 × 3% = 300
    # total = 120 + 108 + 65 + 300 = 593
    assert row[0] == "03/2026"
    assert row[5] == "120,00"       # irpj
    assert row[6] == "108,00"       # csll
    assert row[7] == "65,00"        # pis
    assert row[8] == "300,00"       # cofins
    assert row[9] == "593,00"       # total_tributos


# ---------------------------------------------------------------------------
# Unit: _row_real
# ---------------------------------------------------------------------------

def test_row_real_calculations():
    """IRPJ e CSLL incidem sobre lucro; PIS/COFINS sobre receita bruta."""
    row = _row_real(2026, 6, receita=10_000.0, custo=6_000.0)
    # lucro_bruto=4000; irpj=600; csll=360; pis=165; cofins=760; total=1885; lucro_est=2115
    # _HEADERS_REAL: [0]competencia [1]receita [2]custo [3]lucro_bruto
    #                [4]irpj [5]csll [6]pis [7]cofins [8]total_tributos [9]lucro_estimado
    assert row[3] == "4000,00"      # lucro_bruto
    assert row[4] == "600,00"       # irpj
    assert row[5] == "360,00"       # csll
    assert row[6] == "165,00"       # pis
    assert row[7] == "760,00"       # cofins
    assert row[8] == "1885,00"      # total_tributos
    assert row[9] == "2115,00"      # lucro_estimado (4000 - 1885)


# ---------------------------------------------------------------------------
# Unit: _monthly_aggregates
# ---------------------------------------------------------------------------

def test_monthly_aggregates_groups_by_month(app, db, user_simples):
    _add_sim(db, user_simples.id, price=100, cost=40, month=1, year=2026)
    _add_sim(db, user_simples.id, price=200, cost=80, month=1, year=2026)
    _add_sim(db, user_simples.id, price=150, cost=60, month=3, year=2026)

    agg = _monthly_aggregates(user_simples.id, 2026)
    assert set(agg.keys()) == {1, 3}
    assert agg[1]["receita"] == pytest.approx(300.0)
    assert agg[3]["receita"] == pytest.approx(150.0)


def test_monthly_aggregates_empty_year(app, db, user_simples):
    agg = _monthly_aggregates(user_simples.id, 2020)
    assert agg == {}


# ---------------------------------------------------------------------------
# Integration: iter_fiscal_csv
# ---------------------------------------------------------------------------

def _parse_csv(content: str) -> list[list[str]]:
    """Parse do CSV (separador ;), ignora linhas de comentário (#) e vazias."""
    reader = csv.reader(
        [l for l in content.splitlines() if l.strip() and not l.startswith("#")],
        delimiter=";",
    )
    return list(reader)


def test_iter_fiscal_csv_simples_output(app, db, user_simples):
    _add_sim(db, user_simples.id, price=1000, cost=400, month=2, year=2025)

    content = "".join(iter_fiscal_csv(user_simples, 2025)).lstrip("﻿")
    rows = _parse_csv(content)

    assert rows[0] == ["competencia", "receita_bruta", "deducoes",
                       "base_calculo", "aliquota_pct", "das_devido",
                       "lucro_estimado", "observacao"]
    data_row = rows[1]
    assert data_row[0] == "02/2025"
    assert data_row[1] == "1000,00"
    assert data_row[4] == "6,00"


def test_iter_fiscal_csv_presumido_output(app, db, user_presumido):
    _add_sim(db, user_presumido.id, price=1000, cost=400, month=5, year=2025)

    content = "".join(iter_fiscal_csv(user_presumido, 2025)).lstrip("﻿")
    rows = _parse_csv(content)

    assert rows[0][0] == "competencia"
    assert "irpj" in rows[0]
    assert rows[1][0] == "05/2025"


def test_iter_fiscal_csv_omits_empty_months(app, db, user_simples):
    _add_sim(db, user_simples.id, price=100, cost=40, month=6, year=2024)

    content = "".join(iter_fiscal_csv(user_simples, 2024)).lstrip("﻿")
    rows = _parse_csv(content)

    # Só 1 linha de dados (mês 6)
    assert len(rows) == 2   # header + 1 data row
    assert rows[1][0] == "06/2024"


# ---------------------------------------------------------------------------
# Route: GET /relatorios/exportar-fiscal
# ---------------------------------------------------------------------------

def test_route_exportar_fiscal_requires_login(client, app, db):
    resp = client.get("/relatorios/exportar-fiscal")
    assert resp.status_code in (302, 401)


def test_route_exportar_fiscal_returns_csv(client, app, db, user_simples):
    from tests.conftest import login

    _add_sim(db, user_simples.id, price=500, cost=200, month=1, year=2026)
    login(client, "simples@test.com", "pw")

    resp = client.get("/relatorios/exportar-fiscal?year=2026")
    assert resp.status_code == 200
    assert "text/csv" in resp.content_type
    assert b"competencia" in resp.data
    assert b"01/2026" in resp.data


def test_route_exportar_fiscal_filename_includes_regime(client, app, db, user_presumido):
    from tests.conftest import login

    _add_sim(db, user_presumido.id, price=500, cost=200, month=1, year=2026)
    login(client, "presumido@test.com", "pw")

    resp = client.get("/relatorios/exportar-fiscal?year=2026")
    assert resp.status_code == 200
    disposition = resp.headers.get("Content-Disposition", "")
    assert "presumido" in disposition
