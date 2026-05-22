"""Testes do scatter plot de margem x volume por SKU."""
from decimal import Decimal

from app.models.pricing import PricingHistory
from app.models.product import Product
from app.services.sku_chart import (
    _r2,
    get_sku_scatter_estimado,
    get_sku_scatter_real,
)
from tests.conftest import login, make_user


def _make_product(db, user_id, sku="SKU-T", name="Produto", cost=20.0, pack=2.0):
    p = Product(
        user_id=user_id, name=name, sku=sku,
        price=100, cost=cost, packaging_cost=pack, stock_quantity=10,
    )
    db.session.add(p)
    db.session.commit()
    return p


def _make_sim(db, user_id, product_id=None, margin=20, net_profit=15):
    sim = PricingHistory(
        user_id=user_id, product_id=product_id, title="Sim",
        price=Decimal("100.00"), cost=Decimal("30.00"),
        fba_fee=Decimal("10.00"), referral_fee=Decimal("15.00"),
        tax_rate=Decimal("4.00"), marketing=Decimal("0.00"),
        net_profit=Decimal(str(net_profit)),
        margin=Decimal(str(margin)),
        roi=Decimal("25.00"),
    )
    db.session.add(sim)
    db.session.commit()
    return sim


# ---------------------------------------------------------------------------
# _r2 -- helper puro
# ---------------------------------------------------------------------------

def test_r2_rounds_to_two_decimals():
    assert _r2(1.2345) == 1.23


def test_r2_integer():
    assert _r2(5) == 5.0


def test_r2_string_number():
    assert _r2("3.14159") == 3.14


def test_r2_non_numeric_returns_zero():
    assert _r2("abc") == 0.0


def test_r2_none_returns_zero():
    assert _r2(None) == 0.0


def test_r2_decimal():
    assert _r2(Decimal("12.345")) == 12.35


# ---------------------------------------------------------------------------
# get_sku_scatter_real -- sem Amazon (SQLite) deve retornar []
# ---------------------------------------------------------------------------

def test_sku_scatter_real_returns_empty_without_amazon(db):
    user = make_user(db, email="real1@test.com")
    result = get_sku_scatter_real(user.id)
    # SQLite: tabela com schema="public" nao existe -> retorna []
    assert result == []


def test_sku_scatter_real_returns_empty_for_unknown_period(db):
    user = make_user(db, email="real2@test.com")
    result = get_sku_scatter_real(user.id, period="invalido")
    assert result == []


def test_sku_scatter_real_returns_empty_for_30d(db):
    user = make_user(db, email="real3@test.com")
    result = get_sku_scatter_real(user.id, period="30d")
    assert result == []


def test_sku_scatter_real_returns_empty_for_90d(db):
    user = make_user(db, email="real4@test.com")
    result = get_sku_scatter_real(user.id, period="90d")
    assert result == []


# ---------------------------------------------------------------------------
# get_sku_scatter_estimado -- totalmente SQLite-friendly
# ---------------------------------------------------------------------------

def test_sku_scatter_estimado_empty_without_linked_sims(db):
    user = make_user(db, email="est1@test.com")
    assert get_sku_scatter_estimado(user.id) == []


def test_sku_scatter_estimado_ignores_unlinked_sims(db):
    user = make_user(db, email="est2@test.com")
    _make_sim(db, user.id, product_id=None, margin=30)
    assert get_sku_scatter_estimado(user.id) == []


def test_sku_scatter_estimado_basic(db):
    user = make_user(db, email="est3@test.com")
    prod = _make_product(db, user.id, sku="SKU-EST")
    _make_sim(db, user.id, product_id=prod.id, margin=25, net_profit=20)
    _make_sim(db, user.id, product_id=prod.id, margin=35, net_profit=30)

    points = get_sku_scatter_estimado(user.id)
    assert len(points) == 1
    p = points[0]
    assert p["sku"] == "SKU-EST"
    assert p["sim_count"] == 2
    assert p["avg_margin_pct"] == 30.0   # (25+35)/2
    assert p["avg_net_profit"] == 25.0   # (20+30)/2


