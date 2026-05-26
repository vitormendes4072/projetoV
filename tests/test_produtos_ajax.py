"""
Testes AJAX para app/produtos/routes.py:
  - PATCH /produtos/<id>  (patch_produto)
  - POST  /produtos/<id>/ajustar-estoque  com header XHR
"""
import json
from tests.conftest import auth_client, make_user, login
from app.models.product import Product


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_product(db, user, name="Produto Teste", sku="SKU-001",
                  price=50.0, cost=20.0, stock_quantity=10):
    p = Product(
        name=name, sku=sku,
        price=price, cost=cost,
        packaging_cost=0.0, stock_quantity=stock_quantity,
        owner=user,
    )
    db.session.add(p)
    db.session.commit()
    return p


def _patch(client, product_id, field, value, csrf="test-csrf"):
    return client.patch(
        f"/produtos/{product_id}",
        data=json.dumps({"field": field, "value": value}),
        content_type="application/json",
        headers={"X-CSRFToken": csrf},
    )


# ---------------------------------------------------------------------------
# PATCH /produtos/<id> — patch_produto
# ---------------------------------------------------------------------------

class TestPatchProduto:

    def test_patch_price_success(self, client, db):
        auth_client(client, db)
        from app.models.user import User
        u = db.session.scalars(db.select(User)).first()
        product = _make_product(db, u)

        resp = _patch(client, product.id, "price", 99.90)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["field"] == "price"
        assert abs(float(data["new_value"]) - 99.90) < 0.001

    def test_patch_cost_success(self, client, db):
        from app.models.user import User
        auth_client(client, db)
        u = db.session.scalars(db.select(User)).first()
        product = _make_product(db, u)

        resp = _patch(client, product.id, "cost", 15.50)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["field"] == "cost"

    def test_patch_invalid_field_rejected(self, client, db):
        from app.models.user import User
        auth_client(client, db)
        u = db.session.scalars(db.select(User)).first()
        product = _make_product(db, u)

        resp = _patch(client, product.id, "name", "hacked")
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["ok"] is False

    def test_patch_negative_float_rejected(self, client, db):
        from app.models.user import User
        auth_client(client, db)
        u = db.session.scalars(db.select(User)).first()
        product = _make_product(db, u)

        resp = _patch(client, product.id, "price", -5.0)
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["ok"] is False

    def test_patch_other_user_forbidden(self, client, db):
        # Create owner and product
        owner = make_user(db, email="owner@test.com")
        product = _make_product(db, owner, sku="SKU-OWN")

        # Log in as a different user
        make_user(db, email="other@test.com")
        login(client, "other@test.com", "senha123")

        resp = _patch(client, product.id, "price", 10.0)
        assert resp.status_code == 403
        data = resp.get_json()
        assert data["ok"] is False

    def test_patch_unauthenticated_redirects(self, client, db):
        # No login — should redirect to login page
        resp = _patch(client, 999, "price", 10.0)
        assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# POST /produtos/<id>/ajustar-estoque — XHR vs normal
# ---------------------------------------------------------------------------

class TestAjustarEstoque:

    def _post_adjust(self, client, product_id, delta, motivo="Teste", xhr=False):
        headers = {}
        if xhr:
            headers["X-Requested-With"] = "XMLHttpRequest"
        return client.post(
            f"/produtos/{product_id}/ajustar-estoque",
            data={"delta": str(delta), "motivo": motivo, "csrf_token": "ignored"},
            headers=headers,
            follow_redirects=False,
        )

    def test_ajax_adjust_returns_json(self, client, db):
        from app.models.user import User
        auth_client(client, db)
        u = db.session.scalars(db.select(User)).first()
        product = _make_product(db, u, stock_quantity=10)

        resp = self._post_adjust(client, product.id, 5, xhr=True)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["new_qty"] == 15

    def test_ajax_adjust_negative_delta(self, client, db):
        from app.models.user import User
        auth_client(client, db)
        u = db.session.scalars(db.select(User)).first()
        product = _make_product(db, u, stock_quantity=10)

        resp = self._post_adjust(client, product.id, -3, xhr=True)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["new_qty"] == 7

    def test_normal_adjust_redirects(self, client, db):
        from app.models.user import User
        auth_client(client, db)
        u = db.session.scalars(db.select(User)).first()
        product = _make_product(db, u, stock_quantity=10)

        resp = self._post_adjust(client, product.id, 5, xhr=False)
        # Without XHR header, route redirects
        assert resp.status_code == 302

    def test_ajax_zero_delta_returns_error(self, client, db):
        from app.models.user import User
        auth_client(client, db)
        u = db.session.scalars(db.select(User)).first()
        product = _make_product(db, u)

        resp = self._post_adjust(client, product.id, 0, xhr=True)
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["ok"] is False

    def test_ajax_invalid_delta_returns_error(self, client, db):
        from app.models.user import User
        auth_client(client, db)
        u = db.session.scalars(db.select(User)).first()
        product = _make_product(db, u)

        resp = client.post(
            f"/produtos/{product.id}/ajustar-estoque",
            data={"delta": "abc", "motivo": "", "csrf_token": "x"},
            headers={"X-Requested-With": "XMLHttpRequest"},
            follow_redirects=False,
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["ok"] is False
