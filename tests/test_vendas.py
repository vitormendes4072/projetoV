"""
Tests for the Vendas blueprint and the app/services/vendas.py service.

All Amazon models use schema="public" and are incompatible with SQLite,
so every test that exercises the service mocks app.services.vendas.db
instead of touching the real database.
"""
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import auth_client as _auth_client


@pytest.fixture
def logged_client(client, db):
    return _auth_client(client, db)


# ---------------------------------------------------------------------------
# Authentication guard
# ---------------------------------------------------------------------------

def test_vendas_requires_auth(client):
    resp = client.get("/vendas/")
    assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# Helpers — build mock db for service tests
# ---------------------------------------------------------------------------

def _make_mock_db(dialect_name: str, total: int, receita: float, top_rows=None):
    """Return a mock db object that makes get_vendas_kpis return predictable values."""
    mock_db = MagicMock()
    mock_db.engine.dialect.name = dialect_name

    if dialect_name != "postgresql":
        return mock_db

    # Q1 result — aggregate row
    agg_row = MagicMock()
    agg_row.total = total
    agg_row.receita = receita

    # Q2 result — top SKU rows
    top_rows = top_rows or []

    # Chain: db.session.execute(...).one() for Q1
    # Chain: db.session.execute(...).all() for Q2
    exec_results = [MagicMock(), MagicMock()]
    exec_results[0].one.return_value = agg_row
    exec_results[1].all.return_value = top_rows

    mock_db.session.execute.side_effect = exec_results

    # db.select / db.func / db.func.count — all used in the query builders
    mock_db.select.return_value = MagicMock()
    mock_db.func = MagicMock()

    return mock_db


def _make_sku_row(sku: str, orders: int, qty: int, revenue: float):
    row = MagicMock()
    row.seller_sku = sku
    row.orders = orders
    row.qty = qty
    row.revenue = revenue
    return row


# ---------------------------------------------------------------------------
# Non-PostgreSQL path (SQLite in tests) — always returns empty state
# ---------------------------------------------------------------------------

def test_vendas_empty_state_sqlite(logged_client):
    """When dialect is not postgresql the service returns empty KPIs."""
    with patch("app.services.vendas.db") as mock_db:
        mock_db.engine.dialect.name = "sqlite"
        resp = logged_client.get("/vendas/")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Nenhum pedido sincronizado" in body


# ---------------------------------------------------------------------------
# PostgreSQL path — zero orders
# ---------------------------------------------------------------------------

def test_vendas_postgresql_no_orders(logged_client):
    mock_db = _make_mock_db("postgresql", total=0, receita=0.0)
    with patch("app.services.vendas.db", mock_db):
        resp = logged_client.get("/vendas/")

    assert resp.status_code == 200
    assert "Nenhum pedido sincronizado" in resp.data.decode()


# ---------------------------------------------------------------------------
# PostgreSQL path — with orders and top SKUs
# ---------------------------------------------------------------------------

def test_vendas_with_orders_shows_kpis(logged_client):
    top = [
        _make_sku_row("SKU-A", orders=5, qty=10, revenue=500.0),
        _make_sku_row("SKU-B", orders=3, qty=6,  revenue=300.0),
    ]
    mock_db = _make_mock_db("postgresql", total=8, receita=800.0, top_rows=top)

    with patch("app.services.vendas.db", mock_db):
        resp = logged_client.get("/vendas/")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert "800" in body          # receita_bruta
    assert "SKU-A" in body
    assert "SKU-B" in body
    assert "Nenhum pedido" not in body


def test_vendas_ticket_medio_shown(logged_client):
    top = [_make_sku_row("SKU-X", 4, 4, 400.0)]
    mock_db = _make_mock_db("postgresql", total=4, receita=400.0, top_rows=top)

    with patch("app.services.vendas.db", mock_db):
        resp = logged_client.get("/vendas/")

    assert resp.status_code == 200
    # ticket_medio = 400 / 4 = 100
    assert "100.00" in resp.data.decode()


def test_vendas_top_skus_table_rendered(logged_client):
    top = [_make_sku_row(f"SKU-{i}", orders=i, qty=i * 2, revenue=float(i * 100))
           for i in range(1, 6)]
    mock_db = _make_mock_db("postgresql", total=15, receita=1500.0, top_rows=top)

    with patch("app.services.vendas.db", mock_db):
        resp = logged_client.get("/vendas/")

    body = resp.data.decode()
    assert "Top SKUs por Receita" in body
    assert "SKU-5" in body    # highest revenue row present


# ---------------------------------------------------------------------------
# Period filter
# ---------------------------------------------------------------------------

def test_vendas_period_filter_valid(logged_client):
    """Valid period values must return 200."""
    for period in ("7d", "30d", "90d", "all"):
        # Rebuild mock each iteration — side_effect list is exhausted per request.
        mock_db = _make_mock_db("postgresql", total=0, receita=0.0)
        with patch("app.services.vendas.db", mock_db):
            resp = logged_client.get(f"/vendas/?period={period}")
        assert resp.status_code == 200, f"period={period} should return 200"


def test_vendas_period_filter_invalid_falls_back(logged_client):
    """Invalid period must silently fall back to 30d and return 200."""
    mock_db = _make_mock_db("postgresql", total=0, receita=0.0)
    with patch("app.services.vendas.db", mock_db):
        resp = logged_client.get("/vendas/?period=invalid_value")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Service unit tests — get_vendas_kpis
# ---------------------------------------------------------------------------

def test_service_empty_kpis_on_sqlite():
    from app.services.vendas import get_vendas_kpis

    mock_db = MagicMock()
    mock_db.engine.dialect.name = "sqlite"
    with patch("app.services.vendas.db", mock_db):
        result = get_vendas_kpis(user_id=1, period="30d")

    assert result["total_orders"] == 0
    assert result["receita_bruta"] == 0.0
    assert result["has_amazon_data"] is False
    assert result["top_skus"] == []


def test_service_ticket_medio_zero_orders():
    """ticket_medio must be 0.0 when total_orders is 0 (avoid ZeroDivisionError)."""
    from app.services.vendas import get_vendas_kpis

    mock_db = _make_mock_db("postgresql", total=0, receita=0.0)
    with patch("app.services.vendas.db", mock_db):
        result = get_vendas_kpis(user_id=1, period="30d")

    assert result["ticket_medio"] == 0.0


def test_service_pct_calculation():
    """SKU pct should sum to ~100% when two SKUs split revenue evenly."""
    from app.services.vendas import get_vendas_kpis

    top = [
        _make_sku_row("SKU-A", orders=5, qty=5, revenue=500.0),
        _make_sku_row("SKU-B", orders=5, qty=5, revenue=500.0),
    ]
    mock_db = _make_mock_db("postgresql", total=10, receita=1000.0, top_rows=top)
    with patch("app.services.vendas.db", mock_db):
        result = get_vendas_kpis(user_id=1, period="30d")

    skus = result["top_skus"]
    assert len(skus) == 2
    assert skus[0]["pct"] == 50.0
    assert skus[1]["pct"] == 50.0


# ---------------------------------------------------------------------------
# Menu tile — no longer "Em breve"
# ---------------------------------------------------------------------------

def test_menu_vendas_tile_enabled(logged_client):
    resp = logged_client.get("/menu")
    assert resp.status_code == 200
    body = resp.data.decode()
    # The vendas tile should link to /vendas/ and not carry the "Em breve" badge
    assert "/vendas/" in body
    # "Em breve" should not appear next to the vendas title
    # (other tiles might still have it, so we check the tile description instead)
    assert "Analytics de pedidos Amazon" in body
