"""Testes da REST API v1 documentada com Flask-Smorest."""
import pytest
from unittest.mock import MagicMock, patch
from tests.conftest import auth_client as _auth_client, make_user


@pytest.fixture
def logged_client(client, db):
    return _auth_client(client, db)


# ---------------------------------------------------------------------------
# Documentacao OpenAPI
# ---------------------------------------------------------------------------

def test_openapi_schema_accessible(client):
    resp = client.get("/api/openapi.json")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["info"]["title"] == "VEntregaz API"
    assert "paths" in data


def test_swagger_ui_accessible(client):
    resp = client.get("/api/docs")
    assert resp.status_code in (200, 301, 308)


def test_openapi_lists_amazon_and_financeiro_paths(client):
    resp = client.get("/api/openapi.json")
    data = resp.get_json()
    paths = data.get("paths", {})
    assert any("/api/v1/amazon/sync/orders" in p for p in paths)
    assert any("/api/v1/financeiro/alertas" in p for p in paths)


# ---------------------------------------------------------------------------
# Autenticacao
# ---------------------------------------------------------------------------

def test_api_requires_auth_sync(client):
    resp = client.post("/api/v1/amazon/sync/orders")
    assert resp.status_code == 401
    assert resp.get_json()["ok"] is False


def test_api_requires_auth_inventory(client):
    resp = client.post("/api/v1/amazon/inventory/sync")
    assert resp.status_code == 401


def test_api_requires_auth_alertas(client):
    resp = client.post("/api/v1/financeiro/alertas/toggle", json={"enabled": True})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Amazon endpoints -- sem integracao configurada -> 400
# ---------------------------------------------------------------------------

def test_sync_orders_no_connection(logged_client):
    with patch("app.api.routes_sync.db") as mock_db:
        mock_db.session.scalar.return_value = None
        resp = logged_client.post("/api/v1/amazon/sync/orders")
    assert resp.status_code == 400


def test_sync_finances_no_connection(logged_client):
    with patch("app.api.routes_sync.db") as mock_db:
        mock_db.session.scalar.return_value = None
        resp = logged_client.post("/api/v1/amazon/sync/finances")
    assert resp.status_code == 400


def test_sync_full_no_connection(logged_client):
    with patch("app.api.routes_sync.db") as mock_db:
        mock_db.session.scalar.return_value = None
        resp = logged_client.post("/api/v1/amazon/sync/full")
    assert resp.status_code == 400


def test_inventory_sync_no_connection(logged_client):
    with patch("app.api.routes_inventory.db") as mock_db:
        mock_db.session.scalar.return_value = None
        resp = logged_client.post("/api/v1/amazon/inventory/sync")
    assert resp.status_code == 400


def test_profit_no_connection(logged_client):
    with patch("app.api.routes_profit.db") as mock_db:
        mock_db.session.scalar.return_value = None
        resp = logged_client.get("/api/v1/amazon/profit/111-2222222-3333333")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Amazon sync com conexao mockada -> 202 + job_id
# ---------------------------------------------------------------------------

def _fake_conn(conn_id=1):
    conn = MagicMock()
    conn.id = conn_id
    return conn


def _fake_job(job_id="job-abc-123"):
    job = MagicMock()
    job.id = job_id
    return job


def test_sync_orders_queued(logged_client):
    with patch("app.api.routes_sync.db") as mock_db, \
         patch("app.api.routes_sync._queue") as mock_queue:
        mock_db.session.scalar.return_value = _fake_conn()
        mock_queue.return_value.enqueue.return_value = _fake_job("job-abc-123")

        resp = logged_client.post("/api/v1/amazon/sync/orders?days=7")

    assert resp.status_code == 202
    data = resp.get_json()
    assert data["ok"] is True
    assert data["job_id"] == "job-abc-123"
    assert data["status"] == "queued"


