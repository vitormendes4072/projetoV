"""Testes do blueprint de relatórios mensais (HTML preview + PDF export)."""
import pytest
from datetime import datetime
from decimal import Decimal

from tests.conftest import auth_client as _auth_client, make_user, login
from app.models.pricing import PricingHistory
from app.models.user import User


@pytest.fixture
def logged_client(client, db):
    return _auth_client(client, db)


def _make_sim(db, user_id, margin=15.0, roi=20.0, price=100.0, cost=50.0,
              net_profit=15.0, title="SKU-TEST", year=2025, month=1):
    sim = PricingHistory(
        user_id=user_id,
        title=title,
        price=Decimal(str(price)),
        cost=Decimal(str(cost)),
        fba_fee=Decimal("10.00"),
        referral_fee=Decimal("15.00"),
        tax_rate=Decimal("4.00"),
        marketing=Decimal("0.00"),
        net_profit=Decimal(str(net_profit)),
        margin=Decimal(str(margin)),
        roi=Decimal(str(roi)),
        created_at=datetime(year, month, 15, 10, 0, 0),
    )
    db.session.add(sim)
    db.session.commit()
    return sim


def _login_with_unique_email(client, db, email):
    """Cria usuário com email único e faz login. Retorna (client, user_id)."""
    make_user(db, email=email)
    login(client, email, "senha123")
    user = db.session.query(User).filter_by(email=email).first()
    return client, user.id


# ---------------------------------------------------------------------------
# Autenticação
# ---------------------------------------------------------------------------

def test_relatorios_requires_auth(client):
    resp = client.get("/relatorios/")
    assert resp.status_code in (302, 401)


def test_relatorios_mensal_requires_auth(client):
    resp = client.get("/relatorios/mensal")
    assert resp.status_code in (302, 401)


def test_relatorios_pdf_requires_auth(client):
    resp = client.get("/relatorios/mensal/pdf?mes=2025-01")
    assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# Hub /relatorios/ — página de navegação
# ---------------------------------------------------------------------------

def test_index_renders_hub(logged_client):
    resp = logged_client.get("/relatorios/")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Relatório Mensal" in body
    assert "Margem por SKU" in body
    assert "Export Fiscal" in body


def test_index_hub_no_months_hides_quick_access(logged_client):
    """Sem simulações, o bloco de acesso rápido não aparece."""
    resp = logged_client.get("/relatorios/")
    assert resp.status_code == 200
    assert b"Acesso r" not in resp.data  # "Acesso rápido" não renderiza


def test_index_hub_shows_quick_access_when_data(client, db):
    c, uid = _login_with_unique_email(client, db, "hub_data@test.com")
    _make_sim(db, uid, year=2025, month=2)
    resp = c.get("/relatorios/")
    assert resp.status_code == 200
    assert "Acesso rápido" in resp.data.decode()


# ---------------------------------------------------------------------------
# HTML preview — mês sem dados
# ---------------------------------------------------------------------------

def test_mensal_empty_month(logged_client):
    resp = logged_client.get("/relatorios/mensal?mes=2000-01")
    assert resp.status_code == 200
    assert b"Nenhuma simula" in resp.data


# ---------------------------------------------------------------------------
# HTML preview — mês com dados
# ---------------------------------------------------------------------------

def test_mensal_with_data(client, db):
    c, uid = _login_with_unique_email(client, db, "mensal_data@test.com")
    _make_sim(db, uid, margin=18.5, roi=22.0, title="Produto A", year=2025, month=3)
    _make_sim(db, uid, margin=-2.0, roi=-1.0, title="Produto B", year=2025, month=3)

    resp = c.get("/relatorios/mensal?mes=2025-03")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Produto A" in body
    assert "Produto B" in body


def test_mensal_shows_export_button_when_data_exists(client, db):
    c, uid = _login_with_unique_email(client, db, "mensal_btn@test.com")
    _make_sim(db, uid, year=2025, month=4)

    resp = c.get("/relatorios/mensal?mes=2025-04")
    assert resp.status_code == 200
    assert b"Exportar PDF" in resp.data


def test_mensal_hides_export_button_when_no_data(logged_client):
    resp = logged_client.get("/relatorios/mensal?mes=2000-06")
    assert resp.status_code == 200
    assert b"Exportar PDF" not in resp.data


# ---------------------------------------------------------------------------
# PDF export
# ---------------------------------------------------------------------------

def test_pdf_empty_month_returns_pdf(logged_client):
    """Mês sem dados ainda deve gerar PDF válido (sem erros)."""
    resp = logged_client.get("/relatorios/mensal/pdf?mes=2000-01")
    assert resp.status_code == 200
    assert resp.content_type == "application/pdf"
    assert resp.data[:4] == b"%PDF"


def test_pdf_with_data_returns_pdf(client, db):
    c, uid = _login_with_unique_email(client, db, "pdf_data@test.com")
    _make_sim(db, uid, margin=20.0, roi=25.0, title="SKU-PDF-TEST", year=2025, month=5)

    resp = c.get("/relatorios/mensal/pdf?mes=2025-05")
    assert resp.status_code == 200
    assert resp.content_type == "application/pdf"
    assert resp.data[:4] == b"%PDF"


def test_pdf_filename_header(client, db):
    c, _ = _login_with_unique_email(client, db, "pdf_fname@test.com")

    resp = c.get("/relatorios/mensal/pdf?mes=2025-06")
    assert resp.status_code == 200
    cd = resp.headers["Content-Disposition"]
    assert "ventregaz_relatorio_" in cd
    assert ".pdf" in cd


# ---------------------------------------------------------------------------
# Parâmetro mes inválido — fallback graceful
# ---------------------------------------------------------------------------

def test_mensal_invalid_mes_param(logged_client):
    resp = logged_client.get("/relatorios/mensal?mes=invalid")
    assert resp.status_code == 200


def test_pdf_invalid_mes_param(logged_client):
    resp = logged_client.get("/relatorios/mensal/pdf?mes=abc")
    assert resp.status_code == 200
    assert resp.content_type == "application/pdf"


# ---------------------------------------------------------------------------
# Menu: endpoint relatorios.index agora resolve (sem badge "Em breve")
# ---------------------------------------------------------------------------

def test_menu_relatorios_link_active(logged_client):
    resp = logged_client.get("/menu")
    assert resp.status_code == 200
    assert b"/relatorios" in resp.data
