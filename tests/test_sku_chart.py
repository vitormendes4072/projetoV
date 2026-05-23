"""Testes do scatter plot de margem x volume por SKU."""
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.models.pricing import PricingHistory
from app.models.product import Product
from app.services.sku_chart import (
    _r2,
    _user_tax_rate,
    get_sku_scatter_estimado,
    get_sku_scatter_real,
)
from tests.conftest import login, make_user

_MODULE = "app.services.sku_chart"
_PROFIT_CALC = "app.services.profit_calc"


def _scalars_rv(items):
    m = MagicMock()
    m.all.return_value = items
    return m


def _fe_row(order_id="111-1", sku="SKU-A"):
    row = MagicMock()
    row.raw_json = {"AmazonOrderId": order_id, "PostedDate": "2026-01-15T00:00:00Z",
                    "SellerSKU": sku, "Amount": {"Amount": "50.00", "CurrencyCode": "BRL"}}
    return row


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


# ---------------------------------------------------------------------------
# _user_tax_rate — helper com mock (lazy import do User)
# ---------------------------------------------------------------------------

def test_user_tax_rate_returns_rate_from_user():
    u = MagicMock()
    u.default_tax_rate = 4.0
    with patch(f"{_MODULE}.db") as mock_db:
        mock_db.session.get.return_value = u
        assert _user_tax_rate(1) == 4.0


def test_user_tax_rate_returns_zero_when_user_missing():
    with patch(f"{_MODULE}.db") as mock_db:
        mock_db.session.get.return_value = None
        assert _user_tax_rate(99) == 0.0


def test_user_tax_rate_returns_zero_when_field_is_none():
    u = MagicMock()
    u.default_tax_rate = None
    with patch(f"{_MODULE}.db") as mock_db:
        mock_db.session.get.return_value = u
        assert _user_tax_rate(1) == 0.0


def test_user_tax_rate_returns_zero_on_exception():
    with patch(f"{_MODULE}.db") as mock_db:
        mock_db.session.get.side_effect = RuntimeError("DB down")
        assert _user_tax_rate(1) == 0.0


# ---------------------------------------------------------------------------
# get_sku_scatter_real — mock-based (cobre linhas 62-130 ignoradas pelo SQLite)
# ---------------------------------------------------------------------------

_EXTRACT_ONE = {
    "by_sku": {"SKU-A": {"revenue": 100.0, "fees": -10.0, "qty": 2.0}}
}


def _run_real_mock(events, extract_rv, sku_links=None, prods_names=None,
                   prods_costs=None, user_id=1, period="all"):
    """Helper: executa get_sku_scatter_real com DB e profit_calc mockados."""
    mock_db = MagicMock()
    mock_db.session.get.return_value = None          # user_tax = 0
    mock_db.session.scalars.side_effect = [
        _scalars_rv(events),
        _scalars_rv(sku_links or []),
        _scalars_rv(prods_names or []),
        _scalars_rv(prods_costs or []),
    ]
    with patch(f"{_MODULE}.db", mock_db), \
         patch(f"{_PROFIT_CALC}.extract_net_from_shipment_events",
               return_value=extract_rv):
        return get_sku_scatter_real(user_id=user_id, period=period)


def test_scatter_real_no_events_returns_empty():
    assert _run_real_mock([], {"by_sku": {}}) == []


def test_scatter_real_returns_one_point():
    pts = _run_real_mock([_fe_row()], _EXTRACT_ONE)
    assert len(pts) == 1
    assert pts[0]["sku"] == "SKU-A"


def test_scatter_real_calculates_margin():
    """revenue=100, fees=-10, tax=0, cost=0 → net=90, lucro=90, margin=90%."""
    pts = _run_real_mock([_fe_row()], _EXTRACT_ONE)
    assert pts[0]["lucro_total"] == 90.0
    assert pts[0]["margin_pct"] == 90.0
    assert pts[0]["avg_lucro_per_unit"] == 45.0


