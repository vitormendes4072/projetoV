"""
Testes para app/main/routes.py — rota /dashboard.
"""
from decimal import Decimal

from app.models.pricing import PricingHistory
from tests.conftest import auth_client, login, make_user


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

def test_dashboard_empty_state(client, db):
    auth_client(client, db)
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "Nenhum dado ainda".encode() in resp.data


def test_dashboard_empty_has_no_charts(client, db):
    auth_client(client, db)
    resp = client.get("/dashboard")
    assert b"chartMargem" not in resp.data


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
