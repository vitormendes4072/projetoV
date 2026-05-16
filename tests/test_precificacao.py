from app.models.pricing import PricingHistory
from tests.conftest import auth_client


def _calc_data(**kwargs):
    base = {
        "price": "100.00",
        "cost": "40.00",
        "fba_fee": "10.00",
        "referral_fee": "15.0",
        "tax_rate": "4.0",
        "marketing": "0.0",
        "title": "",
    }
    base.update(kwargs)
    return base


def test_calcular_margem_basica(client, db):
    auth_client(client, db)
    # price=100, cost=40, fba=10, referral=15%, tax=4%, marketing=0
    # net_profit = 100 - (40 + 15 + 10 + 4 + 0) = 31
    r = client.post("/calculator", data={**_calc_data(), "submit": True}, follow_redirects=True)
    assert r.status_code == 200
    assert b"31" in r.data


def test_salvar_historico(client, db):
    auth_client(client, db)
    r = client.post("/calculator", data={**_calc_data(), "save": True}, follow_redirects=True)
    assert r.status_code == 200
    assert PricingHistory.query.count() == 1
    h = PricingHistory.query.first()
    assert float(h.price) == 100.0
    assert float(h.cost) == 40.0


def test_calculadora_requer_login(client, db):
    r = client.get("/calculator", follow_redirects=True)
    assert r.status_code == 200
    assert r.request.path == "/login"


def test_preco_invalido(client, db):
    auth_client(client, db)
    r = client.post("/calculator", data={**_calc_data(price="0"), "submit": True},
                    follow_redirects=True)
    assert r.status_code == 200
    assert PricingHistory.query.count() == 0
