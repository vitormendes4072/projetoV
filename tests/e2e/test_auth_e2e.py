"""
E2E auth flow:
- Página de login renderiza
- Login com credenciais corretas redireciona para área autenticada
- Logout redireciona e bloqueia acesso à área autenticada
- Login com credenciais inválidas mostra mensagem de erro
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e


def test_login_page_renders(live_server, page):
    page.goto(f"{live_server.url}/login")
    assert page.title() != ""
    # Campos do form devem estar presentes
    assert page.locator('input[name="email"]').count() == 1
    assert page.locator('input[name="password"]').count() == 1


def test_login_with_valid_credentials_redirects_to_dashboard(live_server, seeded_user, page):
    page.goto(f"{live_server.url}/login")
    page.fill('input[name="email"]', seeded_user.email)
    page.fill('input[name="password"]', "senha123")
    page.click('input[type="submit"]')

    # Após login bem-sucedido, sai de /login
    page.wait_for_url(lambda url: "/login" not in url, timeout=5000)
    assert "/login" not in page.url


def test_logout_clears_session(live_server, seeded_user, page):
    # Login primeiro
    page.goto(f"{live_server.url}/login")
    page.fill('input[name="email"]', seeded_user.email)
    page.fill('input[name="password"]', "senha123")
    page.click('input[type="submit"]')
    page.wait_for_url(lambda url: "/login" not in url, timeout=5000)

    # Logout
    page.goto(f"{live_server.url}/logout")

    # Acessar /menu sem sessão deve redirecionar para /login
    page.goto(f"{live_server.url}/menu")
    page.wait_for_url(lambda url: "/login" in url, timeout=5000)
    assert "/login" in page.url


def test_login_with_invalid_credentials_stays_on_login(live_server, seeded_user, page):
    page.goto(f"{live_server.url}/login")
    page.fill('input[name="email"]', seeded_user.email)
    page.fill('input[name="password"]', "senha-errada")
    page.click('input[type="submit"]')

    # Aguarda response e confirma que ainda está na página de login
    page.wait_for_load_state("networkidle")
    assert "/login" in page.url
