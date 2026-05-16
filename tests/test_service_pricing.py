from app.services.pricing import calcular_fba


def test_calcular_fba_valores_corretos():
    # price=100, cost=40, fba=10, referral=15%, tax=4%, marketing=0
    # referral_cost=15, tax_cost=4, total_fees=29, total_cost=69, net=31
    r = calcular_fba(price=100, cost=40, fba_fee=10, referral_pct=15, tax_pct=4)
    assert r["net_profit"] == 31.0
    assert r["total_cost"] == 69.0
    assert r["margin"] == 31.0
    assert round(r["roi"], 4) == round(31 / 40 * 100, 4)
    assert r["breakdown"]["referral"] == 15.0
    assert r["breakdown"]["tax"] == 4.0


def test_calcular_fba_com_marketing():
    r = calcular_fba(price=100, cost=40, fba_fee=10, referral_pct=15, tax_pct=4, marketing=5)
    assert r["net_profit"] == 26.0
    assert r["breakdown"]["marketing"] == 5


def test_calcular_fba_price_zero_nao_divide():
    r = calcular_fba(price=0, cost=40, fba_fee=0, referral_pct=0, tax_pct=0)
    assert r["margin"] == 0


def test_calcular_fba_cost_zero_nao_divide():
    r = calcular_fba(price=100, cost=0, fba_fee=0, referral_pct=0, tax_pct=0)
    assert r["roi"] == 0
    assert r["net_profit"] == 100.0
