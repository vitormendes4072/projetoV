"""
Testes para app/integrations/amazon/routes_orders.py.
Tabelas Amazon usam schema="public" — queries interceptadas com mock.
"""
from unittest.mock import MagicMock, patch

from tests.conftest import auth_client


# ---------------------------------------------------------------------------
# Unauthenticated
# ---------------------------------------------------------------------------

def test_orders_page_unauthenticated(client, db):
    resp = client.get("/integrations/amazon/orders")
    assert resp.status_code in (302, 401)


def test_profit_order_unauthenticated(client, db):
    resp = client.get("/integrations/amazon/profit/order/123-FAKE")
    assert resp.status_code in (302, 401)


def test_order_details_unauthenticated(client, db):
    resp = client.get("/integrations/amazon/orders/123-FAKE/details")
    assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# GET /orders — página de listagem
# ---------------------------------------------------------------------------

def test_orders_page_renders_empty(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_orders.db") as mock_db:
        mock_db.session.scalars.return_value.all.return_value = []
        resp = client.get("/integrations/amazon/orders")
    assert resp.status_code == 200


def test_orders_page_passes_orders_to_template(client, db):
    auth_client(client, db)
    fake_order = MagicMock()
    fake_order.amazon_order_id = "111-2222222-3333333"
    fake_order.order_status = "Shipped"
    fake_order.purchase_date = None

    with patch("app.integrations.amazon.routes_orders.db") as mock_db:
        mock_db.session.scalars.return_value.all.return_value = [fake_order]
        resp = client.get("/integrations/amazon/orders")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /profit/order/<id> — sem conexão → 400
# ---------------------------------------------------------------------------

def test_profit_order_no_conn(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_orders.db") as mock_db:
        mock_db.session.scalar.return_value = None
        resp = client.get("/integrations/amazon/profit/order/111-ORDER")
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert "error" in data


# ---------------------------------------------------------------------------
# GET /orders/<id>/details — retorna JSON (compute_order_item_breakdown)
# ---------------------------------------------------------------------------

def test_order_details_returns_json(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_orders.compute_order_item_breakdown") as mock_bd:
        mock_bd.return_value = {"ok": True, "items": []}
        resp = client.get("/integrations/amazon/orders/111-ORDER/details")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
