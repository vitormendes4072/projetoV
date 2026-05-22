"""Testes do comparativo de margem real x estimada (app/services/comparativo.py)."""
from decimal import Decimal
from unittest.mock import patch

from app.models.pricing import PricingHistory
from app.models.product import Product
from app.services.comparativo import aggregate_real_margin, get_sku_comparison
from tests.conftest import login, make_user


def _make_product(db, user_id, sku="SKU-A", **kw):
    p = Product(
        user_id=user_id,
        name=kw.get("name", "Produto Teste"),
        sku=sku,
        price=kw.get("price", 100),
        cost=kw.get("cost", 30),
        packaging_cost=kw.get("packaging_cost", 2),
        stock_quantity=10,
    )
    db.session.add(p)
    db.session.commit()
    return p


def _make_sim(db, user_id, product_id=None, margin=20, net_profit=15):
    sim = PricingHistory(
        user_id=user_id,
        product_id=product_id,
        title="Sim teste",
        price=Decimal("100.00"),
        cost=Decimal("30.00"),
        fba_fee=Decimal("10.00"),
        referral_fee=Decimal("15.00"),
        tax_rate=Decimal("4.00"),
        marketing=Decimal("0.00"),
        net_profit=Decimal(str(net_profit)),
        margin=Decimal(str(margin)),
        roi=Decimal("25.00"),
    )
    db.session.add(sim)
    db.session.commit()
    return sim


def _shipment_event(sku, qty, charge, fee):
    """Monta um ShipmentEventList no formato esperado pelo profit_calc."""
    return {
        "ShipmentItemList": [{
            "SellerSKU": sku,
            "QuantityShipped": qty,
            "ItemChargeList": [{"ChargeAmount": {"CurrencyAmount": charge}}],
            "ItemFeeList": [{"FeeAmount": {"CurrencyAmount": fee}}],
        }]
    }


# ---------------------------------------------------------------------------
# aggregate_real_margin -- funcao pura
# ---------------------------------------------------------------------------

def test_aggregate_real_margin_basic():
    ev = _shipment_event("SKU-A", 2, 100.0, -20.0)
    r = aggregate_real_margin([ev], {"SKU-A"}, unit_cost=10.0, unit_pack=2.0, tax_rate_pct=4.0)
    assert r is not None
    assert r["units_sold"] == 2
    assert r["revenue_total"] == 100.0
    assert r["fees_total"] == -20.0
    assert r["net_total"] == 80.0
    assert r["imposto_total"] == 4.0       # 100 * 4%
    assert r["cmv_total"] == 20.0          # 10 * 2
    assert r["embalagem_total"] == 4.0     # 2 * 2
    assert r["lucro_total"] == 52.0        # 80 - 4 - 20 - 4
    assert r["margin_pct"] == 52.0         # 52 / 100
    assert r["avg_net_per_unit"] == 26.0
    assert r["avg_revenue_per_unit"] == 50.0


def test_aggregate_real_margin_no_matching_sku():
    ev = _shipment_event("SKU-A", 2, 100.0, -20.0)
    assert aggregate_real_margin([ev], {"OUTRO"}, 10.0, 2.0, 4.0) is None


def test_aggregate_real_margin_filters_to_target_skus():
    evs = [
        _shipment_event("SKU-A", 1, 50.0, -10.0),
        _shipment_event("SKU-B", 5, 999.0, -100.0),
    ]
    r = aggregate_real_margin(evs, {"SKU-A"}, 5.0, 1.0, 0.0)
    assert r["units_sold"] == 1
    assert r["revenue_total"] == 50.0


def test_aggregate_real_margin_empty_events():
    assert aggregate_real_margin([], {"SKU-A"}, 10.0, 2.0, 4.0) is None


