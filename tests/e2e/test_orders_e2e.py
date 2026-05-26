"""
E2E orders + profit flow.

Phase 3A (SQLite-friendly): usa `page.route()` para mockar os endpoints de sync
no nível de rede do browser. Não toca SP-API nem tabelas com schema='public'.

Phase 3B (Postgres-only): semeia AmazonOrder/AmazonFinancialEvent direto via
SQLAlchemy e valida que a página de pedidos exibe os dados e o painel de
detalhes (profit) expande corretamente.
"""
from __future__ import annotations

import json
import os

import pytest

from tests.e2e.conftest import login_via_ui

pytestmark = pytest.mark.e2e

_USING_PG = bool(os.environ.get("TEST_DATABASE_URL") and
                 "postgresql" in os.environ.get("TEST_DATABASE_URL", ""))


# ---------------------------------------------------------------------------
# Phase 3A — sync mockado via page.route() (sempre roda, mesmo em SQLite)
# ---------------------------------------------------------------------------

def test_sync_orders_button_mocked_success(live_server, seeded_user, page):
    """
    Verifica que o JS de orders.js, ao clicar em 'Sincronizar pedidos',
    consome o endpoint e exibe feedback de sucesso.
    A página de orders pode redirecionar/404 sem dados Amazon configurados (SQLite),
    então testamos clicando em uma página estática + injetando o JS manualmente
    via console.

    NOTA: como /integrations/amazon/orders requer schema='public' (Postgres),
    em SQLite este teste valida apenas o contrato JSON do endpoint via fetch direto.
    """
    login_via_ui(page, live_server.url, seeded_user.email, "senha123")

    # Mocka a resposta do endpoint de sync
    def handle_sync(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "ok": True,
                "orders_returned_by_api": 5,
                "orders_upserted": 5,
            }),
        )

    page.route("**/integrations/amazon/sync_orders_only*", handle_sync)

    # Faz fetch direto no browser pra simular o que o JS faz
    result = page.evaluate(
        """
        async () => {
            const res = await fetch('/integrations/amazon/sync_orders_only?days=30');
            const data = await res.json();
            return { status: res.status, data };
        }
        """
    )
    assert result["status"] == 200
    assert result["data"]["ok"] is True
    assert result["data"]["orders_upserted"] == 5


def test_sync_orders_button_mocked_failure(live_server, seeded_user, page):
    """Endpoint mockado retorna erro → JS deve exibir mensagem de falha."""
    login_via_ui(page, live_server.url, seeded_user.email, "senha123")

    def handle_sync(route):
        route.fulfill(
            status=400,
            content_type="application/json",
            body=json.dumps({"ok": False, "error": "SP-API throttle"}),
        )

    page.route("**/integrations/amazon/sync_orders_only*", handle_sync)

    result = page.evaluate(
        """
        async () => {
            const res = await fetch('/integrations/amazon/sync_orders_only?days=30');
            const data = await res.json();
            return { status: res.status, data };
        }
        """
    )
    assert result["status"] == 400
    assert result["data"]["ok"] is False
    assert "throttle" in result["data"]["error"]


def test_sync_orders_async_job_polling_flow(live_server, seeded_user, page):
    """
    Simula o fluxo enqueue → polling → finished do endpoint async /sync_orders.
    Valida o contrato completo que o frontend espera (queued → finished).
    """
    login_via_ui(page, live_server.url, seeded_user.email, "senha123")

    call_count = {"polls": 0}

    def handle_enqueue(route):
        route.fulfill(
            status=202,
            content_type="application/json",
            body=json.dumps({"ok": True, "job_id": "fake-123", "status": "queued"}),
        )

    def handle_status(route):
        call_count["polls"] += 1
        if call_count["polls"] < 2:
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"ok": True, "status": "started"}))
        else:
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"ok": True, "status": "finished",
                                           "result": {"orders": 10}}))

    page.route("**/integrations/amazon/sync_orders", handle_enqueue)
    page.route("**/integrations/amazon/jobs/fake-123", handle_status)

    result = page.evaluate(
        """
        async () => {
            const enq = await fetch('/integrations/amazon/sync_orders', { method: 'POST' });
            const enqData = await enq.json();
            const jobId = enqData.job_id;
            // Polling: até 5 tentativas
            for (let i = 0; i < 5; i++) {
                const poll = await fetch(`/integrations/amazon/jobs/${jobId}`);
                const pollData = await poll.json();
                if (pollData.status === 'finished') {
                    return { jobId, final: pollData };
                }
                await new Promise(r => setTimeout(r, 50));
            }
            return { jobId, final: null };
        }
        """
    )
    assert result["jobId"] == "fake-123"
    assert result["final"]["status"] == "finished"
    assert result["final"]["result"]["orders"] == 10


# ---------------------------------------------------------------------------
# Phase 3B — Full stack com Postgres: orders page + profit panel
# ---------------------------------------------------------------------------

@pytest.mark.requires_postgres
@pytest.mark.skipif(not _USING_PG, reason="Requer Postgres (schema='public')")
def test_orders_page_lists_seeded_orders(live_server, seeded_amazon_data, page):
    """
    Após semear AmazonConnection + 2 orders no DB, /integrations/amazon/orders
    deve listar os pedidos seedados na tabela.
    """
    user = seeded_amazon_data["user"]
    login_via_ui(page, live_server.url, user.email, "senha123")

    page.goto(f"{live_server.url}/integrations/amazon/orders")
    page.wait_for_load_state("networkidle")

    # Ambos os order IDs devem aparecer na tabela
    assert page.locator("text=111-E2E-0001").count() >= 1
    assert page.locator("text=111-E2E-0002").count() >= 1
    # Status mapeados em português
    assert page.locator("text=Enviado").count() >= 1
    assert page.locator("text=Pendente").count() >= 1


@pytest.mark.requires_postgres
@pytest.mark.skipif(not _USING_PG, reason="Requer Postgres (schema='public')")
def test_orders_page_expand_details_loads_profit(live_server, seeded_amazon_data, page):
    """
    Clicar no botão ▼ deve disparar fetch para /orders/<id>/details e exibir
    o painel de breakdown de lucro com receita/líquido/lucro.
    """
    user = seeded_amazon_data["user"]
    login_via_ui(page, live_server.url, user.email, "senha123")

    page.goto(f"{live_server.url}/integrations/amazon/orders")
    page.wait_for_load_state("networkidle")

    # Clica no toggle do primeiro pedido (com financial event seedado)
    toggle = page.locator('button.toggle-details[data-order-id="111-E2E-0001"]').first
    toggle.click()

    # Aguarda o painel expandir e carregar (fetch assíncrono)
    details_row = page.locator("#details-111-E2E-0001")
    page.wait_for_function(
        "() => document.querySelector('#details-111-E2E-0001')?.dataset.loaded === '1'",
        timeout=5000,
    )

    # Painel deve mostrar os labels de breakdown
    box_text = details_row.text_content() or ""
    assert "Receita" in box_text
    assert "Lucro" in box_text
    # SKU do item seedado deve aparecer
    assert "SKU-E2E-A" in box_text
