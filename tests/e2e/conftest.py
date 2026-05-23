"""
Conftest para testes E2E Playwright.

Sobe uma LiveServer Flask em thread separada (porta dinâmica) e oferece
fixtures para semear usuário e dados Amazon antes de cada teste.

Marcadores:
- `e2e`: todos os testes desta pasta. Excluídos por padrão (ver pytest.ini).
  Rode com `pytest -m e2e tests/e2e/`.
- `requires_postgres`: testes que tocam tabelas com schema="public" (Amazon).
  Pulados automaticamente quando TEST_DATABASE_URL não aponta para Postgres.
"""
from __future__ import annotations

import os
import socket
import tempfile
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterator
from uuid import uuid4

import pytest
from werkzeug.serving import make_server

from app import create_app, db as _db
from app.models.user import User

_TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")
_USING_PG = bool(_TEST_DB_URL and "postgresql" in _TEST_DB_URL)


pytestmark = pytest.mark.e2e


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _LiveServer:
    """Wrapper minimalista para subir Flask em thread."""

    def __init__(self, app, host: str = "127.0.0.1", port: int | None = None):
        self.host = host
        self.port = port or _free_port()
        self._server = make_server(host, self.port, app, threaded=True)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> None:
        self._thread.start()
        # Aguarda o servidor aceitar conexões
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                with socket.create_connection((self.host, self.port), timeout=0.5):
                    return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("LiveServer não iniciou em 5s")

    def stop(self) -> None:
        self._server.shutdown()
        self._thread.join(timeout=2)