def test_aggregate_real_margin_zero_revenue():
    """Quando revenue=0 a margin_pct deve ser 0 sem divisao por zero."""
    ev = _shipment_event("SKU-Z", 1, 0.0, 0.0)
    r = aggregate_real_margin([ev], {"SKU-Z"}, 0.0, 0.0, 0.0)
    # units=1 mas revenue=0 -> margin_pct=0 (nao levanta excecao)
    assert r is not None
    assert r["margin_pct"] == 0.0
    assert r["revenue_total"] == 0.0


def test_aggregate_real_margin_zero_tax_rate():
    ev = _shipment_event("SKU-T", 4, 200.0, -40.0)
    r = aggregate_real_margin([ev], {"SKU-T"}, unit_cost=5.0, unit_pack=1.0, tax_rate_pct=0.0)
    assert r["imposto_total"] == 0.0
    assert r["lucro_total"] == 200.0 - 40.0 - (5.0 * 4) - (1.0 * 4)  # 160 - 20 - 4 = 136


def test_aggregate_real_margin_multiple_skus_in_target():
    """Dois SKUs no mesmo target_skus -> agrega ambos."""
    evs = [
        _shipment_event("SKU-X", 2, 100.0, -10.0),
        _shipment_event("SKU-Y", 3, 150.0, -15.0),
    ]
    r = aggregate_real_margin(evs, {"SKU-X", "SKU-Y"}, 10.0, 1.0, 0.0)
    assert r["units_sold"] == 5
    assert r["revenue_total"] == 250.0


# ---------------------------------------------------------------------------
# get_sku_comparison -- servico
# ---------------------------------------------------------------------------

def test_get_sku_comparison_estimate_only(db):
    user = make_user(db, email="svc@test.com")
    prod = _make_product(db, user.id)
    _make_sim(db, user.id, product_id=prod.id, margin=30, net_profit=20)

    data = get_sku_comparison(user.id, prod, tax_rate_pct=4.0)
    assert data["estimado"] is not None
    assert data["estimado"]["margin_pct"] == 30.0
    assert data["estimado"]["net_profit"] == 20.0
    # Sem dados Amazon no SQLite/PG vazio
    assert data["real"] is None
    assert data["has_amazon_data"] is False
    assert data["delta_margin"] is None


def test_get_sku_comparison_no_estimate(db):
    user = make_user(db, email="svc2@test.com")
    prod = _make_product(db, user.id)

    data = get_sku_comparison(user.id, prod)
    assert data["estimado"] is None
    assert data["real"] is None
    assert data["has_amazon_data"] is False


def test_get_sku_comparison_uses_latest_estimate(db):
    user = make_user(db, email="svc3@test.com")
    prod = _make_product(db, user.id)
    _make_sim(db, user.id, product_id=prod.id, margin=10, net_profit=5)
    _make_sim(db, user.id, product_id=prod.id, margin=40, net_profit=33)

    data = get_sku_comparison(user.id, prod)
    # Deve pegar a simulacao mais recente (margin=40)
    assert data["estimado"]["margin_pct"] == 40.0


def test_get_sku_comparison_ignores_other_product_sim(db):
    user = make_user(db, email="svc4@test.com")
    prod_a = _make_product(db, user.id, sku="SKU-AAA")
    prod_b = _make_product(db, user.id, sku="SKU-BBB")
    _make_sim(db, user.id, product_id=prod_b.id, margin=99, net_profit=88)

    data = get_sku_comparison(user.id, prod_a)
    assert data["estimado"] is None


def test_get_sku_comparison_with_both_real_and_estimated(db):
    """Quando ha dados reais (mockados) E estimados, delta_margin e calculado."""
    user = make_user(db, email="delta@test.com")
    prod = _make_product(db, user.id, sku="SKU-DELTA")
    _make_sim(db, user.id, product_id=prod.id, margin=25.0, net_profit=18.0)

    real_mock = {
        "revenue_total": 100.0,
        "fees_total": -15.0,
        "net_total": 85.0,
        "imposto_total": 4.0,
        "cmv_total": 20.0,
        "embalagem_total": 4.0,
        "lucro_total": 57.0,
        "units_sold": 2.0,
        "avg_net_per_unit": 28.5,
        "avg_revenue_per_unit": 50.0,
        "margin_pct": 30.0,
    }

    with patch("app.services.comparativo._real_from_finance_events", return_value=real_mock):
        data = get_sku_comparison(user.id, prod, tax_rate_pct=4.0)

    assert data["has_amazon_data"] is True
    assert data["real"] is not None
    assert data["real"]["margin_pct"] == 30.0
    assert data["estimado"]["margin_pct"] == 25.0
    # delta = real - estimado = 30 - 25 = 5
    assert data["delta_margin"] == 5.0
    # delta_net = real.avg_net_per_unit - estimado.net_profit = 28.5 - 18 = 10.5
    assert data["delta_net_unit"] == 10.5


