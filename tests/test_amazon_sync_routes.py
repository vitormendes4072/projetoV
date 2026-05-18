"""
Testes para app/integrations/amazon/routes_sync.py.
As tabelas Amazon usam schema="public" (incompatível com SQLite), por isso
as queries são interceptadas com unittest.mock.patch.
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
    with patch("app.integrations.amazon.routes_sync.AmazonConnection") as MockConn:
        MockConn.query.filter_by.return_value.first.return_value = None
        resp = client.post("/integrations/amazon/sync_orders")
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert "error" in data


def test_sync_finances_no_conn(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_sync.AmazonConnection") as MockConn:
        MockConn.query.filter_by.return_value.first.return_value = None
        resp = client.post("/integrations/amazon/sync_finances")
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_sync_full_no_conn(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_sync.AmazonConnection") as MockConn:
        MockConn.query.filter_by.return_value.first.return_value = None
        resp = client.post("/integrations/amazon/sync_full")
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


# ---------------------------------------------------------------------------
# Com conexão → 202 + job_id enfileirado
# ---------------------------------------------------------------------------

def test_sync_orders_enqueues_job(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_sync.AmazonConnection") as MockConn:
        MockConn.query.filter_by.return_value.first.return_value = _fake_conn()
        resp = client.post("/integrations/amazon/sync_orders")
    assert resp.status_code == 202
    data = resp.get_json()
    assert data["ok"] is True
    assert "job_id" in data
    assert data["status"] == "queued"


def test_sync_finances_enqueues_job(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_sync.AmazonConnection") as MockConn:
        MockConn.query.filter_by.return_value.first.return_value = _fake_conn()
        resp = client.post("/integrations/amazon/sync_finances")
    assert resp.status_code == 202
    data = resp.get_json()
    assert data["ok"] is True
    assert "job_id" in data


def test_sync_full_enqueues_job(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_sync.AmazonConnection") as MockConn:
        MockConn.query.filter_by.return_value.first.return_value = _fake_conn()
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
