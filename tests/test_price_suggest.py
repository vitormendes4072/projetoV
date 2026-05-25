# tests/test_price_suggest.py
"""Testes para app.services.price_suggest e rota /preco-sugerido."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.price_suggest import _confidence, _r2_score, suggest_price

MODULE_ROUTE = "app.produtos.routes"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def user(app, db):
    from app.models.user import User

    u = User(email="ps@test.com", name="PS User", confirmed=True)
    u.set_password("pw")
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture()
def product(app, db, user):
    from app.models.product import Product

    p = Product(
        name="Produto PS",
        sku="SKU-PS-01",
        cost=Decimal("20.00"),
        price=Decimal("60.00"),
        packaging_cost=Decimal("0.00"),
        user_id=user.id,
    )
    db.session.add(p)
    db.session.commit()
    return p


def _add_sim(db, user_id, product_id, price, margin, cost=20.0):
    from app.models.pricing import PricingHistory

    ph = PricingHistory(
        user_id=user_id,
        product_id=product_id,
        title="Sim",
        price=Decimal(str(price)),
        cost=Decimal(str(cost)),
        fba_fee=Decimal("5.00"),
        referral_fee=Decimal("5.00"),
        tax_rate=Decimal("4.00"),
        marketing=Decimal("0.00"),
        net_profit=Decimal(str(price * margin / 100)),
        margin=Decimal(str(margin)),
        roi=Decimal("20.00"),
    )
    db.session.add(ph)
    db.session.commit()
    return ph


# ---------------------------------------------------------------------------
# Unit: _r2_score
# ---------------------------------------------------------------------------

def test_r2_perfect():
    y     = [1.0, 2.0, 3.0]
    y_hat = [1.0, 2.0, 3.0]
    assert _r2_score(y, y_hat) == pytest.approx(1.0)


def test_r2_zero():
    y     = [1.0, 2.0, 3.0]
    y_hat = [2.0, 2.0, 2.0]   # predição constante = média → R² = 0
    assert _r2_score(y, y_hat) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Unit: _confidence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("r2,expected", [
    (0.95, "alta"),
    (0.80, "alta"),
    (0.65, "média"),
    (0.50, "média"),
    (0.30, "baixa"),
])
def test_confidence_thresholds(r2, expected):
    assert _confidence(r2) == expected


# ---------------------------------------------------------------------------
# Unit: suggest_price
# ---------------------------------------------------------------------------

def test_suggest_price_too_few_points(app, db, user, product):
    """Menos de 3 simulações → None."""
    _add_sim(db, user.id, product.id, price=50, margin=15)
    _add_sim(db, user.id, product.id, price=70, margin=22)
    result = suggest_price(product.id, target_margin=20.0)
    assert result is None


def test_suggest_price_all_same_price(app, db, user, product):
    """Preço idêntico em todos os pontos → sem variância → None."""
    for _ in range(4):
        _add_sim(db, user.id, product.id, price=60, margin=20)
    result = suggest_price(product.id, target_margin=20.0)
    assert result is None


def test_suggest_price_valid_regression(app, db, user, product):
    """Regressão válida com pontos colineares → R² = 1, preço correto."""
    # margin = 0.3 * price − 2  →  para margem 20%: price = (20 + 2) / 0.3 = 73.33
    points = [(50, 13.0), (60, 16.0), (70, 19.0), (80, 22.0), (90, 25.0)]
    for p, m in points:
        _add_sim(db, user.id, product.id, price=p, margin=m)

    result = suggest_price(product.id, target_margin=20.0)
    assert result is not None
    assert result["suggested_price"] == pytest.approx(73.33, abs=0.1)
    assert result["r2"] == pytest.approx(1.0, abs=0.001)
    assert result["confidence"] == "alta"
    assert result["n_points"] == 5


def test_suggest_price_returns_keys(app, db, user, product):
    """Resultado contém todas as chaves esperadas."""
    for p, m in [(40, 10), (60, 18), (80, 26), (100, 34)]:
        _add_sim(db, user.id, product.id, price=p, margin=m)

    result = suggest_price(product.id, target_margin=15.0)
    assert result is not None
    assert set(result.keys()) == {
        "suggested_price", "target_margin", "slope",
        "intercept", "r2", "n_points", "confidence",
    }


def test_suggest_price_different_targets(app, db, user, product):
    """Target maior → preço sugerido maior (relação monotônica)."""
    for p, m in [(40, 10), (60, 18), (80, 26), (100, 34)]:
        _add_sim(db, user.id, product.id, price=p, margin=m)

    r15 = suggest_price(product.id, target_margin=15.0)
    r25 = suggest_price(product.id, target_margin=25.0)
    assert r15 is not None and r25 is not None
    assert r25["suggested_price"] > r15["suggested_price"]


# ---------------------------------------------------------------------------
# Route: GET /produtos/<id>/preco-sugerido
# ---------------------------------------------------------------------------

def test_route_preco_sugerido_insufficient_data(client, app, db, user, product):
    from tests.conftest import login

    login(client, "ps@test.com", "pw")

    resp = client.get(f"/produtos/{product.id}/preco-sugerido")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is False
    assert data["reason"] == "dados_insuficientes"


def test_route_preco_sugerido_with_data(client, app, db, user, product):
    from tests.conftest import login

    for p, m in [(40, 10), (60, 18), (80, 26), (100, 34)]:
        _add_sim(db, user.id, product.id, price=p, margin=m)

    login(client, "ps@test.com", "pw")

    resp = client.get(f"/produtos/{product.id}/preco-sugerido?target=20")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert "suggested_price" in data
    assert data["suggested_price"] > 0


def test_route_preco_sugerido_requires_login(client, app, db, user, product):
    resp = client.get(f"/produtos/{product.id}/preco-sugerido")
    assert resp.status_code in (302, 401)


def test_route_preco_sugerido_wrong_owner(client, app, db, user, product):
    from app.models.user import User
    from tests.conftest import login

    other = User(email="other@test.com", name="Other", confirmed=True)
    other.set_password("pw2")
    db.session.add(other)
    db.session.commit()

    login(client, "other@test.com", "pw2")
    resp = client.get(f"/produtos/{product.id}/preco-sugerido")
    assert resp.status_code == 403
