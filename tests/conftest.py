import os

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session as SASession, scoped_session

from app import create_app, db as _db
from app.models.user import User
from app.models.product import Product, ProductHistory
from app.models.pricing import PricingHistory
from app.models.custo_fixo import CustoFixo
from app.models.custo_fixo_history import CustoFixoHistory
from app.models.custo_fixo_pagamento import CustoFixoPagamento
from app.models.notification_settings import NotificationSettings
from app.models.notification_recipient import NotificationRecipient

# TEST_DATABASE_URL is set by CI (GitHub Actions postgres service).
# DATABASE_URL from .env points to production — never used in tests.
# When neither is set, SQLite is used for local iteration without a DB.
_TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")
_USING_PG = bool(_TEST_DB_URL and "postgresql" in _TEST_DB_URL)

# Tables that work on SQLite (no schema="public"). Only used in the SQLite path.
_SQLITE_TABLES = [
    User.__table__,
    Product.__table__,
    ProductHistory.__table__,
    PricingHistory.__table__,
    CustoFixo.__table__,
    CustoFixoHistory.__table__,
    CustoFixoPagamento.__table__,
    NotificationSettings.__table__,
    NotificationRecipient.__table__,
]


@pytest.fixture(scope="session")
def app():
    # Pass PostgreSQL URI via test_config so create_app applies it BEFORE
    # db.init_app() — Flask-SQLAlchemy 3.x creates the engine eagerly in init_app.
    test_cfg = None
    if _USING_PG:
        test_cfg = {
            "SQLALCHEMY_DATABASE_URI": _TEST_DB_URL,
            "SQLALCHEMY_ENGINE_OPTIONS": {},
        }

    application = create_app("testing", test_config=test_cfg)

    with application.app_context():
        if _USING_PG:
            # Full schema including schema="public" Amazon tables
            _db.create_all()
        else:
            # SQLite: FK enforcement + only compatible tables
            @event.listens_for(_db.engine, "connect")
            def _sqlite_fk(conn, _):
                conn.execute("PRAGMA foreign_keys=ON")

            _db.metadata.create_all(_db.engine, tables=_SQLITE_TABLES)

        yield application

        if _USING_PG:
            _db.drop_all()
        else:
            _db.metadata.drop_all(_db.engine, tables=_SQLITE_TABLES)


@pytest.fixture(scope="function")
def db(app):
    """PostgreSQL path: BEGIN → test runs (commits become savepoints) → ROLLBACK.
    SQLite path: drop + recreate tables between tests."""
    with app.app_context():
        if _USING_PG:
            connection = _db.engine.connect()
            transaction = connection.begin()
            original_session = _db.session

            def _session_factory():
                return SASession(bind=connection, join_transaction_mode="create_savepoint")

            _db.session = scoped_session(_session_factory)

            yield _db

            _db.session.remove()
            _db.session = original_session
            transaction.rollback()
            connection.close()
        else:
            yield _db
            _db.session.remove()
            _db.metadata.drop_all(_db.engine, tables=_SQLITE_TABLES)
            _db.metadata.create_all(_db.engine, tables=_SQLITE_TABLES)


@pytest.fixture
def client(app, db):
    return app.test_client()


def make_user(db, email="user@test.com", password="senha123", confirmed=True, name="Teste"):
    user = User(email=email, name=name)
    user.set_password(password)
    user.confirmed = confirmed
    db.session.add(user)
    db.session.commit()
    return user


def login(client, email, password):
    return client.post("/login", data={"email": email, "password": password},
                       follow_redirects=True)


def auth_client(client, db, email="user@test.com", password="senha123"):
    make_user(db, email=email, password=password)
    login(client, email, password)
    return client