def test_sync_finances_queued(logged_client):
    with patch("app.api.routes_sync.db") as mock_db, \
         patch("app.api.routes_sync._queue") as mock_queue:
        mock_db.session.scalar.return_value = _fake_conn()
        mock_queue.return_value.enqueue.return_value = _fake_job("job-fin-001")

        resp = logged_client.post("/api/v1/amazon/sync/finances?days=30")

    assert resp.status_code == 202
    data = resp.get_json()
    assert data["ok"] is True
    assert data["job_id"] == "job-fin-001"


def test_sync_full_queued(logged_client):
    with patch("app.api.routes_sync.db") as mock_db, \
         patch("app.api.routes_sync._queue") as mock_queue:
        mock_db.session.scalar.return_value = _fake_conn()
        mock_queue.return_value.enqueue.return_value = _fake_job("job-full-007")

        resp = logged_client.post("/api/v1/amazon/sync/full?days=14")

    assert resp.status_code == 202
    assert resp.get_json()["job_id"] == "job-full-007"


# ---------------------------------------------------------------------------
# Job status
# ---------------------------------------------------------------------------

class _JobStatus:
    """Simula rq.job.JobStatus: tem .value e __str__ corretos."""
    def __init__(self, v: str):
        self.value = v

    def __str__(self):
        return self.value


def test_job_status_not_found(logged_client):
    with patch("app.api.routes_sync._queue") as mock_queue, \
         patch("rq.job.Job") as mock_job_cls:
        from rq.exceptions import NoSuchJobError
        mock_queue.return_value.connection = MagicMock()
        mock_job_cls.fetch.side_effect = NoSuchJobError("no job")
        resp = logged_client.get("/api/v1/amazon/jobs/nao-existe-este-job")

    assert resp.status_code == 404


def test_job_status_queued(logged_client):
    with patch("app.api.routes_sync._queue") as mock_queue, \
         patch("rq.job.Job") as mock_job_cls:
        mock_queue.return_value.connection = MagicMock()
        mock_job = MagicMock()
        mock_job.get_status.return_value = _JobStatus("queued")
        mock_job.result = None
        mock_job_cls.fetch.return_value = mock_job

        resp = logged_client.get("/api/v1/amazon/jobs/job-queued-123")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["status"] == "queued"


def test_job_status_finished(logged_client):
    with patch("app.api.routes_sync._queue") as mock_queue, \
         patch("rq.job.Job") as mock_job_cls:
        mock_queue.return_value.connection = MagicMock()
        mock_job = MagicMock()
        mock_job.get_status.return_value = _JobStatus("finished")
        mock_job.result = {"synced": 42}
        mock_job_cls.fetch.return_value = mock_job

        resp = logged_client.get("/api/v1/amazon/jobs/job-done-456")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "finished"
    assert data["result"] == {"synced": 42}


def test_job_status_failed(logged_client):
    with patch("app.api.routes_sync._queue") as mock_queue, \
         patch("rq.job.Job") as mock_job_cls:
        mock_queue.return_value.connection = MagicMock()
        mock_job = MagicMock()
        mock_job.get_status.return_value = _JobStatus("failed")
        mock_result = MagicMock()
        mock_result.exc_string = "SomeError: something broke"
        mock_job.latest_result.return_value = mock_result
        mock_job_cls.fetch.return_value = mock_job

        resp = logged_client.get("/api/v1/amazon/jobs/job-fail-789")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "failed"
    assert "SomeError" in data["error"]


# ---------------------------------------------------------------------------
# Profit endpoint com conexao mas sem dados financeiros
# ---------------------------------------------------------------------------

def test_profit_with_connection_no_finance_data(logged_client):
    fake_conn = _fake_conn()
    with patch("app.api.routes_profit.db") as mock_db, \
         patch("app.api.routes_profit.compute_order_profit", return_value=None):
        mock_db.session.scalar.return_value = fake_conn
        resp = logged_client.get("/api/v1/amazon/profit/222-3333333-4444444")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["mode"] == "no_finance_events"