# ---------------------------------------------------------------------------
# Fixtures de aplicação
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def e2e_app():
    """App Flask em modo testing. Usa Postgres se TEST_DATABASE_URL apontar para ele;
    caso contrário SQLite file-based (in-memory não funciona cross-thread com
    LiveServer em thread separada)."""
    test_cfg = {
        # Desliga CSRF — Playwright preenche forms e flag de testing já controla o ambiente.
        "WTF_CSRF_ENABLED": False,
        "SERVER_NAME": None,
    }

    tmp_db_path: Path | None = None
    if _USING_PG:
        test_cfg["SQLALCHEMY_DATABASE_URI"] = _TEST_DB_URL
        test_cfg["SQLALCHEMY_ENGINE_OPTIONS"] = {}
    else:
        # File-based SQLite com check_same_thread=False para compartilhar entre
        # thread principal (fixtures) e thread do LiveServer.
        tmp_dir = tempfile.mkdtemp(prefix="ventregaz_e2e_")
        tmp_db_path = Path(tmp_dir) / "e2e.db"
        test_cfg["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_db_path}"
        test_cfg["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "connect_args": {"check_same_thread": False},
        }

    application = create_app("testing", test_config=test_cfg)

    with application.app_context():
        if _USING_PG:
            _db.create_all()
        else:
            from tests.conftest import _SQLITE_TABLES
            _db.metadata.create_all(_db.engine, tables=_SQLITE_TABLES)

    yield application

    with application.app_context():
        if _USING_PG:
            _db.drop_all()
        else:
            from tests.conftest import _SQLITE_TABLES
            _db.metadata.drop_all(_db.engine, tables=_SQLITE_TABLES)

    # Cleanup do arquivo SQLite temporário
    if tmp_db_path and tmp_db_path.exists():
        try:
            tmp_db_path.unlink()
            tmp_db_path.parent.rmdir()
        except OSError:
            pass


@pytest.fixture(scope="session")
def live_server(e2e_app) -> Iterator[_LiveServer]:
    server = _LiveServer(e2e_app)
    server.start()
    yield server
    server.stop()


@pytest.fixture
def app_ctx(e2e_app):
    """Contexto de aplicação para os seeders manipularem o banco diretamente."""
    with e2e_app.app_context():
        yield e2e_app


# ---------------------------------------------------------------------------
# Cleanup por teste — limpa as tabelas que cada teste pode mexer
# ---------------------------------------------------------------------------

@pytest.fixture
def clean_db(app_ctx):
    """Limpa tabelas críticas antes de cada teste para isolamento."""
    from app.models.user import User
    from app.models.product import Product, ProductHistory
    from app.models.pricing import PricingHistory

    # PG-only models — só importa se estiver em Postgres
    if _USING_PG:
        from app.models.amazon import (
            AmazonConnection, AmazonOrder, AmazonOrderItem,
        )
        from app.models.amazon_finances import AmazonFinancialEvent

        _db.session.query(AmazonFinancialEvent).delete()
        _db.session.query(AmazonOrderItem).delete()
        _db.session.query(AmazonOrder).delete()
        _db.session.query(AmazonConnection).delete()

    _db.session.query(PricingHistory).delete()
    _db.session.query(ProductHistory).delete()
    _db.session.query(Product).delete()
    _db.session.query(User).delete()
    _db.session.commit()
    yield _db
    _db.session.rollback()


# ---------------------------------------------------------------------------
# Seeders de teste
# ---------------------------------------------------------------------------

def _make_user(email="e2e@test.com", password="senha123", name="E2E User"):
    u = User(email=email, name=name)
    u.set_password(password)
    u.confirmed = True
    _db.session.add(u)
    _db.session.commit()
    return u


@pytest.fixture
def seeded_user(clean_db):
    """Usuário confirmado padrão para login nos testes E2E."""
    return _make_user()


@pytest.fixture
def seeded_amazon_data(clean_db, seeded_user):
    """Cria AmazonConnection + 2 pedidos + 1 evento financeiro.

    Só disponível em Postgres (tabelas Amazon usam schema="public").
    Testes que dependem dela devem usar @pytest.mark.requires_postgres.
    """
    if not _USING_PG:
        pytest.skip("seeded_amazon_data requer Postgres (schema='public')")

    from app.models.amazon import AmazonConnection, AmazonOrder, AmazonOrderItem
    from app.models.amazon_finances import AmazonFinancialEvent

    # Seta colunas _enc diretamente (None) para não chamar encrypt(), que exige
    # CREDENTIALS_ENCRYPTION_KEY. Os testes E2E não fazem chamadas reais à SP-API,
    # então as credenciais cifradas não precisam existir — só a linha no banco.
    conn = AmazonConnection(
        id=uuid4(),
        user_id=seeded_user.id,
        marketplace_id="A2Q3Y263D00KWC",
        seller_id="A1FAKESELLERID",
        lwa_client_id="amzn1.application-oa2-client.fake",
        lwa_client_secret_enc=None,
        lwa_refresh_token_enc=None,
        aws_access_key_id="AKIA_FAKE_KEY",
        aws_secret_access_key_enc=None,
        aws_region="us-east-1",
    )
    _db.session.add(conn)

    order1 = AmazonOrder(
        user_id=seeded_user.id,
        amazon_order_id="111-E2E-0001",
        marketplace_id="A2Q3Y263D00KWC",
        purchase_date=datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc),
        order_status="Shipped",
        currency="BRL",
        order_total_amount=Decimal("150.00"),
        raw_json={"AmazonOrderId": "111-E2E-0001", "OrderStatus": "Shipped"},
    )
    order2 = AmazonOrder(
        user_id=seeded_user.id,
        amazon_order_id="111-E2E-0002",
        marketplace_id="A2Q3Y263D00KWC",
        purchase_date=datetime(2026, 5, 2, 14, 30, tzinfo=timezone.utc),
        order_status="Pending",
        currency="BRL",
        order_total_amount=Decimal("89.90"),
        raw_json={"AmazonOrderId": "111-E2E-0002", "OrderStatus": "Pending"},
    )
    _db.session.add_all([order1, order2])
    _db.session.flush()

    item1 = AmazonOrderItem(
        user_id=seeded_user.id,
        amazon_order_id="111-E2E-0001",
        seller_sku="SKU-E2E-A",
        asin="B0E2EFAKE1",
        quantity=2,
        item_price=Decimal("75.00"),
        currency="BRL",
        raw_json={"SellerSKU": "SKU-E2E-A"},
    )
    _db.session.add(item1)

    fin_event = AmazonFinancialEvent(
        user_id=seeded_user.id,
        posted_date=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        amazon_order_id="111-E2E-0001",
        event_type="ShipmentEvent",
        amount=Decimal("130.00"),
        currency="BRL",
        fingerprint="e2efake_fingerprint_001",
        raw_json={
            "AmazonOrderId": "111-E2E-0001",
            "PostedDate": "2026-05-01T12:00:00Z",
            "ShipmentItemList": [{
                "SellerSKU": "SKU-E2E-A",
                "QuantityShipped": 2,
                "ItemChargeList": [{"ChargeType": "Principal",
                                    "ChargeAmount": {"CurrencyAmount": 150.0, "CurrencyCode": "BRL"}}],
                "ItemFeeList": [{"FeeType": "FBAPerUnitFulfillmentFee",
                                 "FeeAmount": {"CurrencyAmount": -10.0, "CurrencyCode": "BRL"}},
                                {"FeeType": "Commission",
                                 "FeeAmount": {"CurrencyAmount": -10.0, "CurrencyCode": "BRL"}}],
            }],
        },
    )
    _db.session.add(fin_event)
    _db.session.commit()

    return {
        "user": seeded_user,
        "connection": conn,
        "orders": [order1, order2],
        "financial_event": fin_event,
    }


# ---------------------------------------------------------------------------
# Helpers Playwright (login via UI real)
# ---------------------------------------------------------------------------

def login_via_ui(page, live_server_url: str, email: str, password: str) -> None:
    """Faz login pela página /login (usado pela maioria dos testes E2E)."""
    page.goto(f"{live_server_url}/login")
    page.fill('input[name="email"]', email)
    page.fill('input[name="password"]', password)
    page.click('input[type="submit"]')
    page.wait_for_url(lambda url: "/login" not in url, timeout=5000)


# ---------------------------------------------------------------------------
# Playwright config — browser context com viewport razoável
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {**browser_context_args, "viewport": {"width": 1280, "height": 800}}
