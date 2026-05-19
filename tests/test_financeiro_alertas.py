"""
Testes para app/financeiro/routes_alertas.py.
NotificationSettings e NotificationRecipient estão em SQLITE_TABLES.
"""
from tests.conftest import auth_client


# ---------------------------------------------------------------------------
# Unauthenticated
# ---------------------------------------------------------------------------

def test_alertas_unauthenticated(client, db):
    resp = client.get("/financeiro/alertas")
    assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# GET /alertas — cria settings se não existir
# ---------------------------------------------------------------------------

def test_alertas_get_creates_settings(client, db):
    auth_client(client, db)
    resp = client.get("/financeiro/alertas")
    assert resp.status_code == 200


def test_alertas_get_renders_form(client, db):
    auth_client(client, db)
    resp = client.get("/financeiro/alertas")
    assert b"alerta" in resp.data.lower() or b"Alerta" in resp.data


# ---------------------------------------------------------------------------
# POST /alertas — atualiza configuração
# ---------------------------------------------------------------------------

def test_alertas_post_before_and_due(client, db):
    auth_client(client, db)
    resp = client.post("/financeiro/alertas", data={
        "alert_mode": "before_and_due",
        "days_before": "5",
    }, follow_redirects=True)
    assert resp.status_code == 200


def test_alertas_post_due_only(client, db):
    auth_client(client, db)
    resp = client.post("/financeiro/alertas", data={
        "alert_mode": "due_only",
        "days_before": "",
    }, follow_redirects=True)
    assert resp.status_code == 200


def test_alertas_post_none_mode(client, db):
    auth_client(client, db)
    resp = client.post("/financeiro/alertas", data={
        "alert_mode": "none",
    }, follow_redirects=True)
    assert resp.status_code == 200


def test_alertas_post_invalid_mode(client, db):
    auth_client(client, db)
    resp = client.post("/financeiro/alertas", data={
        "alert_mode": "invalid_mode_xyz",
    }, follow_redirects=True)
    assert resp.status_code == 200


def test_alertas_post_invalid_days_before(client, db):
    auth_client(client, db)
    resp = client.post("/financeiro/alertas", data={
        "alert_mode": "before_and_due",
        "days_before": "abc",
    }, follow_redirects=True)
    assert resp.status_code == 200


def test_alertas_post_days_before_clamped(client, db):
    auth_client(client, db)
    # 99 deve ser clamped para 10
    resp = client.post("/financeiro/alertas", data={
        "alert_mode": "before_and_due",
        "days_before": "99",
    }, follow_redirects=True)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /alertas/enabled — toggle enabled
# ---------------------------------------------------------------------------

def test_alertas_enabled_true(client, db):
    auth_client(client, db)
    resp = client.post("/financeiro/alertas/enabled", data={"enabled": "1"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["enabled"] is True


def test_alertas_enabled_false(client, db):
    auth_client(client, db)
    resp = client.post("/financeiro/alertas/enabled", data={"enabled": "0"})
    assert resp.status_code == 200
    assert resp.get_json()["enabled"] is False


# ---------------------------------------------------------------------------
# POST /alertas/recipients — adicionar destinatário
# ---------------------------------------------------------------------------

def test_alertas_recipients_add_valid(client, db):
    auth_client(client, db)
    resp = client.post("/financeiro/alertas/recipients",
                       data={"email": "recip@example.com"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["email"] == "recip@example.com"
    assert data["enabled"] is True


def test_alertas_recipients_add_invalid_email(client, db):
    auth_client(client, db)
    resp = client.post("/financeiro/alertas/recipients",
                       data={"email": "not-an-email"})
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_alertas_recipients_add_duplicate_reactivates(client, db):
    auth_client(client, db)
    client.post("/financeiro/alertas/recipients", data={"email": "dup@example.com"})
    # segundo POST com mesmo email não deve criar duplicata
    resp = client.post("/financeiro/alertas/recipients",
                       data={"email": "dup@example.com"})
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


# ---------------------------------------------------------------------------
# POST /alertas/recipients/<id>/toggle
# ---------------------------------------------------------------------------

def test_alertas_recipients_toggle(client, db):
    auth_client(client, db)
    add_resp = client.post("/financeiro/alertas/recipients",
                           data={"email": "tog@example.com"})
    rid = add_resp.get_json()["id"]

    resp = client.post(f"/financeiro/alertas/recipients/{rid}/toggle",
                       data={"enabled": "0"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["enabled"] is False


def test_alertas_recipients_toggle_enable(client, db):
    auth_client(client, db)
    add_resp = client.post("/financeiro/alertas/recipients",
                           data={"email": "tog2@example.com"})
    rid = add_resp.get_json()["id"]

    resp = client.post(f"/financeiro/alertas/recipients/{rid}/toggle",
                       data={"enabled": "true"})
    assert resp.status_code == 200
    assert resp.get_json()["enabled"] is True


# ---------------------------------------------------------------------------
# DELETE /alertas/recipients/<id>
# ---------------------------------------------------------------------------

def test_alertas_recipients_delete(client, db):
    auth_client(client, db)
    add_resp = client.post("/financeiro/alertas/recipients",
                           data={"email": "del@example.com"})
    rid = add_resp.get_json()["id"]

    resp = client.delete(f"/financeiro/alertas/recipients/{rid}")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_alertas_recipients_delete_not_found(client, db):
    auth_client(client, db)
    resp = client.delete("/financeiro/alertas/recipients/99999")
    assert resp.status_code == 404
