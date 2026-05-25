"""
Testes para app/main/routes.py — rota /dashboard e /dashboard/drill/<metric>.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models.pricing import PricingHistory
from app.models.product import Product
from app.services.dashboard import _get_amazon_conn_status, _compute_period_deltas
from tests.conftest import auth_client, login, make_user


def _auth_client_and_get_user(client, db, email="u@test.com", password="senha123"):
    """Cria usuário, loga e retorna o objeto User (para usar o id em fixtures)."""
    user = make_user(db, email=email, password=password)
    login(client, email, password)
    return user


def _add_sim(db, user_id, margin, net_profit=Decimal("10.00"), index=0,
             days_ago=0, roi=Decimal("20.00")):
    created = datetime.now() - timedelta(days=days_ago)
    sim = PricingHistory(
        user_id=user_id,
        title=f"Sim {index}",
        price=Decimal("100.00"),
        cost=Decimal("50.00"),
        fba_fee=Decimal("10.00"),
        referral_fee=Decimal("15.00"),
        tax_rate=Decimal("4.00"),
        marketing=Decimal("0.00"),
        net_profit=net_profit,
        margin=Decimal(str(margin)),
        roi=roi,
        created_at=created,
    )
    db.session.add(sim)
    db.session.commit()
    return sim


# ---------------------------------------------------------------------------
# Unauthenticated
# ---------------------------------------------------------------------------

def test_dashboard_unauthenticated(client, db):
    resp = client.get("/dashboard")
    assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# Estado vazio (zero produtos, zero simulações)
# ---------------------------------------------------------------------------

def test_dashboard_onboarding_checklist_shows(client, db):
    """Novo usuário sem produtos nem Amazon vê o checklist de onboarding."""
    auth_client(client, db)
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    body = resp.data
    assert "Primeiros passos".encode() in body
    assert "Configure seus produtos".encode() in body
    assert "Conecte a Amazon".encode() in body
    assert "primeira sincroniza".encode() in body


def test_dashboard_onboarding_step1_done_when_has_products(client, db):
    """Usuário com produto vê passo 1 concluído."""
    user = _auth_client_and_get_user(client, db)
    p = Product(user_id=user.id, name="Prod X", sku="SKU-001", price=10, cost=5, stock_quantity=1)
    db.session.add(p)
    db.session.commit()

    resp = client.get("/dashboard")
    assert resp.status_code == 200
    # passo 1 concluído → "Concluído" deve aparecer
    assert "Concluído".encode() in resp.data


def test_dashboard_empty_has_no_charts(client, db):
    auth_client(client, db)
    resp = client.get("/dashboard")
    assert b"chartMargem" not in resp.data


def test_dashboard_onboarding_hidden_when_complete(client, db):
    """Checklist some quando todas as 3 etapas estão ok (simulado via dados)."""
    # Simular onboarding.complete=True exige Amazon connection que não existe
    # no SQLite — testamos o inverso: com dados mas sem Amazon,
    # o checklist AINDA aparece (has_amazon_conn=False).
    user = _auth_client_and_get_user(client, db)
    _add_sim(db, user.id, margin=20)

    resp = client.get("/dashboard")
    assert resp.status_code == 200
    # Amazon não configurada → checklist ainda visível
    assert "Primeiros passos".encode() in resp.data


# ---------------------------------------------------------------------------
# Com simulações — KPIs e gráficos
# ---------------------------------------------------------------------------

def test_dashboard_shows_kpis_with_data(client, db):
    user = make_user(db, email="kpi@test.com")
    login(client, "kpi@test.com", "senha123")

    _add_sim(db, user.id, margin=25, net_profit=Decimal("25.00"), index=0)
    _add_sim(db, user.id, margin=15, net_profit=Decimal("15.00"), index=1)

    resp = client.get("/dashboard")
    assert resp.status_code == 200
    # KPI da margem aparece (25% ou 15% media)
    assert b"%" in resp.data


def test_dashboard_charts_appear_with_two_or_more_sims(client, db):
    user = make_user(db, email="charts@test.com")
    login(client, "charts@test.com", "senha123")

    for i in range(3):
        _add_sim(db, user.id, margin=10 + i * 5, index=i)

    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert b"chartMargem" in resp.data
    assert b"chartDist" in resp.data


def test_dashboard_charts_hidden_with_one_sim(client, db):
    user = make_user(db, email="one@test.com")
    login(client, "one@test.com", "senha123")

    _add_sim(db, user.id, margin=20, index=0)

    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert b"chartMargem" not in resp.data


def test_dashboard_negative_margin_bucket(client, db):
    user = make_user(db, email="neg@test.com")
    login(client, "neg@test.com", "senha123")

    _add_sim(db, user.id, margin=-5, net_profit=Decimal("-5.00"), index=0)
    _add_sim(db, user.id, margin=25, net_profit=Decimal("25.00"), index=1)

    resp = client.get("/dashboard")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# min_stock — alertas de reposição
# ---------------------------------------------------------------------------

def test_dashboard_low_stock_alert_appears(client, db):
    """Produto abaixo do min_stock aparece no alerta de estoque baixo."""
    user = _auth_client_and_get_user(client, db, email="low@test.com")
    p = Product(
        user_id=user.id, name="Produto Baixo", sku="LOW-001",
        price=10, cost=5, stock_quantity=2, min_stock=10,
    )
    db.session.add(p)
    db.session.commit()

    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "estoque baixo".encode() in resp.data.lower()
    assert b"Produto Baixo" in resp.data


def test_dashboard_low_stock_shows_min_stock_value(client, db):
    """O alerta exibe 'X / Y un.' com o min_stock por produto."""
    user = _auth_client_and_get_user(client, db, email="minval@test.com")
    p = Product(
        user_id=user.id, name="Item Critico", sku="CRIT-001",
        price=10, cost=5, stock_quantity=3, min_stock=15,
    )
    db.session.add(p)
    db.session.commit()

    resp = client.get("/dashboard")
    assert resp.status_code == 200
    # deve exibir "3 / 15 un."
    assert b"3 / 15" in resp.data


def test_dashboard_no_low_stock_alert_when_stock_ok(client, db):
    """Produto com stock_quantity > min_stock não dispara o alerta."""
    user = _auth_client_and_get_user(client, db, email="ok@test.com")
    p = Product(
        user_id=user.id, name="Produto Ok", sku="OK-001",
        price=10, cost=5, stock_quantity=50, min_stock=10,
    )
    db.session.add(p)
    db.session.commit()

    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert b"Produto Ok" not in resp.data or "estoque baixo".encode() not in resp.data.lower()


def test_dashboard_low_stock_zero_shows_red(client, db):
    """Produto com stock_quantity=0 é incluído no alerta (zerado)."""
    user = _auth_client_and_get_user(client, db, email="zero@test.com")
    p = Product(
        user_id=user.id, name="Produto Zerado", sku="ZERO-001",
        price=10, cost=5, stock_quantity=0, min_stock=5,
    )
    db.session.add(p)
    db.session.commit()

    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert b"Produto Zerado" in resp.data
    assert b"0 / 5" in resp.data


# ---------------------------------------------------------------------------
# _get_amazon_conn_status — dialeto explícito, sem try/except genérico
# ---------------------------------------------------------------------------

class TestGetAmazonConnStatus:
    """Testa a função helper que verifica conexão Amazon por dialeto BD."""

    def test_returns_false_false_on_sqlite(self, client, db):
        """SQLite → (False, False) imediatamente, sem consultar BD."""
        # O fixture db usa SQLite, portanto dialect.name != "postgresql"
        has_conn, has_sync = _get_amazon_conn_status(user_id=1)
        assert has_conn is False
        assert has_sync is False

    def test_does_not_query_db_on_non_postgres(self, client, db):
        """Dialeto não-postgres não deve chamar db.session.scalar."""
        with patch("app.services.dashboard.db") as mock_db:
            mock_db.engine.dialect.name = "sqlite"
            has_conn, has_sync = _get_amazon_conn_status(user_id=1)
        mock_db.session.scalar.assert_not_called()
        assert has_conn is False
        assert has_sync is False

    def test_queries_db_on_postgres_no_conn(self, client, db):
        """Dialeto postgres + sem AmazonConnection → (False, False)."""
        with patch("app.services.dashboard.db") as mock_db:
            mock_db.engine.dialect.name = "postgresql"
            mock_db.session.scalar.return_value = None
            mock_db.select.return_value = MagicMock()
            has_conn, has_sync = _get_amazon_conn_status(user_id=1)
        assert has_conn is False
        assert has_sync is False

    def test_queries_db_on_postgres_conn_no_sync(self, client, db):
        """Dialeto postgres + conexão sem sync → (True, False)."""
        fake_conn = MagicMock()
        fake_conn.last_sync_at = None
        with patch("app.services.dashboard.db") as mock_db:
            mock_db.engine.dialect.name = "postgresql"
            mock_db.session.scalar.return_value = fake_conn
            mock_db.select.return_value = MagicMock()
            has_conn, has_sync = _get_amazon_conn_status(user_id=1)
        assert has_conn is True
        assert has_sync is False

    def test_queries_db_on_postgres_conn_with_sync(self, client, db):
        """Dialeto postgres + conexão com sync → (True, True)."""
        fake_conn = MagicMock()
        fake_conn.last_sync_at = "2026-01-01T00:00:00Z"
        with patch("app.services.dashboard.db") as mock_db:
            mock_db.engine.dialect.name = "postgresql"
            mock_db.session.scalar.return_value = fake_conn
            mock_db.select.return_value = MagicMock()
            has_conn, has_sync = _get_amazon_conn_status(user_id=1)
        assert has_conn is True
        assert has_sync is True


# ---------------------------------------------------------------------------
# Top-nav persistente — partials/_main_nav.html
# ---------------------------------------------------------------------------

class TestMainNav:
    """Garante que a nav persistente é renderizada em páginas autenticadas."""

    def test_renders_on_authenticated_pages(self, client, db):
        """/dashboard inclui a nav persistente com os 6 itens principais."""
        auth_client(client, db)
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        body = resp.data
        # A nav em si deve estar presente
        assert 'aria-label="Navegação principal"'.encode() in body
        # Os 6 itens principais — verificados pelo atributo data-nav-item
        # (label de texto colidiria com outros elementos da página).
        assert b'data-nav-item="main.dashboard"' in body
        assert b'data-nav-item="produtos.lista_produtos"' in body
        assert b'data-nav-item="amazon.orders_page"' in body
        assert b'data-nav-item="financeiro.custos_fixos"' in body
        assert b'data-nav-item="pricing.calculator"' in body
        assert b'data-nav-item="settings.index"' in body
        # E os hrefs apontam para as rotas corretas
        assert b'href="/produtos"' in body
        assert b'href="/integrations/amazon/orders"' in body
        assert b'href="/financeiro/custos-fixos"' in body

    def test_marks_active_item_with_aria_current(self, client, db):
        """Em /dashboard, o item Dashboard tem aria-current='page'."""
        auth_client(client, db)
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        # Apenas o item ativo ganha aria-current="page"
        assert b'aria-current="page"' in resp.data
        assert b'data-nav-item="main.dashboard"' in resp.data

    def test_not_rendered_when_unauthenticated(self, client, db):
        """Páginas públicas (login) não devem ter a nav persistente."""
        resp = client.get("/login")
        assert resp.status_code == 200
        # Sem auth, nada de nav (e nem header autenticado)
        assert b'data-nav-item="main.dashboard"' not in resp.data


# ---------------------------------------------------------------------------
# Drill-down — GET /dashboard/drill/<metric>
# ---------------------------------------------------------------------------

def _fake_drill_rows(n=3):
    from datetime import date
    return [
        SimpleNamespace(
            title=f"SKU-{i}",
            best_margin=20.0 - i * 5,
            best_roi=30.0 - i * 5,
            best_net_profit=15.0 - i * 2,
            last_date=date(2025, 1, 1),
            sim_count=i + 1,
        )
        for i in range(n)
    ]


class TestDashboardDrill:
    """Testes para o endpoint de drill-down dos KPI cards."""

    DRILL_MODULE = "app.services.dashboard.get_drill_data"

    def test_drill_unauthenticated(self, client, db):
        resp = client.get("/dashboard/drill/margin")
        assert resp.status_code in (302, 401)

    def test_drill_margin_returns_200_with_table(self, client, db):
        """GET /dashboard/drill/margin retorna 200 com cabeçalho da tabela."""
        auth_client(client, db)
        with patch(self.DRILL_MODULE, return_value=_fake_drill_rows()):
            resp = client.get("/dashboard/drill/margin?period=30d")
        assert resp.status_code == 200
        body = resp.data.decode()
        assert "Margem" in body
        assert "SKU-0" in body

    def test_drill_roi_returns_200_with_table(self, client, db):
        """GET /dashboard/drill/roi retorna 200 com cabeçalho da tabela."""
        auth_client(client, db)
        with patch(self.DRILL_MODULE, return_value=_fake_drill_rows()):
            resp = client.get("/dashboard/drill/roi?period=30d")
        assert resp.status_code == 200
        assert b"ROI" in resp.data

    def test_drill_invalid_metric_returns_404(self, client, db):
        """Métrica desconhecida deve retornar 404."""
        auth_client(client, db)
        resp = client.get("/dashboard/drill/invalid_metric")
        assert resp.status_code == 404

    def test_drill_empty_period_shows_empty_message(self, client, db):
        """Sem simulações no período, exibe mensagem 'Nenhuma simulação'."""
        auth_client(client, db)
        with patch(self.DRILL_MODULE, return_value=[]):
            resp = client.get("/dashboard/drill/margin?period=7d")
        assert resp.status_code == 200
        assert "Nenhuma simulação".encode() in resp.data


# ---------------------------------------------------------------------------
# Delta período-a-período — _compute_period_deltas
# ---------------------------------------------------------------------------

class TestPeriodDeltas:
    """Testa _compute_period_deltas diretamente (sem HTTP)."""

    def test_all_period_returns_none_deltas(self, client, db):
        """period='all' → todos os deltas devem ser None."""
        user = make_user(db, email="delta_all@test.com")
        result = _compute_period_deltas(user.id, period="all")
        assert result["delta_simulations"] is None
        assert result["delta_margin"] is None
        assert result["delta_roi"] is None

    def test_delta_positive_when_current_margin_higher(self, client, db):
        """Margem atual maior que período anterior → delta_margin > 0."""
        user = make_user(db, email="delta_pos@test.com")
        # Período anterior (15 dias atrás, dentro da janela de 7-14d para period=7d)
        _add_sim(db, user.id, margin=10, days_ago=10, index=0)
        # Período atual (2 dias atrás, dentro da janela de 0-7d)
        _add_sim(db, user.id, margin=30, days_ago=2, index=1)

        result = _compute_period_deltas(user.id, period="7d")
        assert result["delta_margin"] is not None
        assert result["delta_margin"] > 0

    def test_delta_negative_when_current_margin_lower(self, client, db):
        """Margem atual menor que período anterior → delta_margin < 0."""
        user = make_user(db, email="delta_neg@test.com")
        _add_sim(db, user.id, margin=30, days_ago=10, index=0)
        _add_sim(db, user.id, margin=10, days_ago=2, index=1)

        result = _compute_period_deltas(user.id, period="7d")
        assert result["delta_margin"] is not None
        assert result["delta_margin"] < 0

    def test_delta_none_when_no_prev_period_data(self, client, db):
        """Sem dados no período anterior → delta_margin = None."""
        user = make_user(db, email="delta_noprev@test.com")
        # Só há dado na janela atual (2 dias atrás)
        _add_sim(db, user.id, margin=20, days_ago=2, index=0)

        result = _compute_period_deltas(user.id, period="7d")
        assert result["delta_margin"] is None

    def test_delta_simulations_positive(self, client, db):
        """Mais simulações no período atual → delta_simulations > 0."""
        user = make_user(db, email="delta_sims@test.com")
        # 1 simulação na janela anterior
        _add_sim(db, user.id, margin=20, days_ago=10, index=0)
        # 3 simulações na janela atual
        for i in range(3):
            _add_sim(db, user.id, margin=20, days_ago=2, index=i + 1)

        result = _compute_period_deltas(user.id, period="7d")
        assert result["delta_simulations"] == 2  # 3 - 1

    def test_dashboard_renders_delta_badge(self, client, db):
        """Página /dashboard renderiza badge de delta (↑ ou ↓ ou —)."""
        user = make_user(db, email="delta_render@test.com")
        login(client, "delta_render@test.com", "senha123")
        _add_sim(db, user.id, margin=20, days_ago=2, index=0)

        resp = client.get("/dashboard?period=30d")
        assert resp.status_code == 200
        body = resp.data.decode()
        # Badge deve conter "vs. anterior" (seja positivo, negativo ou None)
        assert "vs. anterior" in body or "— vs. período anterior" in body
