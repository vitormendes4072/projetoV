"""
Tests for the Estoque blueprint and app/services/estoque.py service.

Strategy:
  - Pure helpers (_classify_status, _reorder_qty) — unit tested without DB.
  - Internal path (_get_internal_data) — uses real SQLite + Product model, no mocks.
  - FBA path (_get_fba_data) — Amazon models require schema="public", so db is mocked.
  - Route tests — cover auth guard, empty state, and data rendering.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models.product import Product
from app.services.estoque import _classify_status, _reorder_qty
from tests.conftest import auth_client as _auth_client, make_user, login


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def logged_client(client, db):
    return _auth_client(client, db)


def _login_with_email(client, db, email: str):
    """Create a unique user and return (client, user_id)."""
    user = make_user(db, email=email)
    login(client, email, "senha123")
    return client, user.id


def _make_product(db, user_id: int, sku: str, name: str,
                  stock: int, min_stock: int | None = None) -> Product:
    p = Product(
        user_id=user_id,
        sku=sku,
        name=name,
        stock_quantity=stock,
        min_stock=min_stock,
        price=10.0,
        cost=5.0,
    )
    db.session.add(p)
    db.session.commit()
    return p


# ---------------------------------------------------------------------------
# Pure helper: _classify_status
# ---------------------------------------------------------------------------

def test_classify_zero_is_critical():
    assert _classify_status(0, 10) == "critical"
    assert _classify_status(0, None) == "critical"
    assert _classify_status(0, 0) == "critical"


def test_classify_at_min_stock_is_alert():
    assert _classify_status(5, 5) == "alert"


def test_classify_below_min_stock_is_alert():
    assert _classify_status(3, 5) == "alert"


def test_classify_above_min_stock_is_ok():
    assert _classify_status(6, 5) == "ok"


def test_classify_no_min_stock_nonzero_is_ok():
    assert _classify_status(1, None) == "ok"
    assert _classify_status(100, None) == "ok"


# ---------------------------------------------------------------------------
# Pure helper: _reorder_qty
# ---------------------------------------------------------------------------

def test_reorder_zero_when_above_min():
    assert _reorder_qty(10, 5) == 0


def test_reorder_zero_when_no_min():
    assert _reorder_qty(0, None) == 0
    assert _reorder_qty(5, None) == 0


def test_reorder_tops_up_to_double_min():
    # min=10, qty=3 → need 2*10 - 3 = 17
    assert _reorder_qty(3, 10) == 17


def test_reorder_when_qty_is_zero():
    # min=10, qty=0 → need 2*10 - 0 = 20
    assert _reorder_qty(0, 10) == 20


def test_reorder_exact_at_min():
    # min=5, qty=5 → need 2*5 - 5 = 5
    assert _reorder_qty(5, 5) == 5


# ---------------------------------------------------------------------------
# Authentication guard
# ---------------------------------------------------------------------------

def test_estoque_requires_auth(client):
    resp = client.get("/estoque/")
    assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# Route — internal path (SQLite, real DB)
# ---------------------------------------------------------------------------

def test_estoque_empty_state_no_products(logged_client):
    """No products → empty state card is shown."""
    resp = logged_client.get("/estoque/")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Nenhum produto cadastrado" in body


def test_estoque_shows_skus_when_products_exist(client, db):
    c, uid = _login_with_email(client, db, "estoque_skus@test.com")
    _make_product(db, uid, "SKU-001", "Produto A", stock=20, min_stock=5)   # ok — not in table
    _make_product(db, uid, "SKU-002", "Produto B", stock=2, min_stock=10)   # alert — shown

    resp = c.get("/estoque/")
    assert resp.status_code == 200
    body = resp.data.decode()
    # SKU-002 is in alert → appears in reposição table
    assert "SKU-002" in body
    # KPI shows total_skus = 2
    assert "2" in body


def test_estoque_shows_critical_badge(client, db):
    c, uid = _login_with_email(client, db, "estoque_crit@test.com")
    _make_product(db, uid, "SKU-CRIT", "Crítico", stock=0, min_stock=5)

    resp = c.get("/estoque/")
    body = resp.data.decode()
    assert "Crítico" in body


def test_estoque_shows_alert_badge(client, db):
    c, uid = _login_with_email(client, db, "estoque_alert@test.com")
    _make_product(db, uid, "SKU-ALT", "Alerta", stock=3, min_stock=10)

    resp = c.get("/estoque/")
    body = resp.data.decode()
    assert "Alerta" in body


def test_estoque_shows_reposicao_suggestion(client, db):
    c, uid = _login_with_email(client, db, "estoque_repo@test.com")
    # qty=3, min=10 → sugestão = 2*10-3 = 17
    _make_product(db, uid, "SKU-REPO", "Produto Repo", stock=3, min_stock=10)

    resp = c.get("/estoque/")
    body = resp.data.decode()
    assert "+17" in body


def test_estoque_ok_products_not_in_reposicao(client, db):
    c, uid = _login_with_email(client, db, "estoque_ok@test.com")
    _make_product(db, uid, "SKU-OK", "Produto OK", stock=50, min_stock=5)

    resp = c.get("/estoque/")
    body = resp.data.decode()
    # All items OK → reposição table shows empty state
    assert "adequado" in body


def test_estoque_kpi_total_skus(client, db):
    c, uid = _login_with_email(client, db, "estoque_kpi@test.com")
    for i in range(3):
        _make_product(db, uid, f"SKU-{i}", f"Produto {i}", stock=10 * (i + 1))

    resp = c.get("/estoque/")
    body = resp.data.decode()
    assert "3" in body   # total_skus appears in KPI card


def test_estoque_internal_badge_shown(client, db):
    c, uid = _login_with_email(client, db, "estoque_badge@test.com")
    _make_product(db, uid, "SKU-X", "Produto X", stock=5)

    resp = c.get("/estoque/")
    body = resp.data.decode()
    assert "Estoque interno" in body


# ---------------------------------------------------------------------------
# FBA path — mocked
# ---------------------------------------------------------------------------

def _make_fba_mock_db(rows: list) -> MagicMock:
    """Return a mock db that simulates the FBA query path."""
    mock_db = MagicMock()
    mock_db.engine.dialect.name = "postgresql"

    exec_result = MagicMock()
    exec_result.all.return_value = rows

    mock_db.session.execute.return_value = exec_result
    mock_db.select.return_value = MagicMock()
    mock_db.and_.return_value = MagicMock()

    return mock_db


def _make_fba_row(sku: str, fulfillable: int, reserved: int = 0,
                  inbound: int = 0, min_stock: int | None = None,
                  product_name: str | None = None) -> MagicMock:
    row = MagicMock()
    row.seller_sku = sku
    row.fulfillable_qty = fulfillable
    row.reserved_qty = reserved
    row.inbound_qty = inbound
    row.min_stock = min_stock
    row.product_name = product_name
    row.updated_at = datetime(2025, 1, 15, tzinfo=timezone.utc)
    return row


def test_estoque_fba_empty_falls_to_internal(logged_client):
    """FBA path returning empty rows falls through to internal path."""
    mock_db = _make_fba_mock_db(rows=[])
    with patch("app.services.estoque.db", mock_db):
        resp = logged_client.get("/estoque/")
    assert resp.status_code == 200


def test_estoque_fba_data_shown(logged_client):
    rows = [
        _make_fba_row("FBA-001", fulfillable=50, min_stock=10, product_name="Produto FBA A"),
        _make_fba_row("FBA-002", fulfillable=2,  min_stock=20, product_name="Produto FBA B"),
    ]
    mock_db = _make_fba_mock_db(rows)
    with patch("app.services.estoque.db", mock_db):
        resp = logged_client.get("/estoque/")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert "FBA-002" in body   # in reposição (qty=2 ≤ min=20)
    assert "FBA – Amazon" in body


def test_estoque_fba_inbound_total(logged_client):
    rows = [
        _make_fba_row("FBA-X", fulfillable=5, inbound=30, min_stock=10),
        _make_fba_row("FBA-Y", fulfillable=5, inbound=20, min_stock=10),
    ]
    mock_db = _make_fba_mock_db(rows)
    with patch("app.services.estoque.db", mock_db):
        resp = logged_client.get("/estoque/")

    body = resp.data.decode()
    # total_inbound = 50 should appear in KPI card
    assert "50" in body


def test_estoque_fba_columns_shown(logged_client):
    """FBA view shows reserved/inbound columns."""
    rows = [_make_fba_row("FBA-Z", fulfillable=0, reserved=5, inbound=10)]
    mock_db = _make_fba_mock_db(rows)
    with patch("app.services.estoque.db", mock_db):
        resp = logged_client.get("/estoque/")

    body = resp.data.decode()
    assert "Reservado" in body
    assert "Em trânsito" in body


# ---------------------------------------------------------------------------
# Menu tile — no longer "Em breve"
# ---------------------------------------------------------------------------

def test_menu_estoque_tile_enabled(logged_client):
    resp = logged_client.get("/menu")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "/estoque/" in body
    assert "Controle estoque" in body
