from datetime import date
from decimal import Decimal
from tests.conftest import auth_client, make_user, login
from app.models.custo_fixo import CustoFixo
from app.models.custo_fixo_history import CustoFixoHistory
from app.models.custo_fixo_pagamento import CustoFixoPagamento


FORM_BASE = {
    "nome": "Aluguel",
    "categoria": "Moradia",
    "valor_mensal": "1500,00",
    "dia_pagamento": "5",
    "data_inicio": "2026-01-01",
    "data_fim": "",
}


def _criar_custo(client):
    return client.post("/financeiro/custos-fixos", data=FORM_BASE, follow_redirects=True)


def _get_item(db, nome="Aluguel"):
    return CustoFixo.query.filter_by(nome=nome).first()


# ---------------------------------------------------------------------------
# Criar
# ---------------------------------------------------------------------------

def test_criar_custo_fixo(client, db):
    auth_client(client, db)

    r = _criar_custo(client)
    assert r.status_code == 200

    item = _get_item(db)
    assert item is not None
    assert float(item.valor_mensal) == 1500.0
    assert item.dia_pagamento == 5
    assert item.ativo is True

    history = CustoFixoHistory.query.filter_by(item_id=item.id, action="create").first()
    assert history is not None


def test_criar_custo_fixo_sem_nome(client, db):
    auth_client(client, db)
    r = client.post("/financeiro/custos-fixos",
                    data={**FORM_BASE, "nome": ""},
                    follow_redirects=True)
    assert r.status_code == 200
    assert CustoFixo.query.count() == 0


def test_criar_custo_fixo_sem_data_inicio(client, db):
    auth_client(client, db)
    r = client.post("/financeiro/custos-fixos",
                    data={**FORM_BASE, "data_inicio": ""},
                    follow_redirects=True)
    assert r.status_code == 200
    assert CustoFixo.query.count() == 0


def test_criar_custo_fixo_dia_invalido(client, db):
    auth_client(client, db)
    r = client.post("/financeiro/custos-fixos",
                    data={**FORM_BASE, "dia_pagamento": "99"},
                    follow_redirects=True)
    assert r.status_code == 200
    assert CustoFixo.query.count() == 0


def test_criar_custo_fixo_valor_invalido(client, db):
    auth_client(client, db)
    r = client.post("/financeiro/custos-fixos",
                    data={**FORM_BASE, "valor_mensal": "abc"},
                    follow_redirects=True)
    assert r.status_code == 200
    assert CustoFixo.query.count() == 0


# ---------------------------------------------------------------------------
# Editar
# ---------------------------------------------------------------------------

def test_editar_custo_fixo(client, db):
    auth_client(client, db)
    _criar_custo(client)

    item = _get_item(db)

    r = client.post(
        f"/financeiro/custos-fixos/{item.id}/update",
        data={**FORM_BASE, "nome": "Aluguel Atualizado", "valor_mensal": "1800,00"},
        follow_redirects=True,
    )
    assert r.status_code == 200

    db.session.refresh(item)
    assert item.nome == "Aluguel Atualizado"
    assert float(item.valor_mensal) == 1800.0

    history = CustoFixoHistory.query.filter_by(item_id=item.id, action="update").first()
    assert history is not None
    assert "nome" in history.diff


# ---------------------------------------------------------------------------
# Toggle ativo
# ---------------------------------------------------------------------------

def test_toggle_ativo(client, db):
    auth_client(client, db)
    _criar_custo(client)

    item = _get_item(db)
    assert item.ativo is True

    client.post(f"/financeiro/custos-fixos/{item.id}/toggle", follow_redirects=True)
    db.session.refresh(item)
    assert item.ativo is False

    history = CustoFixoHistory.query.filter_by(item_id=item.id, action="toggle_active").first()
    assert history is not None


# ---------------------------------------------------------------------------
# Toggle pago
# ---------------------------------------------------------------------------

def test_marcar_pago_e_desmarcar(client, db):
    auth_client(client, db)
    _criar_custo(client)

    item = _get_item(db)
    hoje = date.today()

    # marcar como pago
    client.post(f"/financeiro/custos-fixos/{item.id}/pago", follow_redirects=True)
    pagamento = CustoFixoPagamento.query.filter_by(
        custo_fixo_id=item.id, ano=hoje.year, mes=hoje.month
    ).first()
    assert pagamento is not None

    # desmarcar (toggle)
    client.post(f"/financeiro/custos-fixos/{item.id}/pago", follow_redirects=True)
    pagamento = CustoFixoPagamento.query.filter_by(
        custo_fixo_id=item.id, ano=hoje.year, mes=hoje.month
    ).first()
    assert pagamento is None