def test_scatter_real_deducts_product_costs():
    """cost=10/unit, pack=2/unit, qty=2 → cost_total=24 → lucro=66."""
    prod = MagicMock()
    prod.sku = "SKU-A"
    prod.cost = 10.0
    prod.packaging_cost = 2.0
    pts = _run_real_mock([_fe_row()], _EXTRACT_ONE, prods_costs=[prod])
    assert pts[0]["lucro_total"] == 66.0


def test_scatter_real_skips_zero_units():
    extract = {"by_sku": {"SKU-Z": {"revenue": 100.0, "fees": -5.0, "qty": 0.0}}}
    assert _run_real_mock([_fe_row()], extract) == []


def test_scatter_real_skips_zero_revenue():
    extract = {"by_sku": {"SKU-Z": {"revenue": 0.0, "fees": 0.0, "qty": 5.0}}}
    assert _run_real_mock([_fe_row()], extract) == []


def test_scatter_real_uses_sku_link_product_name():
    link = MagicMock()
    link.amazon_seller_sku = "SKU-A"
    link.product = MagicMock()
    link.product.name = "Nome via Link"
    pts = _run_real_mock([_fe_row()], _EXTRACT_ONE, sku_links=[link])
    assert pts[0]["product_name"] == "Nome via Link"


def test_scatter_real_falls_back_to_sku_as_name():
    pts = _run_real_mock([_fe_row()], _EXTRACT_ONE)
    assert pts[0]["product_name"] == "SKU-A"


def test_scatter_real_sorts_by_revenue_desc():
    extract = {
        "by_sku": {
            "SKU-LOW":  {"revenue": 50.0,  "fees": -5.0,  "qty": 1.0},
            "SKU-HIGH": {"revenue": 200.0, "fees": -20.0, "qty": 4.0},
        }
    }
    pts = _run_real_mock([_fe_row("1", "SKU-LOW"), _fe_row("2", "SKU-HIGH")], extract)
    assert pts[0]["sku"] == "SKU-HIGH"
    assert pts[1]["sku"] == "SKU-LOW"


def test_scatter_real_period_30d_no_crash():
    pts = _run_real_mock([_fe_row()], _EXTRACT_ONE, period="30d")
    assert len(pts) == 1


def test_scatter_real_exception_returns_empty():
    with patch(f"{_MODULE}.db") as mock_db:
        mock_db.session.scalars.side_effect = RuntimeError("crash")
        assert get_sku_scatter_real(user_id=1) == []


def test_scatter_real_caps_at_80_skus():
    many = {f"SKU-{i}": {"revenue": float(100 - i), "fees": -10.0, "qty": 2.0}
            for i in range(90)}
    rows = [_fe_row(f"111-{i}", f"SKU-{i}") for i in range(90)]
    mock_db = MagicMock()
    mock_db.session.get.return_value = None
    mock_db.session.scalars.side_effect = [
        _scalars_rv(rows), _scalars_rv([]), _scalars_rv([]), _scalars_rv([])
    ]
    with patch(f"{_MODULE}.db", mock_db), \
         patch(f"{_PROFIT_CALC}.extract_net_from_shipment_events",
               return_value={"by_sku": many}):
        pts = get_sku_scatter_real(user_id=1)
    assert len(pts) == 80


# ---------------------------------------------------------------------------
# get_sku_scatter_estimado — caminhos não cobertos com mock
# ---------------------------------------------------------------------------

def test_scatter_estimado_exception_in_prod_map_uses_fallback():
    """Exceção ao buscar produtos → fallback 'produto-{pid}', sem crash."""
    row = MagicMock()
    row.product_id = 7
    row.margin = 20.0
    row.net_profit = 10.0

    mock_db = MagicMock()
    mock_db.session.scalars.side_effect = [
        _scalars_rv([row]),
        RuntimeError("DB explodiu"),  # falha ao buscar Product
    ]
    with patch(f"{_MODULE}.db", mock_db):
        result = get_sku_scatter_estimado(user_id=1)

    assert len(result) == 1
    assert result[0]["sku"] == "produto-7"
    assert result[0]["product_name"] == "Produto #7"
