"""Testes da REST API v1 documentada com Flask-Smorest."""
import pytest
from unittest.mock import MagicMock, patch
from tests.conftest import auth_client as _auth_client


@pytest.fixture
def logged_client(client, db):
    return _auth_client(client, db)


# ---------------------------------------------------------------------------
# Documentação OpenAPI
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
# Autenticação
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
# Amazon endpoints — sem integração configurada → 400
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
# Amazon sync com conexão mockada → 202 + job_id
# ---------------------------------------------------------------------------

def _fake_conn(conn_id=1):
    conn = MagicMock()
    conn.id = conn_id
    return conn


def test_sync_orders_queued(logged_client):
    with patch("app.api.routes_sync.db") as mock_db, \
         patch("app.api.routes_sync._queue") as mock_queue:
        mock_db.session.scalar.return_value = _fake_conn()
        fake_job = MagicMock()
        fake_job.id = "job-abc-123"
        mock_queue.return_value.enqueue.return_value = fake_job

        resp = logged_client.post("/api/v1/amazon/sync/orders?days=7")

    assert resp.status_code == 202
    data = resp.get_json()
    assert data["ok"] is True
    assert data["job_id"] == "job-abc-123"
    assert data["status"] == "queued"


# ---------------------------------------------------------------------------
# Alertas (não precisam de integração Amazon)
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