# ---------------------------------------------------------------------------
# Delete individual
# ---------------------------------------------------------------------------

def test_delete_custo_fixo(client, db):
    auth_client(client, db)
    _criar_custo(client)
    item = _get_item(db)
    item_id = item.id

    r = client.post(f"/financeiro/custos-fixos/{item_id}/delete", follow_redirects=True)
    assert r.status_code == 200
    assert CustoFixo.query.filter_by(id=item_id).first() is None


def test_delete_custo_fixo_outro_usuario_404(client, db):
    auth_client(client, db, email="owner@test.com")
    _criar_custo(client)
    item = _get_item(db)
    client.get("/logout", follow_redirects=True)

    make_user(db, email="intruder@test.com")
    login(client, "intruder@test.com", "senha123")
    r = client.post(f"/financeiro/custos-fixos/{item.id}/delete", follow_redirects=True)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Historico JSON
# ---------------------------------------------------------------------------

def test_historico_json_retorna_lista(client, db):
    auth_client(client, db)
    _criar_custo(client)
    item = _get_item(db)

    r = client.get(f"/financeiro/custos-fixos/{item.id}/history")
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)
    # deve ter ao menos o registro de criacao
    assert len(data) >= 1
    assert data[0]["action"] == "create"


def test_historico_json_outro_usuario_404(client, db):
    auth_client(client, db, email="owner2@test.com")
    _criar_custo(client)
    item = _get_item(db)
    client.get("/logout", follow_redirects=True)

    make_user(db, email="intruder2@test.com")
    login(client, "intruder2@test.com", "senha123")
    r = client.get(f"/financeiro/custos-fixos/{item.id}/history")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Bulk actions
# ---------------------------------------------------------------------------

def _ids_form(*items):
    """Monta dict com selected_ids para o form de bulk."""
    return {"selected_ids": [str(i.id) for i in items], "action": ""}


def test_bulk_no_ids_flash_warning(client, db):
    auth_client(client, db)
    r = client.post("/financeiro/custos-fixos/bulk",
                    data={"action": "delete"},
                    follow_redirects=True)
    assert r.status_code == 200
    # nenhum item excluido
    assert CustoFixo.query.count() == 0


def test_bulk_invalid_action(client, db):
    auth_client(client, db)
    _criar_custo(client)
    item = _get_item(db)

    r = client.post("/financeiro/custos-fixos/bulk",
                    data={"action": "hack", "selected_ids": [str(item.id)]},
                    follow_redirects=True)
    assert r.status_code == 200
    # item nao foi afetado
    assert CustoFixo.query.filter_by(id=item.id).first() is not None


def test_bulk_delete(client, db):
    auth_client(client, db)
    _criar_custo(client)
    item = _get_item(db)
    item_id = item.id

    r = client.post("/financeiro/custos-fixos/bulk",
                    data={"action": "delete", "selected_ids": [str(item_id)]},
                    follow_redirects=True)
    assert r.status_code == 200
    assert CustoFixo.query.filter_by(id=item_id).first() is None


def test_bulk_activate(client, db):
    auth_client(client, db)
    _criar_custo(client)
    item = _get_item(db)
    item.ativo = False
    db.session.commit()

    client.post("/financeiro/custos-fixos/bulk",
                data={"action": "activate", "selected_ids": [str(item.id)]},
                follow_redirects=True)
    db.session.refresh(item)
    assert item.ativo is True


def test_bulk_deactivate(client, db):
    auth_client(client, db)
    _criar_custo(client)
    item = _get_item(db)

    client.post("/financeiro/custos-fixos/bulk",
                data={"action": "deactivate", "selected_ids": [str(item.id)]},
                follow_redirects=True)
    db.session.refresh(item)
    assert item.ativo is False


def test_bulk_mark_paid(client, db):
    auth_client(client, db)
    _criar_custo(client)
    item = _get_item(db)
    hoje = date.today()

    client.post("/financeiro/custos-fixos/bulk",
                data={"action": "mark_paid", "selected_ids": [str(item.id)]},
                follow_redirects=True)
    p = CustoFixoPagamento.query.filter_by(
        custo_fixo_id=item.id, ano=hoje.year, mes=hoje.month
    ).first()
    assert p is not None


