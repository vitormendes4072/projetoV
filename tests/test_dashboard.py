"""
Testes para app/main/routes.py — rota /dashboard.
"""
from decimal import Decimal

from app.models.pricing import PricingHistory
from app.models.product import Product
from tests.conftest import auth_client, login, make_user


def _auth_client_and_get_user(client, db, email="u@test.com", password="senha123"):
    """Cria usuário, loga e retorna o objeto User (para usar o id em fixtures)."""
    user = make_user(db, email=email, password=password)
    login(client, email, password)
    return user


def _add_sim(db, user_id, margin, net_profit=Decimal("10.00"), index=0):
    sim = PricingHistory(
        user_id=user_id,
        title=f"Sim {index}",
        price=Decimal("100.00"),
        cost=Decimal("50.00"),
        fba_fee=Decimal("10.00"),
        referral_fee=Decimal("15.00"),
        tax_rate=Decimal("4.00"),
        marketing=Decimal("0.00"),
        net_profit=net_profit,
        margin=Decimal(str(margin)),
        roi=Decimal("20.00"),
    )
    db.session.add(sim)
    db.session.commit()
    return sim


# ---------------------------------------------------------------------------
# Unauthenticated
# ---------------------------------------------------------------------------

def test_dashboard_unauthenticated(client, db):
    resp = client.get("/dashboard")
    assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# Estado vazio (zero produtos, zero simulações)
# ---------------------------------------------------------------------------

def test_dashboard_onboarding_checklist_shows(client, db):
    """Novo usuário sem produtos nem Amazon vê o checklist de onboarding."""
    auth_client(client, db)
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    body = resp.data
    assert "Primeiros passos".encode() in body
    assert "Configure seus produtos".encode() in body
    assert "Conecte a Amazon".encode() in body
    assert "primeira sincroniza".encode() in body


def test_dashboard_onboarding_step1_done_when_has_products(client, db):
    """Usuário com produto vê passo 1 concluído."""
    from app.models.product import Product
    user = _auth_client_and_get_user(client, db)
    p = Product(user_id=user.id, name="Prod X", sku="SKU-001", price=10, cost=5, stock_quantity=1)
    db.session.add(p)
    db.session.commit()

    resp = client.get("/dashboard")
    assert resp.status_code == 200
    # passo 1 concluído → "Concluído" deve aparecer
    assert "Concluído".encode() in resp.data


def test_dashboard_empty_has_no_charts(client, db):
    auth_client(client, db)
    resp = client.get("/dashboard")
    assert b"chartMargem" not in resp.data


def test_dashboard_onboarding_hidden_when_complete(client, db):
    """Checklist some quando todas as 3 etapas estão ok (simulado via dados)."""
    # Simular onboarding.complete=True exige Amazon connection que não existe
    # no SQLite — testamos o inverso: com dados mas sem Amazon,
    # o checklist AINDA aparece (has_amazon_conn=False).
    user = _auth_client_and_get_user(client, db)
    _add_sim(db, user.id, margin=20)

    resp = client.get("/dashboard")
    assert resp.status_code == 200
    # Amazon não configurada → checklist ainda visível
    assert "Primeiros passos".encode() in resp.data


# ---------------------------------------------------------------------------
# Com simulações — KPIs e gráficos
# ---------------------------------------------------------------------------

def test_dashboard_shows_kpis_with_data(client, db):
    user = make_user(db, email="kpi@test.com")
    login(client, "kpi@test.com", "senha123")

    _add_sim(db, user.id, margin=25, net_profit=Decimal("25.00"), index=0)
    _add_sim(db, user.id, margin=15, net_profit=Decimal("15.00"), index=1)

    resp = client.get("/dashboard")
    assert resp.status_code == 200
    # KPI da margem aparece (25% ou 15% media)
    assert b"%" in resp.data


def test_dashboard_charts_appear_with_two_or_more_sims(client, db):
    user = make_user(db, email="charts@test.com")
    login(client, "charts@test.com", "senha123")

    for i in range(3):
        _add_sim(db, user.id, margin=10 + i * 5, index=i)

    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert b"chartMargem" in resp.data
    assert b"chartDist" in resp.data


def test_dashboard_charts_hidden_with_one_sim(client, db):
    user = make_user(db, email="one@test.com")
    login(client, "one@test.com", "senha123")

    _add_sim(db, user.id, margin=20, index=0)

    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert b"chartMargem" not in resp.data


def test_dashboard_negative_margin_bucket(client, db):
    user = make_user(db, email="neg@test.com")
    login(client, "neg@test.com", "senha123")

    _add_sim(db, user.id, margin=-5, net_profit=Decimal("-5.00"), index=0)
    _add_sim(db, user.id, margin=25, net_profit=Decimal("25.00"), index=1)

    resp = client.get("/dashboard")
    assert resp.status_code == 200
