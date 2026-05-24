"""
Testes para app/settings/routes.py.
"""
from itsdangerous import URLSafeTimedSerializer
from tests.conftest import auth_client, make_user, login


# ---------------------------------------------------------------------------
# Unauthenticated
# ---------------------------------------------------------------------------

def test_settings_unauthenticated(client, db):
    resp = client.get("/settings")
    assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# GET /settings — renderiza página com formulários preenchidos
# ---------------------------------------------------------------------------

def test_settings_get_renders(client, db):
    auth_client(client, db)
    resp = client.get("/settings")
    assert resp.status_code == 200


def test_settings_get_prefills_user_data(client, db):
    auth_client(client, db, email="fill@test.com")
    resp = client.get("/settings")
    assert b"fill@test.com" in resp.data


# ---------------------------------------------------------------------------
# POST /settings — trocar senha
# ---------------------------------------------------------------------------

def test_settings_change_password_wrong_current(client, db):
    auth_client(client, db)
    resp = client.post("/settings", data={
        "submit_password": "1",
        "current_password": "senha_errada",
        "new_password": "novaSenha99",
        "confirm_password": "novaSenha99",
    }, follow_redirects=True)
    assert resp.status_code == 200


def test_settings_change_password_success(client, db):
    auth_client(client, db)
    resp = client.post("/settings", data={
        "submit_password": "1",
        "current_password": "senha123",
        "new_password": "novaSenha99",
        "confirm_password": "novaSenha99",
    }, follow_redirects=True)
    assert resp.status_code == 200


def test_settings_change_password_mismatch(client, db):
    auth_client(client, db)
    resp = client.post("/settings", data={
        "submit_password": "1",
        "current_password": "senha123",
        "new_password": "novaSenha99",
        "confirm_password": "outraSenha99",
    }, follow_redirects=True)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /settings — dados tributários
# ---------------------------------------------------------------------------

def test_settings_business_update_success(client, db):
    auth_client(client, db)
    resp = client.post("/settings", data={
        "submit_business": "1",
        "tax_regime": "simples",
        "default_tax_rate": "4.0",
    }, follow_redirects=True)
    assert resp.status_code == 200


def test_settings_business_update_mei(client, db):
    auth_client(client, db)
    resp = client.post("/settings", data={
        "submit_business": "1",
        "tax_regime": "mei",
        "default_tax_rate": "0.0",
    }, follow_redirects=True)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /settings — atualizar nome
# ---------------------------------------------------------------------------

def test_settings_update_name_success(client, db):
    auth_client(client, db)
    resp = client.post("/settings", data={
        "submit": "1",
        "name": "Novo Nome",
        "email": "user@test.com",
        "current_password": "senha123",
    }, follow_redirects=True)
    assert resp.status_code == 200


def test_settings_update_name_wrong_password(client, db):
    auth_client(client, db)
    resp = client.post("/settings", data={
        "submit": "1",
        "name": "Novo Nome",
        "email": "user@test.com",
        "current_password": "senha_errada",
    }, follow_redirects=True)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /settings/confirm_email/<token> — fluxo de confirmação de email
# ---------------------------------------------------------------------------

def test_confirm_email_invalid_token(client, db):
    auth_client(client, db)
    resp = client.get("/settings/confirm_email/token_invalido",
                      follow_redirects=True)
    assert resp.status_code == 200


def test_confirm_email_valid_token(app, client, db):
    auth_client(client, db)
    s = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    token = s.dumps({"new_email": "newemail@test.com", "user_id": 1},
                    salt="email-update")
    resp = client.get(f"/settings/confirm_email/{token}",
                      follow_redirects=True)
    assert resp.status_code == 200


def test_confirm_email_already_in_use(app, client, db):
    # Cria dois usuários: o token aponta para o email do segundo
    u1 = make_user(db, email="a@test.com")
    make_user(db, email="taken@test.com")
    login(client, "a@test.com", "senha123")

    s = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    token = s.dumps({"new_email": "taken@test.com", "user_id": u1.id},
                    salt="email-update")
    resp = client.get(f"/settings/confirm_email/{token}",
                      follow_redirects=True)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# UX: modal unificado + senha inline
# ---------------------------------------------------------------------------

def test_password_modal_removed(client, db):
    """O modal escuro de senha (#passwordModal) não deve mais existir."""
    auth_client(client, db)
    resp = client.get("/settings")
    assert resp.status_code == 200
    assert b'id="passwordModal"' not in resp.data


def test_password_card_has_inline_current_password(client, db):
    """Campo 'Senha Atual' deve estar inline no card, não escondido em modal."""
    auth_client(client, db)
    resp = client.get("/settings")
    assert resp.status_code == 200
    body = resp.data
    # Campo inline identificado pelo id que não é o modal
    assert b'id="pass_current_input"' in body
    # E o card tem os 3 campos de senha visíveis
    assert b'id="new_pass_input"' in body
    assert b'id="confirm_pass_input"' in body


def test_profile_modal_uses_blue_not_red(client, db):
    """Modal de perfil deve usar tema azul, não vermelho."""
    auth_client(client, db)
    resp = client.get("/settings")
    assert resp.status_code == 200
    body = resp.data
    # Azul presente no modal de perfil
    assert b"bg-blue-50" in body
    assert b"bg-blue-100" in body
    # Vermelho removido do modal (bg-red-600 era o botão, bg-red-50 era o header)
    assert b"bg-red-50" not in body
    assert b"bg-red-600" not in body


def test_settings_renders_with_unified_title(client, db):
    """Modal de perfil deve usar título 'Confirmar Identidade'."""
    auth_client(client, db)
    resp = client.get("/settings")
    assert resp.status_code == 200
    assert "Confirmar Identidade".encode() in resp.data