def test_bulk_unmark_paid(client, db):
    auth_client(client, db)
    _criar_custo(client)
    item = _get_item(db)
    hoje = date.today()

    # primeiro marca
    client.post("/financeiro/custos-fixos/bulk",
                data={"action": "mark_paid", "selected_ids": [str(item.id)]},
                follow_redirects=True)
    # depois desmarca
    client.post("/financeiro/custos-fixos/bulk",
                data={"action": "unmark_paid", "selected_ids": [str(item.id)]},
                follow_redirects=True)

    p = CustoFixoPagamento.query.filter_by(
        custo_fixo_id=item.id, ano=hoje.year, mes=hoje.month
    ).first()
    assert p is None


def test_bulk_ids_de_outro_usuario_ignorados(client, db):
    """Bulk action nao deve afetar itens de outro usuario."""
    auth_client(client, db, email="owner3@test.com")
    _criar_custo(client)
    item = _get_item(db)
    item_id = item.id
    client.get("/logout", follow_redirects=True)

    make_user(db, email="intruder3@test.com")
    login(client, "intruder3@test.com", "senha123")
    r = client.post("/financeiro/custos-fixos/bulk",
                    data={"action": "delete", "selected_ids": [str(item_id)]},
                    follow_redirects=True)
    assert r.status_code == 200
    # item do outro usuario nao foi apagado
    assert CustoFixo.query.filter_by(id=item_id).first() is not None


# ---------------------------------------------------------------------------
# Filtros e parametros GET
# ---------------------------------------------------------------------------

def test_filtros_sort_nome(client, db):
    auth_client(client, db)
    r = client.get("/financeiro/custos-fixos?sort=nome")
    assert r.status_code == 200


def test_filtros_sort_categoria(client, db):
    auth_client(client, db)
    r = client.get("/financeiro/custos-fixos?sort=categoria")
    assert r.status_code == 200


def test_filtros_sort_valor_desc(client, db):
    auth_client(client, db)
    r = client.get("/financeiro/custos-fixos?sort=valor_desc")
    assert r.status_code == 200


def test_filtros_sort_valor_asc(client, db):
    auth_client(client, db)
    r = client.get("/financeiro/custos-fixos?sort=valor_asc")
    assert r.status_code == 200


def test_filtros_sort_inicio(client, db):
    auth_client(client, db)
    r = client.get("/financeiro/custos-fixos?sort=inicio")
    assert r.status_code == 200


def test_filtros_ativo_active(client, db):
    auth_client(client, db)
    r = client.get("/financeiro/custos-fixos?ativo=active")
    assert r.status_code == 200


def test_filtros_ativo_inactive(client, db):
    auth_client(client, db)
    r = client.get("/financeiro/custos-fixos?ativo=inactive")
    assert r.status_code == 200


def test_filtros_cat_filter(client, db):
    auth_client(client, db)
    r = client.get("/financeiro/custos-fixos?cat=Moradia")
    assert r.status_code == 200


def test_filtros_busca_texto(client, db):
    auth_client(client, db)
    _criar_custo(client)
    r = client.get("/financeiro/custos-fixos?q=Aluguel")
    assert r.status_code == 200
    assert b"Aluguel" in r.data


def test_filtros_view_next7(client, db):
    auth_client(client, db)
    r = client.get("/financeiro/custos-fixos?view=next7")
    assert r.status_code == 200


def test_filtros_view_open_month(client, db):
    auth_client(client, db)
    r = client.get("/financeiro/custos-fixos?view=open_month")
    assert r.status_code == 200


def test_filtros_paid_paid(client, db):
    auth_client(client, db)
    r = client.get("/financeiro/custos-fixos?paid=paid")
    assert r.status_code == 200


def test_filtros_paid_unpaid(client, db):
    auth_client(client, db)
    r = client.get("/financeiro/custos-fixos?paid=unpaid")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Isolamento tenant
# ---------------------------------------------------------------------------

def test_isolamento_tenant(client, db):
    # usuario A cria o custo
    auth_client(client, db, email="a@test.com")
    _criar_custo(client)
    item = _get_item(db)

    # usuario B tenta editar
    client.get("/logout", follow_redirects=True)
    make_user(db, email="b@test.com")
    login(client, "b@test.com", "senha123")

    r = client.post(
        f"/financeiro/custos-fixos/{item.id}/update",
        data={**FORM_BASE, "nome": "Invadido"},
        follow_redirects=True,
    )
    assert r.status_code == 404
    db.session.refresh(item)
    assert item.nome == "Aluguel"
