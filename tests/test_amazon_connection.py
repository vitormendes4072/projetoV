"""
Testes para app/integrations/amazon/routes_connection.py.

Todas as tabelas Amazon usam schema="public" e nao existem no SQLite,
portanto todos os acessos ao DB sao mockados.
"""
from unittest.mock import MagicMock, patch

from tests.conftest import auth_client


BASE = "/integrations/amazon"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_conn(**kw):
    c = MagicMock()
    c.marketplace_id = kw.get("marketplace_id", "A2Q3Y263D00KWC")
    c.last_sync_at = kw.get("last_sync_at", None)
    return c


# ---------------------------------------------------------------------------
# GET /status -- nao autenticado
# ---------------------------------------------------------------------------

def test_status_unauthenticated(client, db):
    resp = client.get(f"{BASE}/status")
    assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# GET /status -- sem conexao configurada
# ---------------------------------------------------------------------------

def test_status_not_connected(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_connection.db") as mock_db:
        mock_db.session.scalar.return_value = None
        resp = client.get(f"{BASE}/status")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["connected"] is False


# ---------------------------------------------------------------------------
# GET /status -- com conexao configurada
# ---------------------------------------------------------------------------

def test_status_connected(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_connection.db") as mock_db:
        mock_db.session.scalar.return_value = _fake_conn()
        resp = client.get(f"{BASE}/status")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["connected"] is True
    assert data["marketplace_id"] == "A2Q3Y263D00KWC"
    assert "last_sync_at" in data


def test_status_connected_with_sync_date(client, db):
    from datetime import datetime, timezone
    auth_client(client, db)
    last_sync = datetime(2024, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
    with patch("app.integrations.amazon.routes_connection.db") as mock_db:
        mock_db.session.scalar.return_value = _fake_conn(last_sync_at=last_sync)
        resp = client.get(f"{BASE}/status")

    data = resp.get_json()
    assert data["connected"] is True
    assert "2024-03-10" in data["last_sync_at"]


# ---------------------------------------------------------------------------
# POST /connect -- nao autenticado
# ---------------------------------------------------------------------------

def test_connect_unauthenticated(client, db):
    resp = client.post(f"{BASE}/connect", json={})
    assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# POST /connect -- conta demo
# ---------------------------------------------------------------------------

def test_connect_demo_account_rejected(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_connection.g") as mock_g:
        mock_g.is_demo = True
        resp = client.post(f"{BASE}/connect", json={"marketplace_id": "X"})

    assert resp.status_code == 403
    data = resp.get_json()
    assert data["ok"] is False
    assert "demo" in data["error"].lower()


# ---------------------------------------------------------------------------
# POST /connect -- campos obrigatorios faltando
# ---------------------------------------------------------------------------

def test_connect_missing_fields_returns_400(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_connection.g") as mock_g:
        mock_g.is_demo = False
        resp = client.post(f"{BASE}/connect", json={"marketplace_id": "A2Q3Y263D00KWC"})

    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert "Faltando" in data["error"]


def test_connect_empty_body_returns_400(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_connection.g") as mock_g:
        mock_g.is_demo = False
        resp = client.post(f"{BASE}/connect", json={})

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /connect -- criacao de nova conexao
# ---------------------------------------------------------------------------

_FULL_PAYLOAD = {
    "marketplace_id": "A2Q3Y263D00KWC",
    "lwa_client_id": "amzn1.application-oa2-client.xxx",
    "lwa_client_secret": "secret",
    "lwa_refresh_token": "Atzr|token",
    "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
    "aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
}


def test_connect_creates_new_connection(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_connection.db") as mock_db, \
         patch("app.integrations.amazon.routes_connection.g") as mock_g:
        mock_g.is_demo = False
        mock_db.session.scalar.return_value = None  # sem conexao existente
        resp = client.post(f"{BASE}/connect", json=_FULL_PAYLOAD)

    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_connect_updates_existing_connection(client, db):
    auth_client(client, db)
    existing_conn = _fake_conn()
    with patch("app.integrations.amazon.routes_connection.db") as mock_db, \
         patch("app.integrations.amazon.routes_connection.g") as mock_g:
        mock_g.is_demo = False
        mock_db.session.scalar.return_value = existing_conn  # ja tem conexao
        resp = client.post(f"{BASE}/connect", json={**_FULL_PAYLOAD, "aws_region": "us-east-1"})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True


# ---------------------------------------------------------------------------
# POST /test -- nao autenticado
# ---------------------------------------------------------------------------

def test_test_connection_unauthenticated(client, db):
    resp = client.post(f"{BASE}/test")
    assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# POST /test -- sem conexao
# ---------------------------------------------------------------------------

def test_test_connection_no_conn(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_connection.db") as mock_db:
        mock_db.session.scalar.return_value = None
        resp = client.post(f"{BASE}/test")

    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False


# ---------------------------------------------------------------------------
# POST /test -- sucesso
# ---------------------------------------------------------------------------

def test_test_connection_success(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_connection.db") as mock_db, \
         patch("app.integrations.amazon.routes_connection.list_orders", return_value=["order1", "order2"]):
        mock_db.session.scalar.return_value = _fake_conn()
        resp = client.post(f"{BASE}/test")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["orders_found"] == 2


# ---------------------------------------------------------------------------
# POST /test -- falha na SP-API
# ---------------------------------------------------------------------------

def test_test_connection_api_failure(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_connection.db") as mock_db, \
         patch("app.integrations.amazon.routes_connection.list_orders",
               side_effect=Exception("SP-API timeout")):
        mock_db.session.scalar.return_value = _fake_conn()
        resp = client.post(f"{BASE}/test")

    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert "Falha" in data["error"]
