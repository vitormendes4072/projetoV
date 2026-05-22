"""
Testes adicionais para app/produtos/routes.py --
cobre rotas nao exercidas pelos testes originais: lista, historico, CSV import/export,
ajuste de estoque.
"""
import io
from app.models.product import Product, ProductHistory
from tests.conftest import auth_client, make_user, login


def _produto_data(**kwargs):
    base = {
        "name": "Produto Extra",
        "sku": "EXT-001",
        "cost": "15.00",
        "price": "30.00",
        "packaging_cost": "1.00",
        "stock_quantity": "10",
        "image_url": "",
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# GET /produtos -- listagem paginada
# ---------------------------------------------------------------------------

def test_lista_produtos_empty(client, db):
    auth_client(client, db)
    resp = client.get("/produtos")
    assert resp.status_code == 200


def test_lista_produtos_with_products(client, db):
    auth_client(client, db)
    client.post("/produtos/novo", data=_produto_data(), follow_redirects=True)
    resp = client.get("/produtos")
    assert resp.status_code == 200
    assert b"EXT-001" in resp.data


def test_lista_produtos_unauthenticated(client, db):
    resp = client.get("/produtos")
    assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# GET /produtos/novo -- formulario de criacao
# ---------------------------------------------------------------------------

def test_criar_produto_get(client, db):
    auth_client(client, db)
    resp = client.get("/produtos/novo")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /produtos/editar/<id> -- preenche formulario com dados existentes
# ---------------------------------------------------------------------------

def test_editar_produto_get(client, db):
    auth_client(client, db)
    client.post("/produtos/novo", data=_produto_data(), follow_redirects=True)
    produto = Product.query.filter_by(sku="EXT-001").first()

    resp = client.get(f"/produtos/editar/{produto.id}")
    assert resp.status_code == 200
    assert b"Produto Extra" in resp.data


def test_editar_produto_outro_usuario_403(client, db):
    make_user(db, email="owner@test.com")
    login(client, "owner@test.com", "senha123")
    client.post("/produtos/novo", data=_produto_data(), follow_redirects=True)
    produto = Product.query.filter_by(sku="EXT-001").first()
    client.get("/logout", follow_redirects=True)

    make_user(db, email="intruder@test.com")
    login(client, "intruder@test.com", "senha123")
    resp = client.get(f"/produtos/editar/{produto.id}")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /produtos/historico/<id>
# ---------------------------------------------------------------------------

def test_historico_produto(client, db):
    auth_client(client, db)
    client.post("/produtos/novo", data=_produto_data(), follow_redirects=True)
    produto = Product.query.filter_by(sku="EXT-001").first()

    resp = client.get(f"/produtos/historico/{produto.id}")
    assert resp.status_code == 200


def test_historico_produto_outro_usuario_403(client, db):
    make_user(db, email="histowner@test.com")
    login(client, "histowner@test.com", "senha123")
    client.post("/produtos/novo", data=_produto_data(), follow_redirects=True)
    produto = Product.query.filter_by(sku="EXT-001").first()
    client.get("/logout", follow_redirects=True)

    make_user(db, email="histintruder@test.com")
    login(client, "histintruder@test.com", "senha123")
    resp = client.get(f"/produtos/historico/{produto.id}")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /produtos/exportar-csv
# ---------------------------------------------------------------------------

def test_exportar_csv_requer_login(client, db):
    resp = client.get("/produtos/exportar-csv")
    assert resp.status_code in (302, 401)


def test_exportar_csv_retorna_csv(client, db):
    auth_client(client, db)
    client.post("/produtos/novo", data=_produto_data(), follow_redirects=True)

    resp = client.get("/produtos/exportar-csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.content_type
    assert b"name" in resp.data  # cabecalho


def test_exportar_csv_contem_produto(client, db):
    auth_client(client, db)
    client.post("/produtos/novo", data=_produto_data(name="Produto Export", sku="EXP-001"),
                follow_redirects=True)

    resp = client.get("/produtos/exportar-csv")
    assert b"EXP-001" in resp.data
    assert b"Produto Export" in resp.data


def test_exportar_csv_vazio_sem_produtos(client, db):
    auth_client(client, db)
    resp = client.get("/produtos/exportar-csv")
    assert resp.status_code == 200
    lines = resp.data.decode("utf-8").strip().split("\n")
    # Apenas a linha de cabecalho (ou vazio)
    assert len(lines) <= 1 or lines[0].startswith("name")


# ---------------------------------------------------------------------------
# POST /produtos/importar-csv
# ---------------------------------------------------------------------------

def _csv_file(content: str, filename="produtos.csv"):
    return (io.BytesIO(content.encode("utf-8")), filename)


def test_importar_csv_valido(client, db):
    auth_client(client, db)
    csv_data = "name,sku,cost,price,stock_quantity\nProduto CSV,CSV-001,10.00,25.00,5\n"
    resp = client.post("/produtos/importar-csv", data={
        "arquivo": _csv_file(csv_data),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert resp.status_code == 200
    assert Product.query.filter_by(sku="CSV-001").count() == 1


def test_importar_csv_semicolon_separator(client, db):
    auth_client(client, db)
    csv_data = "name;sku;cost;price\nProduto PV;PV-001;12.00;28.00\n"
    resp = client.post("/produtos/importar-csv", data={
        "arquivo": _csv_file(csv_data),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert resp.status_code == 200
    assert Product.query.filter_by(sku="PV-001").count() == 1


def test_importar_csv_colunas_faltando(client, db):
    auth_client(client, db)
    csv_data = "title,code\nProduto Invalido,XXX\n"
    resp = client.post("/produtos/importar-csv", data={
        "arquivo": _csv_file(csv_data),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert resp.status_code == 200
    assert Product.query.count() == 0


def test_importar_csv_sku_duplicado_ignorado(client, db):
    auth_client(client, db)
    client.post("/produtos/novo", data=_produto_data(sku="SKU-DUP"), follow_redirects=True)

    csv_data = "name,sku,cost\nProduto Dup,SKU-DUP,10.00\n"
    resp = client.post("/produtos/importar-csv", data={
        "arquivo": _csv_file(csv_data),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert resp.status_code == 200
    assert Product.query.filter_by(sku="SKU-DUP").count() == 1


# ---------------------------------------------------------------------------
# POST /produtos/<id>/ajustar-estoque
# ---------------------------------------------------------------------------

def _criar_e_pegar_produto(client, db, sku="ADJ-001", stock=10):
    auth_client(client, db)
    client.post("/produtos/novo", data=_produto_data(sku=sku, stock_quantity=str(stock)),
                follow_redirects=True)
    return Product.query.filter_by(sku=sku).first()


def test_ajustar_estoque_positivo(client, db):
    produto = _criar_e_pegar_produto(client, db, sku="ADJ-POS", stock=10)

    resp = client.post(f"/produtos/{produto.id}/ajustar-estoque",
                       data={"delta": "5", "motivo": "Reposicao"},
                       follow_redirects=True)
    assert resp.status_code == 200
    db.session.refresh(produto)
    assert produto.stock_quantity == 15


def test_ajustar_estoque_negativo(client, db):
    produto = _criar_e_pegar_produto(client, db, sku="ADJ-NEG", stock=20)

    resp = client.post(f"/produtos/{produto.id}/ajustar-estoque",
                       data={"delta": "-3"},
                       follow_redirects=True)
    assert resp.status_code == 200
    db.session.refresh(produto)
    assert produto.stock_quantity == 17


def test_ajustar_estoque_zero_nao_altera(client, db):
    produto = _criar_e_pegar_produto(client, db, sku="ADJ-ZERO", stock=10)

    resp = client.post(f"/produtos/{produto.id}/ajustar-estoque",
                       data={"delta": "0"},
                       follow_redirects=True)
    assert resp.status_code == 200
    db.session.refresh(produto)
    # delta=0 deve gerar aviso e nao alterar estoque
    assert produto.stock_quantity == 10


def test_ajustar_estoque_delta_invalido(client, db):
    produto = _criar_e_pegar_produto(client, db, sku="ADJ-INV", stock=10)

    resp = client.post(f"/produtos/{produto.id}/ajustar-estoque",
                       data={"delta": "abc"},
                       follow_redirects=True)
    assert resp.status_code == 200
    db.session.refresh(produto)
    # delta invalido -> sem alteracao
    assert produto.stock_quantity == 10


def test_ajustar_estoque_registra_historico(client, db):
    produto = _criar_e_pegar_produto(client, db, sku="ADJ-HIST", stock=5)

    client.post(f"/produtos/{produto.id}/ajustar-estoque",
                data={"delta": "10", "motivo": "Entrada de NF"},
                follow_redirects=True)

    from app.models.product import ProductHistory
    hist = ProductHistory.query.filter_by(product_id=produto.id).order_by(
        ProductHistory.changed_at.desc()
    ).first()
    assert hist is not None
    assert "Ajuste" in hist.action_type


def test_ajustar_estoque_outro_usuario_403(client, db):
    make_user(db, email="adjowner@test.com")
    login(client, "adjowner@test.com", "senha123")
    client.post("/produtos/novo", data=_produto_data(sku="ADJ-OWN"), follow_redirects=True)
    produto = Product.query.filter_by(sku="ADJ-OWN").first()
    client.get("/logout", follow_redirects=True)

    make_user(db, email="adjintruder@test.com")
    login(client, "adjintruder@test.com", "senha123")
    resp = client.post(f"/produtos/{produto.id}/ajustar-estoque",
                       data={"delta": "99"},
                       follow_redirects=True)
    assert resp.status_code == 403
