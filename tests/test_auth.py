from app.models.user import User
from tests.conftest import make_user, login


def test_register_ok(client, db):
    r = client.post("/register", data={
        "name": "Novo User",
        "email": "novo@test.com",
        "password": "senha123",
        "confirm_password": "senha123",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert User.query.filter_by(email="novo@test.com").first() is not None


def test_register_duplicate_email(client, db):
    make_user(db, email="dup@test.com")
    r = client.post("/register", data={
        "name": "Outro",
        "email": "dup@test.com",
        "password": "senha123",
        "confirm_password": "senha123",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert User.query.filter_by(email="dup@test.com").count() == 1


def test_login_ok(client, db):
    make_user(db, email="ok@test.com", password="senha123")
    r = login(client, "ok@test.com", "senha123")
    assert r.status_code == 200
    assert r.request.path == "/menu"


def test_login_wrong_password(client, db):
    make_user(db, email="wrong@test.com", password="senha123")
    r = login(client, "wrong@test.com", "errada")
    assert r.status_code == 200
    assert r.request.path == "/login"


def test_login_unconfirmed(client, db):
    make_user(db, email="unconf@test.com", password="senha123", confirmed=False)
    r = login(client, "unconf@test.com", "senha123")
    assert r.status_code == 200
    assert r.request.path == "/login"


def test_logout(client, db):
    make_user(db, email="logout@test.com", password="senha123")
    login(client, "logout@test.com", "senha123")
    r = client.get("/logout", follow_redirects=True)
    assert r.status_code == 200
    assert r.request.path == "/login"
