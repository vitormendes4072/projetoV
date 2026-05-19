"""Testes dos handlers de erro globais."""
import pytest
from tests.conftest import auth_client


@pytest.fixture
def logged_client(client, db):
    return auth_client(client, db)


def test_404_returns_status(client):
    resp = client.get("/rota-que-nao-existe-xyz")
    assert resp.status_code == 404


def test_404_page_content(client):
    resp = client.get("/rota-que-nao-existe-xyz")
    assert b"404" in resp.data
    assert "text/html" in resp.content_type


def test_404_authenticated_still_404(logged_client):
    resp = logged_client.get("/rota-que-nao-existe-xyz")
    assert resp.status_code == 404
    assert b"404" in resp.data
