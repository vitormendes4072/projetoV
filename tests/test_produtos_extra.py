"""
Testes adicionais para app/produtos/routes.py —
cobre rotas não exercidas pelos testes originais: lista, historico, CSV import.
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
# GET /produtos — listagem paginada
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
# GET /produtos/novo — formulário de criação
# ---------------------------------------------------------------------------

def test_criar_produto_get(client, db):
    auth_client(client, db)
    resp = client.get("/produtos/novo")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /produtos/editar/<id> — preenche formulário com dados existentes
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
    csv_data = "name;sku;cost;price\nProduto Ponto Vírgula;PV-001;12.00;28.00\n"
    resp = client.post("/produtos/importar-csv", data={
        "arquivo": _csv_file(csv_data),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert resp.status_code == 200
    assert Product.query.filter_by(sku="PV-001").count() == 1


def test_importar_csv_colunas_faltando(client, db):
    auth_client(client, db)
    csv_data = "title,code\nProduto Inválido,XXX\n"
    resp = client.post("/produtos/importar-csv", data={
        "arquivo": _csv_file(csv_data),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert resp.status_code == 200
    # nenhum produto importado — colunas obrigatórias ausentes
    assert Product.query.count() == 0


def test_importar_csv_sku_duplicado_ignorado(client, db):
    auth_client(client, db)
    # cria produto com SKU-DUP manualmente
    client.post("/produtos/novo", data=_produto_data(sku="SKU-DUP"), follow_redirects=True)

    csv_data = "name,sku,cost\nProduto Dup,SKU-DUP,10.00\n"
    resp = client.post("/produtos/importar-csv", data={
        "arquivo": _csv_file(csv_data),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert resp.status_code == 200
    assert Product.query.filter_by(sku="SKU-DUP").count() == 1