def test_profit_with_connection_returns_result(logged_client):
    fake_result = {
        "ok": True,
        "amazon_order_id": "333-4444444-5555555",
        "mode": "finance_events",
    }
    with patch("app.api.routes_profit.db") as mock_db, \
         patch("app.api.routes_profit.compute_order_profit", return_value=fake_result):
        mock_db.session.scalar.return_value = _fake_conn()
        resp = logged_client.get("/api/v1/amazon/profit/333-4444444-5555555")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["mode"] == "finance_events"


def test_order_items_returns_result(logged_client):
    """items endpoint nao verifica conexao -- retorna resultado direto do servico."""
    fake_result = {"ok": True, "amazon_order_id": "444-5555555-6666666", "mode": "items"}
    with patch("app.api.routes_profit.compute_order_item_breakdown", return_value=fake_result):
        resp = logged_client.get("/api/v1/amazon/orders/444-5555555-6666666/items")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True


# ---------------------------------------------------------------------------
# Alertas (nao precisam de integracao Amazon)
# ---------------------------------------------------------------------------

def test_alertas_toggle_true(logged_client):
    resp = logged_client.post(
        "/api/v1/financeiro/alertas/toggle",
        json={"enabled": True},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["enabled"] is True


def test_alertas_toggle_false(logged_client):
    resp = logged_client.post(
        "/api/v1/financeiro/alertas/toggle",
        json={"enabled": False},
    )
    assert resp.status_code == 200
    assert resp.get_json()["enabled"] is False


def test_alertas_add_recipient_valid(logged_client):
    resp = logged_client.post(
        "/api/v1/financeiro/alertas/recipients",
        json={"email": "alerta@exemplo.com"},
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["ok"] is True
    assert data["email"] == "alerta@exemplo.com"
    assert data["enabled"] is True


def test_alertas_add_recipient_invalid_email(logged_client):
    resp = logged_client.post(
        "/api/v1/financeiro/alertas/recipients",
        json={"email": "nao-e-um-email"},
    )
    assert resp.status_code == 422


def test_alertas_add_recipient_missing_field(logged_client):
    resp = logged_client.post(
        "/api/v1/financeiro/alertas/recipients",
        json={},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# API Key authentication
# ---------------------------------------------------------------------------

@pytest.fixture
def user_with_key(db):
    """Cria um usuario com api_key gerada e retorna (user, key)."""
    user = make_user(db, email="apiuser@test.com", password="senha123")
    key = user.generate_api_key()
    db.session.commit()
    return user, key


def test_api_key_auth_works(client, user_with_key):
    """X-API-Key valida autentica e acessa endpoint protegido."""
    _, key = user_with_key
    resp = client.post(
        "/api/v1/financeiro/alertas/toggle",
        json={"enabled": True},
        headers={"X-API-Key": key},
    )
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_api_key_invalid(client, db):
    """X-API-Key invalida retorna 401."""
    resp = client.post(
        "/api/v1/financeiro/alertas/toggle",
        json={"enabled": True},
        headers={"X-API-Key": "chave-invalida-que-nao-existe"},
    )
    assert resp.status_code == 401


def test_api_key_missing_returns_401(client, db):
    """Sem X-API-Key e sem sessao retorna 401."""
    resp = client.post(
        "/api/v1/financeiro/alertas/toggle",
        json={"enabled": True},
    )
    assert resp.status_code == 401


def test_openapi_schema_has_api_key_security(client):
    """Schema OpenAPI expoe ApiKeyAuth como securityScheme."""
    resp = client.get("/api/openapi.json")
    data = resp.get_json()
    schemes = data.get("components", {}).get("securitySchemes", {})
    assert "ApiKeyAuth" in schemes
    assert schemes["ApiKeyAuth"]["in"] == "header"
    assert schemes["ApiKeyAuth"]["name"] == "X-API-Key"
