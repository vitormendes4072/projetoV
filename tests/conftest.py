import os
import sys

import pytest
from sqlalchemy.orm import Session as SASession, scoped_session
from testcontainers.postgres import PostgresContainer

from app import create_app, db as _db
from app.models.user import User

# Docker Desktop on Windows exposes the daemon via TCP instead of a named pipe
# when running with the WSL2 backend. Set DOCKER_HOST before testcontainers
# tries to connect, unless the caller already set it (e.g., in CI).
if sys.platform == "win32" and "DOCKER_HOST" not in os.environ:
    os.environ["DOCKER_HOST"] = "tcp://localhost:2375"

_PG_IMAGE = "postgres:16-alpine"


@pytest.fixture(scope="session")
def pg_container():
    with PostgresContainer(_PG_IMAGE) as pg:
        yield pg


@pytest.fixture(scope="session")
def app(pg_container):
    db_url = pg_container.get_connection_url()
    application = create_app("testing")
    # Override SQLite defaults from TestingConfig with the real PG container URL.
    # Flask-SQLAlchemy creates the engine lazily (first db.engine access), so
    # updating config here — before any DB operation — is safe.
    application.config["SQLALCHEMY_DATABASE_URI"] = db_url
    application.config.pop("SQLALCHEMY_ENGINE_OPTIONS", None)
    with application.app_context():
        _db.create_all()
        yield application
        _db.drop_all()


@pytest.fixture(scope="function")
def db(app):
    """Isolates each test in a transaction that is rolled back on teardown.

    Uses SQLAlchemy join_transaction_mode="create_savepoint" so that
    session.commit() calls within the test create SAVEPOINT/RELEASE pairs
    instead of real commits. The outer BEGIN is rolled back at the end,
    leaving the DB pristine for the next test — no drop/create overhead.
    """
    with app.app_context():
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
