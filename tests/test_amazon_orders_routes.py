"""
Testes para app/integrations/amazon/routes_orders.py.
"""
from unittest.mock import MagicMock, patch

from tests.conftest import auth_client


BASE = "/integrations/amazon"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pagination(items):
    """Cria um mock de Flask-SQLAlchemy Pagination compativel com o template."""
    p = MagicMock()
    p.items   = items
    p.total   = len(items)
    p.page    = 1
    p.pages   = 1
    p.has_prev = False
    p.has_next = False
    p.iter_pages.return_value = [1]
    return p


def _fake_conn():
    c = MagicMock()
    c.id = 1
    return c


def _fake_order(order_id="111-2222222-3333333", status="Shipped"):
    o = MagicMock()
    o.amazon_order_id = order_id
    o.order_status    = status
    o.purchase_date   = None
    o.order_total_amount = 0
    o.currency        = "BRL"
    o.num_items_shipped = 1
    return o


# ---------------------------------------------------------------------------
# Unauthenticated
# ---------------------------------------------------------------------------

def test_orders_page_unauthenticated(client, db):
    resp = client.get(f"{BASE}/orders")
    assert resp.status_code in (302, 401)


def test_profit_order_unauthenticated(client, db):
    resp = client.get(f"{BASE}/profit/order/123-FAKE")
    assert resp.status_code in (302, 401)


def test_order_details_unauthenticated(client, db):
    resp = client.get(f"{BASE}/orders/123-FAKE/details")
    assert resp.status_code in (302, 401)


def test_exportar_csv_unauthenticated(client, db):
    resp = client.get(f"{BASE}/orders/exportar-csv")
    assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# GET /orders -- pagina de listagem
# ---------------------------------------------------------------------------

