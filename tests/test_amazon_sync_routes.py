"""
Testes para app/integrations/amazon/routes_sync.py.
"""
from unittest.mock import MagicMock, patch

from tests.conftest import auth_client


def _fake_conn(conn_id=1):
    conn = MagicMock()
    conn.id = conn_id
    return conn


# ---------------------------------------------------------------------------
# Unauthenticated — login_required redireciona
# ---------------------------------------------------------------------------

def test_sync_orders_unauthenticated(client, db):
    resp = client.post("/integrations/amazon/sync_orders")
    assert resp.status_code in (302, 401)


def test_sync_finances_unauthenticated(client, db):
    resp = client.post("/integrations/amazon/sync_finances")
    assert resp.status_code in (302, 401)


def test_sync_full_unauthenticated(client, db):
    resp = client.post("/integrations/amazon/sync_full")
    assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# Sem conexão Amazon configurada → 400
# ---------------------------------------------------------------------------

def test_sync_orders_no_conn(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_sync.db") as mock_db:
        mock_db.session.scalar.return_value = None
        resp = client.post("/integrations/amazon/sync_orders")
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert "error" in data


def test_sync_finances_no_conn(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_sync.db") as mock_db:
        mock_db.session.scalar.return_value = None
        resp = client.post("/integrations/amazon/sync_finances")
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_sync_full_no_conn(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_sync.db") as mock_db:
        mock_db.session.scalar.return_value = None
        resp = client.post("/integrations/amazon/sync_full")
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


# ---------------------------------------------------------------------------
# Com conexão → 202 + job_id enfileirado
# Mock mantido: controla o objeto retornado sem precisar de credenciais SP-API reais.
# ---------------------------------------------------------------------------

def test_sync_orders_enqueues_job(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_sync.db") as mock_db:
        mock_db.session.scalar.return_value = _fake_conn()
        resp = client.post("/integrations/amazon/sync_orders")
    assert resp.status_code == 202
    data = resp.get_json()
    assert data["ok"] is True
    assert "job_id" in data
    assert data["status"] == "queued"


def test_sync_finances_enqueues_job(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_sync.db") as mock_db:
        mock_db.session.scalar.return_value = _fake_conn()
        resp = client.post("/integrations/amazon/sync_finances")
    assert resp.status_code == 202
    data = resp.get_json()
    assert data["ok"] is True
    assert "job_id" in data


def test_sync_full_enqueues_job(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_sync.db") as mock_db:
        mock_db.session.scalar.return_value = _fake_conn()
        resp = client.post("/integrations/amazon/sync_full")
    assert resp.status_code == 202
    data = resp.get_json()
    assert data["ok"] is True
    assert "job_id" in data


# ---------------------------------------------------------------------------
# job_status — polling
# ---------------------------------------------------------------------------

def test_job_status_not_found(client, db):
    auth_client(client, db)
    resp = client.get("/integrations/amazon/jobs/nonexistent-job-id-xyz")
    assert resp.status_code == 404
    data = resp.get_json()
    assert data["ok"] is False
    assert "error" in data


def test_job_status_unauthenticated(client, db):
    resp = client.get("/integrations/amazon/jobs/some-job-id")
    assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# job_status — finished / failed / queued branches
# ---------------------------------------------------------------------------

class _JobStatus:
    """Simula rq.job.JobStatus com .value e str() corretos."""
    def __init__(self, value: str):
        self.value = value
    def __str__(self):
        return self.value


def _mock_job(status_value, result=None, exc_string=None):
    job = MagicMock()
    job.get_status.return_value = _JobStatus(status_value)
    job.result = result
    if exc_string:
        job.latest_result.return_value.exc_string = exc_string
    else:
        job.latest_result.return_value = None
    return job


def test_job_status_finished_includes_result(client, db):
    auth_client(client, db)
    fake_result = {"ok": True, "orders": 5}
    with patch("rq.job.Job.fetch", return_value=_mock_job("finished", result=fake_result)):
        resp = client.get("/integrations/amazon/jobs/fake-job-id")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["status"] == "finished"
    assert data["result"] == fake_result


def test_job_status_failed_includes_error(client, db):
    auth_client(client, db)
    with patch("rq.job.Job.fetch",
               return_value=_mock_job("failed", exc_string="RuntimeError: boom")):
        resp = client.get("/integrations/amazon/jobs/fake-job-id")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "failed"
    assert "error" in data
    assert "RuntimeError" in data["error"]


def test_job_status_queued_has_no_result_key(client, db):
    auth_client(client, db)
    with patch("rq.job.Job.fetch", return_value=_mock_job("queued")):
        resp = client.get("/integrations/amazon/jobs/fake-job-id")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "queued"
    assert "result" not in data
    assert "error" not in data


# ---------------------------------------------------------------------------
# sync_full_debug — síncrono (dev only)
# ---------------------------------------------------------------------------

_BASE = "/integrations/amazon"
_ROUTES_SYNC = "app.integrations.amazon.routes_sync"


def test_sync_full_debug_no_conn(client, db):
    auth_client(client, db)
    with patch(f"{_ROUTES_SYNC}.db") as mock_db:
        mock_db.session.scalar.return_value = None
        resp = client.get(f"{_BASE}/sync_full_debug")
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_sync_full_debug_success(client, db):
    auth_client(client, db)
    from datetime import datetime, timezone
    fake_start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with patch(f"{_ROUTES_SYNC}.db") as mock_db, \
         patch(f"{_ROUTES_SYNC}.compute_sync_start", return_value=fake_start), \
         patch(f"{_ROUTES_SYNC}.sync_orders_and_items", return_value=(5, 20, 5)), \
         patch(f"{_ROUTES_SYNC}.sync_financial_events", return_value=10):
        mock_db.session.scalar.return_value = _fake_conn()
        mock_db.session.execute.return_value = MagicMock()
        resp = client.get(f"{_BASE}/sync_full_debug")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["orders"] == 5
    assert data["items"] == 20
    assert data["financial_events"] == 10


def test_sync_full_debug_exception_returns_400(client, db):
    auth_client(client, db)
    from datetime import datetime, timezone
    fake_start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with patch(f"{_ROUTES_SYNC}.db") as mock_db, \
         patch(f"{_ROUTES_SYNC}.compute_sync_start", return_value=fake_start), \
         patch(f"{_ROUTES_SYNC}.sync_orders_and_items",
               side_effect=RuntimeError("SP-API down")):
        mock_db.session.scalar.return_value = _fake_conn()
        resp = client.get(f"{_BASE}/sync_full_debug")
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


# ---------------------------------------------------------------------------
# sync_orders_only — operação leve síncrona
# ---------------------------------------------------------------------------

def test_sync_orders_only_no_conn(client, db):
    auth_client(client, db)
    with patch(f"{_ROUTES_SYNC}.db") as mock_db:
        mock_db.session.scalar.return_value = None
        resp = client.get(f"{_BASE}/sync_orders_only?days=7")
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_sync_orders_only_list_orders_fails(client, db):
    auth_client(client, db)
    with patch(f"{_ROUTES_SYNC}.db") as mock_db, \
         patch(f"{_ROUTES_SYNC}.list_orders", side_effect=RuntimeError("throttled")):
        mock_db.session.scalar.return_value = _fake_conn()
        resp = client.get(f"{_BASE}/sync_orders_only")
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_sync_orders_only_success_no_orders(client, db):
    auth_client(client, db)
    with patch(f"{_ROUTES_SYNC}.db") as mock_db, \
         patch(f"{_ROUTES_SYNC}.list_orders", return_value=[]):
        mock_db.session.scalar.return_value = _fake_conn()
        resp = client.get(f"{_BASE}/sync_orders_only")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["orders_upserted"] == 0
    assert data["orders_returned_by_api"] == 0


def test_sync_orders_only_upserts_new_order(client, db):
    auth_client(client, db)
    api_order = {
        "AmazonOrderId": "111-NEW",
        "OrderStatus": "Shipped",
        "PurchaseDate": "2026-01-15T10:00:00Z",
        "OrderTotal": {"Amount": "100.00", "CurrencyCode": "BRL"},
    }
    with patch(f"{_ROUTES_SYNC}.db") as mock_db, \
         patch(f"{_ROUTES_SYNC}.list_orders", return_value=[api_order]):
        # scalar: 1st call → conn, 2nd call → None (order doesn't exist)
        mock_db.session.scalar.side_effect = [_fake_conn(), None]
        resp = client.get(f"{_BASE}/sync_orders_only")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["orders_upserted"] == 1
    assert data["orders_returned_by_api"] == 1


def test_sync_orders_only_skips_order_without_id(client, db):
    auth_client(client, db)
    bad_order = {"OrderStatus": "Shipped"}  # sem AmazonOrderId
    with patch(f"{_ROUTES_SYNC}.db") as mock_db, \
         patch(f"{_ROUTES_SYNC}.list_orders", return_value=[bad_order]):
        mock_db.session.scalar.return_value = _fake_conn()
        resp = client.get(f"{_BASE}/sync_orders_only")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["orders_upserted"] == 0
    assert data["orders_returned_by_api"] == 1


# ---------------------------------------------------------------------------
# sync_items_batch — operação leve síncrona
# ---------------------------------------------------------------------------

def _make_scalars_result(items):
    m = MagicMock()
    m.all.return_value = items
    return m


def _fake_order_row(order_id="111-2222-3333"):
    o = MagicMock()
    o.amazon_order_id = order_id
    return o


def test_sync_items_batch_no_conn(client, db):
    auth_client(client, db)
    with patch(f"{_ROUTES_SYNC}.db") as mock_db:
        mock_db.session.scalar.return_value = None
        resp = client.post(f"{_BASE}/sync_items_batch")
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_sync_items_batch_no_orders_in_db(client, db):
    auth_client(client, db)
    with patch(f"{_ROUTES_SYNC}.db") as mock_db:
        mock_db.session.scalar.return_value = _fake_conn()
        mock_db.session.scalars.return_value = _make_scalars_result([])
        resp = client.post(f"{_BASE}/sync_items_batch")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["processed_orders"] == 0
    assert data["inserted_items"] == 0


def test_sync_items_batch_skips_orders_with_existing_items(client, db):
    auth_client(client, db)
    order = _fake_order_row("111-EXIST")
    existing_item = MagicMock()
    with patch(f"{_ROUTES_SYNC}.db") as mock_db:
        # scalar: conn, then existing item check returns a mock (items exist)
        mock_db.session.scalar.side_effect = [_fake_conn(), existing_item]
        mock_db.session.scalars.return_value = _make_scalars_result([order])
        resp = client.post(f"{_BASE}/sync_items_batch")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["skipped_orders"] == 1
    assert data["processed_orders"] == 0


def test_sync_items_batch_list_order_items_fails_returns_400(client, db):
    auth_client(client, db)
    order = _fake_order_row("111-FAIL")
    with patch(f"{_ROUTES_SYNC}.db") as mock_db, \
         patch(f"{_ROUTES_SYNC}.list_order_items",
               side_effect=RuntimeError("SP-API error")):
        # scalar: conn, then None (no existing items)
        mock_db.session.scalar.side_effect = [_fake_conn(), None]
        mock_db.session.scalars.return_value = _make_scalars_result([order])
        resp = client.post(f"{_BASE}/sync_items_batch")
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_sync_items_batch_inserts_items(client, db):
    auth_client(client, db)
    order = _fake_order_row("111-OK")
    api_items = [
        {"SellerSKU": "SKU-A", "ASIN": "B001", "QuantityOrdered": 2,
         "ItemPrice": {"Amount": "50.00", "CurrencyCode": "BRL"}},
        {"SellerSKU": "SKU-B", "ASIN": "B002", "QuantityOrdered": 1,
         "ItemPrice": {"Amount": "30.00", "CurrencyCode": "BRL"}},
    ]
    with patch(f"{_ROUTES_SYNC}.db") as mock_db, \
         patch(f"{_ROUTES_SYNC}.list_order_items", return_value=api_items):
        mock_db.session.scalar.side_effect = [_fake_conn(), None]
        mock_db.session.scalars.return_value = _make_scalars_result([order])
        resp = client.post(f"{_BASE}/sync_items_batch")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["processed_orders"] == 1
    assert data["inserted_items"] == 2


def test_sync_items_batch_respects_limit(client, db):
    """Não deve processar mais de `limit` pedidos."""
    auth_client(client, db)
    orders = [_fake_order_row(f"111-{i}") for i in range(5)]
    api_items = [{"SellerSKU": "SKU-X", "ASIN": "B001", "QuantityOrdered": 1,
                  "ItemPrice": {"Amount": "10.00", "CurrencyCode": "BRL"}}]
    with patch(f"{_ROUTES_SYNC}.db") as mock_db, \
         patch(f"{_ROUTES_SYNC}.list_order_items", return_value=api_items):
        # conn + None para cada verificação de item existente (5 pedidos)
        mock_db.session.scalar.side_effect = [_fake_conn()] + [None] * 5
        mock_db.session.scalars.return_value = _make_scalars_result(orders)
        resp = client.post(f"{_BASE}/sync_items_batch?limit=2")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["processed_orders"] == 2   # limitado a 2
