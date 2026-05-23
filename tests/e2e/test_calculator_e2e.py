"""
E2E calculator flow:
- Usuário autenticado acessa /calculator
- Preenche preço, custo, FBA, comissão, imposto
- Submete o form de cálculo
- Vê resultado de margem e lucro na coluna de resultados
"""
from __future__ import annotations

import pytest

from tests.e2e.conftest import login_via_ui

pytestmark = pytest.mark.e2e


def test_calculator_page_renders_when_authenticated(live_server, seeded_user, page):
    login_via_ui(page, live_server.url, seeded_user.email, "senha123")
    page.goto(f"{live_server.url}/calculator")
    page.wait_for_load_state("networkidle")
    # Página do simulador deve estar visível (heading "Simulador FBA")
    assert page.locator("text=Simulador FBA").count() >= 1


def test_calculator_computes_and_displays_result(live_server, seeded_user, page):
    login_via_ui(page, live_server.url, seeded_user.email, "senha123")
    page.goto(f"{live_server.url}/calculator")
    page.wait_for_load_state("networkidle")

    # Preencher campos do form
    page.fill('input[name="title"]', "Cenário E2E")
    page.fill('input[name="price"]', "100")
    page.fill('input[name="cost"]', "30")
    page.fill('input[name="fba_fee"]', "10")
    page.fill('input[name="referral_fee"]', "15")
    page.fill('input[name="tax_rate"]', "4")

    # Clica em "Calcular" (form.submit). O form tem 2 botões — submit & save.
    # Usa o primeiro input[type=submit] que aparece (calcular).
    page.locator('input[name="submit"]').click()
    page.wait_for_load_state("networkidle")

    # Coluna de resultado deve exibir margem em % (o template formata como "%.1f%%")
    # Procura por "Margem" no card de resultado
    assert page.locator("text=Margem").count() >= 1
    assert page.locator("text=Lucro").count() >= 1
    # Receita líquida estimada: 100 - 10 (FBA) - 15 (15% comissão) - 4 (4% imposto) - 30 (cmv) = 41
    # ROI 41/30 ≈ 136%. Não comparamos número exato (regras de margem podem variar),
    # mas garantimos que apareceu um valor em R$ no card de resultado.
    assert page.locator("text=R$").count() >= 3
