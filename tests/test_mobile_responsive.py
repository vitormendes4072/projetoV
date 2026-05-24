"""
Smoke tests para responsividade mobile dos templates principais.

Estes testes não simulam viewport — checam apenas que as classes
Tailwind certas estão presentes nos pontos críticos (toolbars e
cabeçalhos que antes não tinham breakpoints).
"""
from unittest.mock import MagicMock, patch

from tests.conftest import auth_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pagination(items=None):
    items = items or []
    p = MagicMock()
    p.items = items
    p.total = len(items)
    p.page = 1
    p.pages = 1
    p.has_prev = False
    p.has_next = False
    p.iter_pages.return_value = [1]
    return p


# ---------------------------------------------------------------------------
# Header global (base.html)
# ---------------------------------------------------------------------------

def test_header_uses_responsive_padding(client, db):
    """Header autenticado deve ter padding responsivo, não px-10 direto."""
    auth_client(client, db)
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    body = resp.data
    # padding mobile-first: px-4 sm:px-6 lg:px-10
    assert b"px-4 sm:px-6 lg:px-10" in body
    # E não deve mais ter o `px-10 py-3` solto (sem prefixo)
    assert b'border-b-[#e7edf4] px-10 py-3' not in body


# ---------------------------------------------------------------------------
# Toolbar de produtos/lista
# ---------------------------------------------------------------------------

def test_produtos_lista_header_stacks_on_mobile(client, db):
    """Cabeçalho de /produtos deve usar flex-col sm:flex-row."""
    auth_client(client, db)
    resp = client.get("/produtos")
    assert resp.status_code == 200
    body = resp.data
    assert b"flex flex-col sm:flex-row sm:justify-between sm:items-center" in body
    # Toolbar dos 3 botões deve ter flex-wrap
    assert b"flex flex-wrap items-center gap-2" in body


# ---------------------------------------------------------------------------
# Toolbar de pedidos Amazon
# ---------------------------------------------------------------------------

def test_amazon_orders_header_stacks_on_mobile(client, db):
    """Cabeçalho de /integrations/amazon/orders deve usar flex-col sm:flex-row."""
    auth_client(client, db)
    with patch("app.integrations.amazon.routes_orders.db") as mock_db:
        mock_db.paginate.return_value = _make_pagination([])
        mock_db.select.return_value = MagicMock()
        resp = client.get("/integrations/amazon/orders")
    assert resp.status_code == 200
    body = resp.data
    # Cabeçalho stacka em mobile
    assert b"flex flex-col sm:flex-row sm:items-center sm:justify-between" in body
    # Toolbar dos 3 botões deve ter flex-wrap
    assert b'<div class="flex flex-wrap gap-2">' in body
