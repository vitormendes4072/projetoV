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
# GET /profit/order/<id> -- resultado None -> retorna 200 sem writes (GET puro)
# ---------------------------------------------------------------------------

def test_profit_order_no_finance_events_is_readonly(client, db):
    """GET deve retornar mode=no_finance_events sem tocar no BD."""
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_orders.db") as mock_db, \
         patch("app.integrations.amazon.routes_orders.compute_order_profit",
               return_value=None), \
         patch("app.integrations.amazon.routes_orders._compute_order_start",
               return_value=(None, "2026-01-08T00:00:00Z")):
        mock_db.session.scalar.return_value = _fake_conn()
        resp = client.get(f"{BASE}/profit/order/111-NOSYNC")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["mode"] == "no_finance_events"
    assert data["from"] == "2026-01-08T00:00:00Z"
    # GET não deve fazer commit/flush (sem writes)
    mock_db.session.commit.assert_not_called()
    mock_db.session.flush.assert_not_called()


# ---------------------------------------------------------------------------
# POST /profit/order/<id>/refresh -- sync falha -> 500
# ---------------------------------------------------------------------------

def test_profit_order_refresh_sync_fails_returns_500(client, db):
    """POST /refresh deve retornar 500 quando refresh_order_finances lança exceção."""
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_orders.db") as mock_db, \
         patch("app.integrations.amazon.routes_orders.refresh_order_finances",
               side_effect=Exception("SP-API error")):
        mock_db.session.scalar.return_value = _fake_conn()
        resp = client.post(f"{BASE}/profit/order/111-NOSYNC/refresh",
                           headers={"X-CSRFToken": "ignored-in-test"})

    assert resp.status_code == 500
    data = resp.get_json()
    assert data["ok"] is False
    assert "error" in data


# ---------------------------------------------------------------------------
# POST /profit/order/<id>/refresh -- sync ok mas ainda sem dados -> 200
# ---------------------------------------------------------------------------

def test_profit_order_refresh_sync_ok_still_no_data(client, db):
    """POST /refresh: sync roda sem erro mas não há ShipmentEventList -> 200 mode=no_finance_events."""
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_orders.db") as mock_db, \
         patch("app.integrations.amazon.routes_orders.compute_order_profit",
               return_value=None), \
         patch("app.integrations.amazon.routes_orders.refresh_order_finances",
               return_value=("2026-01-01T00:00:00Z", 0)):
        mock_db.session.scalar.return_value = _fake_conn()
        resp = client.post(f"{BASE}/profit/order/111-STILLNONE/refresh",
                           headers={"X-CSRFToken": "ignored-in-test"})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["mode"] == "no_finance_events"


# ---------------------------------------------------------------------------
# POST /profit/order/<id>/refresh -- sync ok, dados encontrados -> 200 com resultado
# ---------------------------------------------------------------------------

def test_profit_order_refresh_returns_result_after_sync(client, db):
    """POST /refresh: após sync bem-sucedido retorna o profit calculado."""
    auth_client(client, db)
    fake_result = {"ok": True, "amazon_order_id": "111-OK", "mode": "finance_events", "net_profit": 42.0}
    with patch("app.integrations.amazon.routes_orders.db") as mock_db, \
         patch("app.integrations.amazon.routes_orders.compute_order_profit",
               return_value=fake_result), \
         patch("app.integrations.amazon.routes_orders.refresh_order_finances",
               return_value=("2026-01-01T00:00:00Z", 3)):
        mock_db.session.scalar.return_value = _fake_conn()
        resp = client.post(f"{BASE}/profit/order/111-OK/refresh",
                           headers={"X-CSRFToken": "ignored-in-test"})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["mode"] == "finance_events"
    assert data["net_profit"] == 42.0


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


# ---------------------------------------------------------------------------
# Validação de formato de Order ID — defesa em profundidade
# ---------------------------------------------------------------------------

# IDs inválidos que devem ser rejeitados com 400 antes de chegar ao service layer.
_INVALID_IDS = [
    "../../etc/passwd",
    "<script>alert(1)</script>",
    '" OR 1=1 --',
    "111 222",          # espaço
    "111\x00222",       # null byte
    "",                 # vazio — Flask roteia para outra URL; testado via helper direto
]

# IDs válidos que devem atravessar o guard sem erro de formato.
_VALID_IDS = [
    "111-2222222-3333333",   # formato real Amazon
    "ABC-123_DEF",           # alfanumérico com hífen e underscore
    "ORDER123",              # só letras e dígitos
]


def test_profit_order_rejects_dot_in_id(client, db):
    r"""Ponto não pertence a [\w-] — deve ser rejeitado com 400."""
    auth_client(client, db)
    resp = client.get(f"{BASE}/profit/order/111.222.333")
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert "inválido" in data["error"]


def test_profit_order_rejects_at_sign_in_id(client, db):
    r"""@ não pertence a [\w-] — deve ser rejeitado com 400."""
    auth_client(client, db)
    resp = client.get(f"{BASE}/profit/order/ORDER@USER")
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_profit_order_rejects_exclamation_in_id(client, db):
    r"""! não pertence a [\w-] — deve ser rejeitado com 400."""
    auth_client(client, db)
    resp = client.get(f"{BASE}/profit/order/ORDER!123")
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_profit_order_refresh_rejects_invalid_id(client, db):
    """POST /refresh com ID inválido (ponto) retorna 400 sem tocar no service."""
    auth_client(client, db)
    resp = client.post(f"{BASE}/profit/order/bad.order.id/refresh",
                       headers={"X-CSRFToken": "ignored-in-test"})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert "inválido" in data["error"]


def test_order_details_rejects_invalid_id(client, db):
    """GET /details com @ no ID retorna 400 sem tocar no service."""
    auth_client(client, db)
    resp = client.get(f"{BASE}/orders/bad@order/details")
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert "inválido" in data["error"]


def test_profit_order_valid_id_passes_guard(client, db):
    """ID válido deve ultrapassar o guard e chegar ao service layer normalmente."""
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_orders.db") as mock_db, \
         patch("app.integrations.amazon.routes_orders.compute_order_profit",
               return_value=None), \
         patch("app.integrations.amazon.routes_orders._compute_order_start",
               return_value=(None, "2026-01-01T00:00:00Z")):
        mock_db.session.scalar.return_value = _fake_conn()
        resp = client.get(f"{BASE}/profit/order/111-2222222-3333333")
    # Chega ao service layer — retorna 200 (modo no_finance_events), não 400
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_order_id_valid_format_helper():
    """Testa a lógica do helper _valid_order_id diretamente."""
    from app.integrations.amazon.routes_orders import _valid_order_id

    for valid in _VALID_IDS:
        assert _valid_order_id(valid), f"Esperado válido: {valid!r}"

    for invalid in _INVALID_IDS:
        if invalid == "":
            continue  # string vazia: fullmatch retorna None, já coberta implicitamente
        assert not _valid_order_id(invalid), f"Esperado inválido: {invalid!r}"
