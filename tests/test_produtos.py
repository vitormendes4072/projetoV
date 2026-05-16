from app.models.product import Product
from tests.conftest import make_user, login, auth_client


def _produto_data(**kwargs):
    base = {
        "name": "Produto Teste",
        "sku": "SKU-001",
        "cost": "10.00",
        "price": "0.0",
        "packaging_cost": "0.0",
        "stock_quantity": "5",
        "image_url": "",
    }
    base.update(kwargs)
    return base


def test_criar_produto_ok(client, db):
    auth_client(client, db)
    r = client.post("/produtos/novo", data=_produto_data(), follow_redirects=True)
    assert r.status_code == 200
    assert Product.query.filter_by(sku="SKU-001").count() == 1


def test_sku_duplicado_mesmo_usuario(client, db):
    auth_client(client, db)
    client.post("/produtos/novo", data=_produto_data(sku="DUP-001"), follow_redirects=True)
    r = client.post("/produtos/novo", data=_produto_data(sku="DUP-001"), follow_redirects=True)
    assert r.status_code == 200
    assert Product.query.filter_by(sku="DUP-001").count() == 1


def test_sku_duplicado_outro_usuario(app, client, db):
    # usuário A cria produto com SKU-MULTI
    make_user(db, email="a@test.com", password="senha123")
    login(client, "a@test.com", "senha123")
    client.post("/produtos/novo", data=_produto_data(sku="SKU-MULTI"), follow_redirects=True)
    client.get("/logout", follow_redirects=True)

    # usuário B usa o mesmo SKU — deve ser aceito
    make_user(db, email="b@test.com", password="senha123")
    login(client, "b@test.com", "senha123")
    r = client.post("/produtos/novo", data=_produto_data(sku="SKU-MULTI"), follow_redirects=True)
    assert r.status_code == 200
    assert Product.query.filter_by(sku="SKU-MULTI").count() == 2


def test_editar_produto(client, db):
    auth_client(client, db)
    client.post("/produtos/novo", data=_produto_data(name="Original"), follow_redirects=True)
    produto = Product.query.filter_by(sku="SKU-001").first()
    r = client.post(f"/produtos/editar/{produto.id}",
                    data=_produto_data(name="Editado", sku="SKU-001"),
                    follow_redirects=True)
    assert r.status_code == 200
    db.session.expire_all()
    assert db.session.get(Product, produto.id).name == "Editado"


def test_isolamento_tenant(client, db):
    # usuário A cria produto
    make_user(db, email="owner@test.com", password="senha123")
    login(client, "owner@test.com", "senha123")
    client.post("/produtos/novo", data=_produto_data(), follow_redirects=True)
    produto = Product.query.filter_by(sku="SKU-001").first()
    produto_id = produto.id
    client.get("/logout", follow_redirects=True)

    # usuário B tenta editar
    make_user(db, email="intruder@test.com", password="senha123")
    login(client, "intruder@test.com", "senha123")
    r = client.post(f"/produtos/editar/{produto_id}",
                    data=_produto_data(name="Hackeado"),
                    follow_redirects=True)
    assert r.status_code == 403
    db.session.expire_all()
    assert db.session.get(Product, produto_id).name == "Produto Teste"
