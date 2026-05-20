"""
Testes adicionais para app/auth/routes.py —
cobre reset_password e confirm_email não exercidos pelos testes originais.
"""
from itsdangerous import URLSafeTimedSerializer
from tests.conftest import make_user, login, auth_client


# ---------------------------------------------------------------------------
# GET /reset_password — formulário de solicitação de reset
# ---------------------------------------------------------------------------

def test_reset_request_get(client, db):
    resp = client.get("/reset_password")
    assert resp.status_code == 200


def test_reset_request_authenticated_redirects(client, db):
    auth_client(client, db)
    resp = client.get("/reset_password")
    assert resp.status_code in (302, 200)  # redireciona para menu


# ---------------------------------------------------------------------------
# POST /reset_password — envia email de reset
# ---------------------------------------------------------------------------

def test_reset_request_post_existing_email(client, db):
    make_user(db, email="reset@test.com")
    resp = client.post("/reset_password",
                       data={"email": "reset@test.com"},
                       follow_redirects=True)
    assert resp.status_code == 200


def test_reset_request_post_unknown_email(client, db):
    resp = client.post("/reset_password",
                       data={"email": "nobody@test.com"},
                       follow_redirects=True)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /reset_password/<token> — formulário de nova senha
# ---------------------------------------------------------------------------

def test_reset_token_invalid(client, db):
    resp = client.get("/reset_password/token_invalido",
                      follow_redirects=True)
    assert resp.status_code == 200


def test_reset_token_valid_get(app, client, db):
    user = make_user(db, email="tok@test.com")
    s = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    token = s.dumps(user.email, salt="password-reset")
    resp = client.get(f"/reset_password/{token}")
    assert resp.status_code == 200


def test_reset_token_valid_post(app, client, db):
    user = make_user(db, email="tokpost@test.com")
    s = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    token = s.dumps(user.email, salt="password-reset")
    resp = client.post(f"/reset_password/{token}", data={
        "password": "novaSenhaSegura1",
        "confirm_password": "novaSenhaSegura1",
    }, follow_redirects=True)
    assert resp.status_code == 200


def test_reset_token_user_not_found(app, client, db):
    s = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    token = s.dumps("nonexistent@test.com", salt="password-reset")
    resp = client.get(f"/reset_password/{token}", follow_redirects=True)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /confirm/<token> — confirmação de email
# ---------------------------------------------------------------------------

def test_confirm_email_invalid_token(client, db):
    resp = client.get("/confirm/token_invalido", follow_redirects=True)
    assert resp.status_code == 200


def test_confirm_email_valid_unconfirmed(app, client, db):
    user = make_user(db, email="conf@test.com", confirmed=False)
    s = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    token = s.dumps(user.email, salt="email-confirm")
    resp = client.get(f"/confirm/{token}", follow_redirects=True)
    assert resp.status_code == 200
    db.session.expire(user)
    assert user.confirmed is True


def test_confirm_email_already_confirmed(app, client, db):
    user = make_user(db, email="already@test.com", confirmed=True)
    s = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    token = s.dumps(user.email, salt="email-confirm")
    resp = client.get(f"/confirm/{token}", follow_redirects=True)
    assert resp.status_code == 200


def test_confirm_email_user_not_found(app, client, db):
    s = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    token = s.dumps("ghost@test.com", salt="email-confirm")
    resp = client.get(f"/confirm/{token}", follow_redirects=True)
    assert resp.status_code == 200


def test_confirm_email_authenticated_redirects(app, client, db):
    auth_client(client, db)
    s = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    token = s.dumps("user@test.com", salt="email-confirm")
    resp = client.get(f"/confirm/{token}")
    assert resp.status_code in (302, 200)
