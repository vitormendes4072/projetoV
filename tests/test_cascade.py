from app.models.user import User
from app.models.product import Product, ProductHistory
from app.models.pricing import PricingHistory
from tests.conftest import make_user


def test_delete_user_cascades_products(client, db):
    user = make_user(db)

    produto = Product(name="Prod", sku="SKU-DEL", cost=10.0, price=0.0,
                      packaging_cost=0.0, stock_quantity=1, owner=user)
    db.session.add(produto)
    db.session.commit()

    historico = ProductHistory(
        product_id=produto.id, user_id=user.id,
        price=0.0, cost=10.0, stock_quantity=1, action_type="Criação Inicial"
    )
    db.session.add(historico)
    db.session.commit()

    ph = PricingHistory(
        user_id=user.id, price=100, cost=40, fba_fee=10,
        referral_fee=15, tax_rate=4, marketing=0,
        net_profit=31, margin=31, roi=77.5
    )
    db.session.add(ph)
    db.session.commit()

    db.session.delete(user)
    db.session.commit()

    assert Product.query.filter_by(sku="SKU-DEL").count() == 0
    assert ProductHistory.query.filter_by(action_type="Criação Inicial").count() == 0
    assert PricingHistory.query.count() == 0