def test_orders_page_renders_empty(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_orders.db") as mock_db:
        mock_db.paginate.return_value = _make_pagination([])
        mock_db.select.return_value   = MagicMock()
        resp = client.get(f"{BASE}/orders")
    assert resp.status_code == 200


def test_orders_page_passes_orders_to_template(client, db):
    auth_client(client, db)
    fake_order = _fake_order()

    with patch("app.integrations.amazon.routes_orders.db") as mock_db:
        mock_db.paginate.return_value = _make_pagination([fake_order])
        mock_db.select.return_value   = MagicMock()
        resp = client.get(f"{BASE}/orders")
    assert resp.status_code == 200
    assert b"111-2222222-3333333" in resp.data


def test_orders_page_with_status_filter(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_orders.db") as mock_db:
        mock_db.paginate.return_value = _make_pagination([])
        mock_db.select.return_value   = MagicMock()
        resp = client.get(f"{BASE}/orders?status=Shipped")
    assert resp.status_code == 200


def test_orders_page_with_q_filter(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_orders.db") as mock_db:
        mock_db.paginate.return_value = _make_pagination([])
        mock_db.select.return_value   = MagicMock()
        resp = client.get(f"{BASE}/orders?q=111-222")
    assert resp.status_code == 200


def test_orders_page_with_pagination(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_orders.db") as mock_db:
        mock_db.paginate.return_value = _make_pagination([])
        mock_db.select.return_value   = MagicMock()
        resp = client.get(f"{BASE}/orders?page=2")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /orders/exportar-csv
# ---------------------------------------------------------------------------

def test_exportar_orders_csv_empty(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_orders.db") as mock_db:
        result = MagicMock()
        result.all.return_value = []
        mock_db.session.scalars.return_value = result
        resp = client.get(f"{BASE}/orders/exportar-csv")
        body = resp.data  # consome dentro do patch (stream_with_context e lazy)

    assert resp.status_code == 200
    assert "text/csv" in resp.content_type
    # Cabecalho esperado
    assert b"order_id" in body


def test_exportar_orders_csv_with_orders(client, db):
    auth_client(client, db)
    fake_order = _fake_order(order_id="222-3333333-4444444", status="Shipped")
    with patch("app.integrations.amazon.routes_orders.db") as mock_db:
        result1 = MagicMock()
        result1.all.return_value = [fake_order]
        result2 = MagicMock()
        result2.all.return_value = []
        mock_db.session.scalars.side_effect = [result1, result2]
        resp = client.get(f"{BASE}/orders/exportar-csv")
        body = resp.data  # consome dentro do patch (stream_with_context e lazy)

    assert resp.status_code == 200
    assert b"222-3333333-4444444" in body


# ---------------------------------------------------------------------------
# GET /profit/order/<id> -- sem conexao -> 400
# ---------------------------------------------------------------------------

def test_profit_order_no_conn(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_orders.db") as mock_db:
        mock_db.session.scalar.return_value = None
        resp = client.get(f"{BASE}/profit/order/111-ORDER")
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert "error" in data


# ---------------------------------------------------------------------------
# GET /profit/order/<id> -- com conexao e resultado direto
# ---------------------------------------------------------------------------

def test_profit_order_with_conn_returns_result(client, db):
    auth_client(client, db)
    fake_result = {
        "ok": True,
        "amazon_order_id": "111-RESULT",
        "mode": "finance_events",
        "net_profit": 55.0,
    }
    with patch("app.integrations.amazon.routes_orders.db") as mock_db, \
         patch("app.integrations.amazon.routes_orders.compute_order_profit",
               return_value=fake_result):
        mock_db.session.scalar.return_value = _fake_conn()
        resp = client.get(f"{BASE}/profit/order/111-RESULT")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["mode"] == "finance_events"


# ---------------------------------------------------------------------------
# GET /profit/order/<id> -- resultado None -> tenta sync, sync falha -> 400
# ---------------------------------------------------------------------------

def test_profit_order_sync_fails_returns_400(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_orders.db") as mock_db, \
         patch("app.integrations.amazon.routes_orders.compute_order_profit",
               return_value=None), \
         patch("app.integrations.amazon.routes_orders.sync_financial_events",
               side_effect=Exception("SP-API error")):
        # 1o scalar -> conn; 2o scalar -> None (order) para start ser datetime real
        mock_db.session.scalar.side_effect = [_fake_conn(), None]
        mock_db.session.execute = MagicMock()
        mock_db.session.flush = MagicMock()
        mock_db.session.rollback = MagicMock()
        resp = client.get(f"{BASE}/profit/order/111-NOSYNC")

    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert "mode" in data


# ---------------------------------------------------------------------------
# GET /profit/order/<id> -- resultado None -> sync ok -> ainda None -> 200 sem finance
# ---------------------------------------------------------------------------

def test_profit_order_sync_ok_but_still_no_data(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_orders.db") as mock_db, \
         patch("app.integrations.amazon.routes_orders.compute_order_profit",
               return_value=None), \
         patch("app.integrations.amazon.routes_orders.sync_financial_events"):
        # 1o scalar -> conn; 2o scalar -> None (order) para start ser datetime real
        mock_db.session.scalar.side_effect = [_fake_conn(), None]
        mock_db.session.execute = MagicMock()
        mock_db.session.flush = MagicMock()
        mock_db.session.commit = MagicMock()
        resp = client.get(f"{BASE}/profit/order/111-STILLNONE")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["mode"] == "no_finance_events"


# ---------------------------------------------------------------------------
# GET /orders/<id>/details -- retorna JSON
# ---------------------------------------------------------------------------

def test_order_details_returns_json(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_orders.compute_order_item_breakdown") as mock_bd:
        mock_bd.return_value = {"ok": True, "items": []}
        resp = client.get(f"{BASE}/orders/111-ORDER/details")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_order_details_returns_breakdown_items(client, db):
    auth_client(client, db)
    fake_breakdown = {
        "ok": True,
        "amazon_order_id": "333-ORDER",
        "items": [
            {"sku": "SKU-A", "qty": 2, "net_profit": 10.0},
        ],
    }
    with patch("app.integrations.amazon.routes_orders.compute_order_item_breakdown",
               return_value=fake_breakdown):
        resp = client.get(f"{BASE}/orders/333-ORDER/details")

    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["items"]) == 1
    assert data["items"][0]["sku"] == "SKU-A"