def test_get_sku_comparison_delta_negative(db):
    """delta_margin negativo: real abaixo do estimado."""
    user = make_user(db, email="deltaneg@test.com")
    prod = _make_product(db, user.id, sku="SKU-NEG")
    _make_sim(db, user.id, product_id=prod.id, margin=35.0, net_profit=25.0)

    real_mock = {
        "revenue_total": 100.0, "fees_total": -15.0, "net_total": 85.0,
        "imposto_total": 4.0, "cmv_total": 20.0, "embalagem_total": 4.0,
        "lucro_total": 20.0, "units_sold": 2.0,
        "avg_net_per_unit": 10.0, "avg_revenue_per_unit": 50.0,
        "margin_pct": 20.0,
    }

    with patch("app.services.comparativo._real_from_finance_events", return_value=real_mock):
        data = get_sku_comparison(user.id, prod)

    assert data["delta_margin"] == -15.0  # 20 - 35 = -15


def test_get_sku_comparison_delta_none_when_no_real(db):
    """Sem dados reais -> delta_margin permanece None."""
    user = make_user(db, email="deltanone@test.com")
    prod = _make_product(db, user.id, sku="SKU-NONE")
    _make_sim(db, user.id, product_id=prod.id, margin=25.0, net_profit=18.0)

    data = get_sku_comparison(user.id, prod)
    assert data["delta_margin"] is None
    assert data["delta_net_unit"] is None


# ---------------------------------------------------------------------------
# Rota /produtos/<id>/comparativo
# ---------------------------------------------------------------------------

def test_comparativo_requires_login(client, db):
    resp = client.get("/produtos/1/comparativo")
    assert resp.status_code in (302, 401)


def test_comparativo_404_nonexistent(client, db):
    make_user(db, email="r1@test.com")
    login(client, "r1@test.com", "senha123")
    resp = client.get("/produtos/99999/comparativo")
    assert resp.status_code == 404


def test_comparativo_403_other_user(client, db):
    owner = make_user(db, email="owner@test.com")
    prod = _make_product(db, owner.id)
    make_user(db, email="intruso@test.com")
    login(client, "intruso@test.com", "senha123")
    resp = client.get(f"/produtos/{prod.id}/comparativo")
    assert resp.status_code == 403


def test_comparativo_no_data_renders(client, db):
    user = make_user(db, email="nodata@test.com")
    login(client, "nodata@test.com", "senha123")
    prod = _make_product(db, user.id)

    resp = client.get(f"/produtos/{prod.id}/comparativo")
    assert resp.status_code == 200
    assert "Nenhuma simulacao vinculada".encode() in resp.data or \
           "Nenhuma simulação vinculada".encode() in resp.data
    assert "Sem dados financeiros da Amazon".encode() in resp.data


def test_comparativo_shows_estimate(client, db):
    user = make_user(db, email="est@test.com")
    login(client, "est@test.com", "senha123")
    prod = _make_product(db, user.id)
    _make_sim(db, user.id, product_id=prod.id, margin=22, net_profit=18)

    resp = client.get(f"/produtos/{prod.id}/comparativo")
    assert resp.status_code == 200
    assert "Estimado (Simulacao)".encode() in resp.data or \
           "Estimado (Simulação)".encode() in resp.data
    assert b"22.0%" in resp.data
