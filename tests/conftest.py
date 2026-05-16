import pytest
from app import create_app, db as _db
from app.models.user import User
from app.models.product import Product, ProductHistory
from app.models.pricing import PricingHistory
from app.models.custo_fixo import CustoFixo
from app.models.custo_fixo_history import CustoFixoHistory
from app.models.custo_fixo_pagamento import CustoFixoPagamento
from app.models.notification_settings import NotificationSettings
from app.models.notification_recipient import NotificationRecipient

# Tabelas compatíveis com SQLite (sem schema="public")
SQLITE_TABLES = [
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
    application = create_app("testing")
    with application.app_context():
        yield application


@pytest.fixture(scope="function")
def db(app):
    with app.app_context():
        _db.metadata.create_all(_db.engine, tables=SQLITE_TABLES)
        yield _db
        _db.session.remove()
        _db.metadata.drop_all(_db.engine, tables=SQLITE_TABLES)


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
