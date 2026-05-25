"""
Testes para app/integrations/amazon/routes_inventory.py.
Cobre inventory_page (GET) e sync_inventory (POST).
"""
from unittest.mock import MagicMock, patch

from tests.conftest import auth_client

BASE = "/integrations/amazon"
MODULE = "app.integrations.amazon.routes_inventory"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_conn(marketplace_id="A2Q3Y263D00KWC"):
    c = MagicMock()
    c.marketplace_id = marketplace_id
    return c


def _make_pagination(items=None):
    p = MagicMock()
    p.items = items or []
    p.total = len(p.items)
    p.page = 1
    p.pages = 1
    p.has_prev = False
    p.has_next = False
    p.iter_pages.return_value = [1]
    return p


def _fake_snapshot(sku="SKU-A", asin="B001TEST", qty=10):
    s = MagicMock()
    s.seller_sku = sku
    s.asin = asin
    s.fulfillable_qty = qty
    s.reserved_qty = 2
    s.inbound_working_qty = 0
    s.inbound_shipped_qty = 0
    s.inbound_receiving_qty = 0
    s.updated_at = None
    return s


# ---------------------------------------------------------------------------
# Unauthenticated
# ---------------------------------------------------------------------------

def test_inventory_page_unauthenticated(client, db):
    resp = client.get(f"{BASE}/inventory")
    assert resp.status_code in (302, 401)


def test_sync_inventory_unauthenticated(client, db):
    resp = client.post(f"{BASE}/sync_inventory")
    assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# GET /inventory — inventory_page
# ---------------------------------------------------------------------------

def test_inventory_page_empty(client, db):
    auth_client(client, db)
    with patch(f"{MODULE}.db") as mock_db, \
         patch(f"{MODULE}.get_min_stock_map", return_value={}):
        mock_db.select.return_value = MagicMock()
        mock_db.paginate.return_value = _make_pagination([])
        resp = client.get(f"{BASE}/inventory")
    assert resp.status_code == 200


def test_inventory_page_with_snapshots(client, db):
    auth_client(client, db)
    snaps = [_fake_snapshot("SKU-A"), _fake_snapshot("SKU-B")]
    with patch(f"{MODULE}.db") as mock_db, \
         patch(f"{MODULE}.get_min_stock_map", return_value={}):
        mock_db.select.return_value = MagicMock()
        mock_db.paginate.return_value = _make_pagination(snaps)
        resp = client.get(f"{BASE}/inventory")
    assert resp.status_code == 200


def test_inventory_page_with_search_query(client, db):
    auth_client(client, db)
    with patch(f"{MODULE}.db") as mock_db, \
         patch(f"{MODULE}.get_min_stock_map", return_value={}):
        mock_db.select.return_value = MagicMock()
        mock_db.or_.return_value = MagicMock()
        mock_db.paginate.return_value = _make_pagination([_fake_snapshot("SKU-FOUND")])
        resp = client.get(f"{BASE}/inventory?q=SKU-FOUND")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Alertas de reposição — min_stock_map integrado na página
# ---------------------------------------------------------------------------

def test_inventory_alert_banner_shown_when_below_min(client, db):
    """Banner âmbar aparece quando algum SKU está abaixo do min_stock."""
    auth_client(client, db)
    snap = _fake_snapshot("SKU-LOW", qty=3)
    with patch(f"{MODULE}.db") as mock_db, \
         patch(f"{MODULE}.get_min_stock_map", return_value={"SKU-LOW": 5}):
        mock_db.select.return_value = MagicMock()
        mock_db.paginate.return_value = _make_pagination([snap])
        resp = client.get(f"{BASE}/inventory")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "abaixo do mínimo" in body
    assert "Repor" in body


def test_inventory_alert_banner_hidden_when_above_min(client, db):
    """Sem banner quando estoque está acima do min_stock."""
    auth_client(client, db)
    snap = _fake_snapshot("SKU-OK", qty=20)
    with patch(f"{MODULE}.db") as mock_db, \
         patch(f"{MODULE}.get_min_stock_map", return_value={"SKU-OK": 5}):
        mock_db.select.return_value = MagicMock()
        mock_db.paginate.return_value = _make_pagination([snap])
        resp = client.get(f"{BASE}/inventory")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "abaixo do mínimo" not in body
    assert "Repor" not in body


def test_inventory_min_column_present(client, db):
    """Coluna 'Mín.' aparece no cabeçalho da tabela."""
    auth_client(client, db)
    snaps = [_fake_snapshot("SKU-A", qty=5)]
    with patch(f"{MODULE}.db") as mock_db, \
         patch(f"{MODULE}.get_min_stock_map", return_value={"SKU-A": 10}):
        mock_db.select.return_value = MagicMock()
        mock_db.paginate.return_value = _make_pagination(snaps)
        resp = client.get(f"{BASE}/inventory")
    assert resp.status_code == 200
    assert "Mín." in resp.data.decode()


# ---------------------------------------------------------------------------
# POST /sync_inventory
# ---------------------------------------------------------------------------

def test_sync_inventory_no_conn(client, db):
    auth_client(client, db)
    with patch(f"{MODULE}.db") as mock_db:
        mock_db.session.scalar.return_value = None
        resp = client.post(f"{BASE}/sync_inventory")
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert "error" in data


def test_sync_inventory_get_summaries_fails(client, db):
    auth_client(client, db)
    with patch(f"{MODULE}.db") as mock_db, \
         patch(f"{MODULE}.get_inventory_summaries",
               side_effect=RuntimeError("SP-API throttle")):
        mock_db.session.scalar.return_value = _fake_conn()
        resp = client.post(f"{BASE}/sync_inventory")
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False


def test_sync_inventory_success(client, db):
    auth_client(client, db)
    fake_summaries = [{"sellerSku": "SKU-A"}, {"sellerSku": "SKU-B"}]
    with patch(f"{MODULE}.db") as mock_db, \
         patch(f"{MODULE}.get_inventory_summaries", return_value=fake_summaries), \
         patch(f"{MODULE}.upsert_inventory_snapshots", return_value=(2, 0)):
        mock_db.session.scalar.return_value = _fake_conn()
        resp = client.post(f"{BASE}/sync_inventory")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["inserted"] == 2
    assert data["updated"] == 0
    assert data["total"] == 2


def test_sync_inventory_returns_updated_count(client, db):
    auth_client(client, db)
    fake_summaries = [{"sellerSku": "SKU-A"}, {"sellerSku": "SKU-B"}, {"sellerSku": "SKU-C"}]
    with patch(f"{MODULE}.db") as mock_db, \
         patch(f"{MODULE}.get_inventory_summaries", return_value=fake_summaries), \
         patch(f"{MODULE}.upsert_inventory_snapshots", return_value=(1, 2)):
        mock_db.session.scalar.return_value = _fake_conn()
        resp = client.post(f"{BASE}/sync_inventory")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["inserted"] == 1
    assert data["updated"] == 2
    assert data["total"] == 3
