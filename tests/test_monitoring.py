# tests/test_monitoring.py
"""Testes para os endpoints /livez, /readyz e /metrics."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# /livez
# ---------------------------------------------------------------------------

class TestLivez:
    def test_livez_returns_200(self, client):
        resp = client.get("/livez")
        assert resp.status_code == 200

    def test_livez_body(self, client):
        data = client.get("/livez").get_json()
        assert data == {"status": "ok"}


# ---------------------------------------------------------------------------
# /readyz — estado normal
# ---------------------------------------------------------------------------

class TestReadyzOk:
    def test_readyz_200_when_db_and_redis_ok(self, client, db):
        """DB acessível + Redis (fakeredis) configurado → 200."""
        resp = client.get("/readyz")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["checks"]["db"] == "ok"

    def test_readyz_has_db_check(self, client, db):
        resp = client.get("/readyz")
        assert "db" in resp.get_json()["checks"]

    def test_readyz_has_redis_check(self, client, db):
        resp = client.get("/readyz")
        assert "redis" in resp.get_json()["checks"]

    def test_readyz_redis_ok_when_queue_configured(self, client, db):
        """fakeredis está configurado nos testes → redis deve ser 'ok'."""
        data = client.get("/readyz").get_json()
        # fakeredis responde ping() corretamente
        assert data["checks"]["redis"] == "ok"


# ---------------------------------------------------------------------------
# /readyz — falha de DB
# ---------------------------------------------------------------------------

class TestReadyzDbFailure:
    def test_readyz_503_when_db_fails(self, client, db):
        from sqlalchemy.exc import OperationalError

        with patch("app.monitoring.db") as mock_db:
            mock_db.session.execute.side_effect = OperationalError(
                "connection refused", {}, None
            )
            resp = client.get("/readyz")

        assert resp.status_code == 503
        data = resp.get_json()
        assert data["status"] == "degraded"
        assert "error" in data["checks"]["db"]

    def test_readyz_db_error_message_present(self, client, db):
        from sqlalchemy.exc import OperationalError

        with patch("app.monitoring.db") as mock_db:
            mock_db.session.execute.side_effect = OperationalError(
                "timeout", {}, None
            )
            data = client.get("/readyz").get_json()

        assert data["checks"]["db"].startswith("error:")


# ---------------------------------------------------------------------------
# /readyz — falha de Redis
# ---------------------------------------------------------------------------

class TestReadyzRedisFailure:
    def test_readyz_503_when_redis_ping_fails(self, client, db, app):
        """Se o ping do Redis falha → 503 degraded."""
        mock_queue = MagicMock()
        mock_queue.connection.ping.side_effect = ConnectionError("redis down")

        with app.app_context():
            original = app.extensions.get("rq_queue")
            app.extensions["rq_queue"] = mock_queue
            try:
                resp = client.get("/readyz")
            finally:
                app.extensions["rq_queue"] = original

        assert resp.status_code == 503
        data = resp.get_json()
        assert data["status"] == "degraded"
        assert "error" in data["checks"]["redis"]

    def test_readyz_dev_not_configured_is_ok(self, client, db, app):
        """Em dev (APP_ENV != production), Redis 'not configured' não degrada."""
        import os

        with app.app_context():
            original = app.extensions.pop("rq_queue", None)
            try:
                with patch.dict(os.environ, {}, clear=False):
                    # garantir que APP_ENV não é production
                    os.environ.pop("APP_ENV", None)
                    resp = client.get("/readyz")
            finally:
                if original is not None:
                    app.extensions["rq_queue"] = original

        data = resp.get_json()
        assert data["checks"]["redis"] == "not configured"
        # sem Redis em dev não é erro crítico → status depende apenas do DB
        assert data["checks"]["db"] == "ok"

    def test_readyz_prod_not_configured_is_503(self, client, db, app):
        """Em produção, Redis 'not configured' deve degradar → 503."""
        import os

        with app.app_context():
            original = app.extensions.pop("rq_queue", None)
            try:
                with patch.dict(os.environ, {"APP_ENV": "production"}):
                    resp = client.get("/readyz")
            finally:
                if original is not None:
                    app.extensions["rq_queue"] = original

        assert resp.status_code == 503
        data = resp.get_json()
        assert data["status"] == "degraded"
        assert data["checks"]["redis"] == "not configured"


# ---------------------------------------------------------------------------
# /metrics
# ---------------------------------------------------------------------------

class TestMetrics:
    def test_metrics_returns_200(self, client):
        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_metrics_content_type_is_text(self, client):
        resp = client.get("/metrics")
        assert "text/plain" in resp.content_type

    def test_metrics_contains_prometheus_output(self, client):
        """Deve conter pelo menos uma linha de métrica Prometheus."""
        body = client.get("/metrics").data.decode()
        # Prometheus output sempre tem linhas # HELP ou # TYPE
        assert "# HELP" in body or "# TYPE" in body