def test_sku_scatter_estimado_multiple_products(db):
    user = make_user(db, email="est4@test.com")
    prod_a = _make_product(db, user.id, sku="SKU-A", name="Prod A")
    prod_b = _make_product(db, user.id, sku="SKU-B", name="Prod B")

    _make_sim(db, user.id, product_id=prod_a.id, margin=10)
    _make_sim(db, user.id, product_id=prod_b.id, margin=40)
    _make_sim(db, user.id, product_id=prod_b.id, margin=20)

    points = get_sku_scatter_estimado(user.id)
    assert len(points) == 2
    # Ordenado por avg_margin desc: SKU-B (30%) > SKU-A (10%)
    assert points[0]["sku"] == "SKU-B"
    assert points[0]["sim_count"] == 2
    assert points[0]["avg_margin_pct"] == 30.0
    assert points[1]["sku"] == "SKU-A"
    assert points[1]["sim_count"] == 1


def test_sku_scatter_estimado_ignores_other_user(db):
    user_a = make_user(db, email="ua@test.com")
    user_b = make_user(db, email="ub@test.com")
    prod = _make_product(db, user_b.id, sku="SKU-B")
    _make_sim(db, user_b.id, product_id=prod.id, margin=99)

    # user_a nao deve ver dados de user_b
    assert get_sku_scatter_estimado(user_a.id) == []



def test_sku_scatter_estimado_negative_margin(db):
    """Margens negativas sao incluidas e ordenadas corretamente."""
    user = make_user(db, email="negmarg@test.com")
    prod_pos = _make_product(db, user.id, sku="SKU-POS", name="Positivo")
    prod_neg = _make_product(db, user.id, sku="SKU-NEG", name="Negativo")
    _make_sim(db, user.id, product_id=prod_pos.id, margin=15, net_profit=10)
    _make_sim(db, user.id, product_id=prod_neg.id, margin=-5, net_profit=-3)

    points = get_sku_scatter_estimado(user.id)
    assert len(points) == 2
    assert points[0]["sku"] == "SKU-POS"
    assert points[1]["avg_margin_pct"] == -5.0


# ---------------------------------------------------------------------------
# Rota /relatorios/sku
# ---------------------------------------------------------------------------

def test_sku_route_requires_login(client, db):
    resp = client.get("/relatorios/sku")
    assert resp.status_code in (302, 401)


def test_sku_route_renders_empty_state(client, db):
    make_user(db, email="rt1@test.com")
    login(client, "rt1@test.com", "senha123")
    resp = client.get("/relatorios/sku")
    assert resp.status_code == 200
    assert "Sem dados para exibir".encode() in resp.data


def test_sku_route_with_estimado_data(client, db):
    user = make_user(db, email="rt2@test.com")
    login(client, "rt2@test.com", "senha123")
    prod = _make_product(db, user.id, sku="SKU-RT")
    _make_sim(db, user.id, product_id=prod.id, margin=28, net_profit=22)

    resp = client.get("/relatorios/sku")
    assert resp.status_code == 200
    assert b"SKU-RT" in resp.data
    assert "Margem Estimada".encode() in resp.data
    assert b"scatterEstimado" in resp.data


def test_sku_route_period_filter_invalid(client, db):
    make_user(db, email="rt3@test.com")
    login(client, "rt3@test.com", "senha123")
    # Periodo invalido e sanitizado -> "all"
    resp = client.get("/relatorios/sku?period=999d")
    assert resp.status_code == 200


def test_sku_route_valid_periods(client, db):
    make_user(db, email="rt4@test.com")
    login(client, "rt4@test.com", "senha123")
    for period in ("30d", "90d", "all"):
        resp = client.get(f"/relatorios/sku?period={period}")
        assert resp.status_code == 200
