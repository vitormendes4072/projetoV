from datetime import date
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


def test_criar_custo_fixo(client, db):
    auth_client(client, db)

    r = _criar_custo(client)
    assert r.status_code == 200

    item = CustoFixo.query.filter_by(nome="Aluguel").first()
    assert item is not None
    assert float(item.valor_mensal) == 1500.0
    assert item.dia_pagamento == 5
    assert item.ativo is True

    history = CustoFixoHistory.query.filter_by(item_id=item.id, action="create").first()
    assert history is not None


def test_editar_custo_fixo(client, db):
    auth_client(client, db)
    _criar_custo(client)

    item = CustoFixo.query.filter_by(nome="Aluguel").first()

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


def test_toggle_ativo(client, db):
    auth_client(client, db)
    _criar_custo(client)

    item = CustoFixo.query.filter_by(nome="Aluguel").first()
    assert item.ativo is True

    client.post(f"/financeiro/custos-fixos/{item.id}/toggle", follow_redirects=True)
    db.session.refresh(item)
    assert item.ativo is False

    history = CustoFixoHistory.query.filter_by(item_id=item.id, action="toggle_active").first()
    assert history is not None


def test_marcar_pago_e_desmarcar(client, db):
    auth_client(client, db)
    _criar_custo(client)

    item = CustoFixo.query.filter_by(nome="Aluguel").first()
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


def test_isolamento_tenant(client, db):
    # usuário A cria o custo
    auth_client(client, db, email="a@test.com")
    _criar_custo(client)
    item = CustoFixo.query.filter_by(nome="Aluguel").first()

    # usuário B tenta editar
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
