"""
Testes para app/integrations/amazon/routes_sku_links.py.

AmazonSkuLink e AmazonInventorySnapshot usam schema="public".
Todos os acessos ao DB dessas tabelas sao mockados.
Produtos (SQLite) sao criados normalmente via client.
"""
from unittest.mock import MagicMock, patch

from tests.conftest import auth_client, make_user, login


BASE = "/integrations/amazon"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_link(link_id=1, seller_sku="SKU-AMZ", product_id=None):
    link = MagicMock()
    link.id = link_id
    link.amazon_seller_sku = seller_sku
    link.product_id = product_id
    link.marketplace_id = None
    link.asin = None
    return link


# ---------------------------------------------------------------------------
# GET /sku_links -- autenticacao
# ---------------------------------------------------------------------------

def test_sku_links_page_unauthenticated(client, db):
    resp = client.get(f"{BASE}/sku_links")
    assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# GET /sku_links -- renderiza pagina
# ---------------------------------------------------------------------------

def test_sku_links_page_renders(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_sku_links.db") as mock_db:
        mock_db.session.scalars.return_value = MagicMock(__iter__=lambda s: iter([]))
        resp = client.get(f"{BASE}/sku_links")

    assert resp.status_code == 200


def test_sku_links_page_shows_links(client, db):
    auth_client(client, db)
    fake_link = _fake_link(seller_sku="SELLER-SKU-001")
    with patch("app.integrations.amazon.routes_sku_links.db") as mock_db:
        # Primeiro scalars -> products (vazio), segundo -> links, terceiro -> inventory
        mock_db.session.scalars.side_effect = [
            MagicMock(__iter__=lambda s: iter([])),   # products
            MagicMock(__iter__=lambda s: iter([fake_link])),  # links
            MagicMock(__iter__=lambda s: iter([])),   # inventory
        ]
        resp = client.get(f"{BASE}/sku_links")

    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /sku_links/missing -- PostgreSQL-only (raw SQL)
# ---------------------------------------------------------------------------

def test_sku_links_missing_unauthenticated(client, db):
    resp = client.get(f"{BASE}/sku_links/missing")
    assert resp.status_code in (302, 401)


def test_sku_links_missing_returns_json(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_sku_links.db") as mock_db:
        # Simula resultado da query de skus e da query de links
        mock_execute = MagicMock()
        mock_execute.fetchall.side_effect = [
            [("SKU-A", 5, "ASIN001"), ("SKU-B", 3, None)],  # skus
            [("SKU-A",)],  # linked
        ]
        mock_db.session.execute.return_value = mock_execute
        resp = client.get(f"{BASE}/sku_links/missing")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert "missing" in data
    # SKU-A esta linkado, SKU-B nao -> missing_count=1
    assert data["missing_count"] == 1
    assert data["missing"][0]["seller_sku"] == "SKU-B"


def test_sku_links_missing_empty(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_sku_links.db") as mock_db:
        mock_execute = MagicMock()
        mock_execute.fetchall.side_effect = [[], []]
        mock_db.session.execute.return_value = mock_execute
        resp = client.get(f"{BASE}/sku_links/missing")

    data = resp.get_json()
    assert data["missing_count"] == 0
    assert data["missing"] == []


# ---------------------------------------------------------------------------
# POST /sku_links -- upsert
# ---------------------------------------------------------------------------

def test_sku_links_upsert_unauthenticated(client, db):
    resp = client.post(f"{BASE}/sku_links", json={})
    assert resp.status_code in (302, 401)


def test_sku_links_upsert_missing_fields(client, db):
    auth_client(client, db)
    resp = client.post(f"{BASE}/sku_links", json={"amazon_seller_sku": "SKU-X"})
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_sku_links_upsert_missing_sku(client, db):
    auth_client(client, db)
    resp = client.post(f"{BASE}/sku_links", json={"product_id": 1})
    assert resp.status_code == 400


def test_sku_links_upsert_creates_new_link(client, db):
    auth_client(client, db)
    new_link = _fake_link(link_id=42, seller_sku="SELLER-NEW", product_id=1)
    with patch("app.integrations.amazon.routes_sku_links.db") as mock_db:
        mock_db.session.scalar.side_effect = [
            None,        # nao existe link -> cria novo
            None,        # produto sem ASIN -> nao atualiza
        ]
        mock_db.session.add = MagicMock()
        mock_db.session.commit = MagicMock()
        # Para que link.id seja 42 apos o add, precisamos do fake_link
        # Simulamos o comportamento do AmazonSkuLink(...)
        with patch("app.integrations.amazon.routes_sku_links.AmazonSkuLink",
                   return_value=new_link):
            resp = client.post(f"{BASE}/sku_links",
                               json={"amazon_seller_sku": "SELLER-NEW", "product_id": 1})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["id"] == 42


def test_sku_links_upsert_updates_existing_link(client, db):
    auth_client(client, db)
    existing_link = _fake_link(link_id=7, seller_sku="SELLER-OLD", product_id=5)
    with patch("app.integrations.amazon.routes_sku_links.db") as mock_db:
        mock_db.session.scalar.side_effect = [
            existing_link,  # link ja existe
            None,           # produto
        ]
        mock_db.session.add = MagicMock()
        mock_db.session.commit = MagicMock()
        resp = client.post(f"{BASE}/sku_links",
                           json={"amazon_seller_sku": "SELLER-OLD", "product_id": 9})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert existing_link.product_id == 9


def test_sku_links_upsert_with_asin_updates_product(client, db):
    auth_client(client, db)
    new_link = _fake_link(link_id=99, seller_sku="SELLER-ASIN", product_id=3)
    fake_product = MagicMock()
    fake_product.asin = None  # produto sem ASIN ainda
    with patch("app.integrations.amazon.routes_sku_links.db") as mock_db, \
         patch("app.integrations.amazon.routes_sku_links.AmazonSkuLink", return_value=new_link):
        mock_db.session.scalar.side_effect = [
            None,          # nao existe link
            fake_product,  # produto encontrado
        ]
        mock_db.session.add = MagicMock()
        mock_db.session.commit = MagicMock()
        resp = client.post(f"{BASE}/sku_links",
                           json={"amazon_seller_sku": "SELLER-ASIN",
                                 "product_id": 3,
                                 "asin": "B00EXAMPLE1"})

    assert resp.status_code == 200
    # produto teve o ASIN atualizado
    assert fake_product.asin == "B00EXAMPLE1"


# ---------------------------------------------------------------------------
# DELETE /sku_links/<id>
# ---------------------------------------------------------------------------

def test_sku_links_delete_unauthenticated(client, db):
    resp = client.post(f"{BASE}/sku_links/1/delete")
    assert resp.status_code in (302, 401)


def test_sku_links_delete_not_found(client, db):
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_sku_links.db") as mock_db:
        mock_db.session.scalar.return_value = None
        resp = client.post(f"{BASE}/sku_links/999/delete")

    assert resp.status_code == 404
    assert resp.get_json()["ok"] is False


def test_sku_links_delete_success(client, db):
    auth_client(client, db)
    fake_link = _fake_link(link_id=5)
    with patch("app.integrations.amazon.routes_sku_links.db") as mock_db:
        mock_db.session.scalar.return_value = fake_link
        mock_db.session.delete = MagicMock()
        mock_db.session.commit = MagicMock()
        resp = client.post(f"{BASE}/sku_links/5/delete")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    mock_db.session.delete.assert_called_once_with(fake_link)


def test_sku_links_delete_via_post(client, db):
    """Rota aceita POST alem de DELETE."""
    auth_client(client, db)
    fake_link = _fake_link(link_id=8)
    with patch("app.integrations.amazon.routes_sku_links.db") as mock_db:
        mock_db.session.scalar.return_value = fake_link
        mock_db.session.delete = MagicMock()
        mock_db.session.commit = MagicMock()
        resp = client.post(f"{BASE}/sku_links/8/delete")

    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
