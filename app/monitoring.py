# app/monitoring.py
import time

from flask import Blueprint, Flask, Response, jsonify
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)

monitoring_bp = Blueprint("monitoring", __name__)

# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------

http_requests_total = Counter(
    "http_requests_total",
    "Total de requisições HTTP",
    ["method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "Latência das requisições HTTP",
    ["method", "endpoint"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

amazon_sync_total = Counter(
    "amazon_sync_total",
    "Jobs de sincronização Amazon enfileirados",
    ["type"],
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@monitoring_bp.get("/livez")
def livez():
    return jsonify({"status": "ok"})


@monitoring_bp.get("/readyz")
def readyz():
    from sqlalchemy import text
    from flask import current_app
    from app import db

    checks: dict = {}
    ok = True

    try:
        db.session.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as exc:
        checks["db"] = f"error: {exc}"
        ok = False

    try:
        queue = current_app.extensions.get("rq_queue")
        if queue:
            queue.connection.ping()
            checks["redis"] = "ok"
        else:
            checks["redis"] = "not configured"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"
        ok = False

    return jsonify({"status": "ok" if ok else "degraded", "checks": checks}), (200 if ok else 503)


@monitoring_bp.get("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

def init_monitoring(app: Flask) -> None:
    from app import csrf

    app.register_blueprint(monitoring_bp)
    csrf.exempt(monitoring_bp)

    if app.testing:
        return

    @app.before_request
    def _start_timer():
        from flask import g
        g._req_start = time.monotonic()

    @app.after_request
    def _record_metrics(response):
        from flask import g, request
        endpoint = request.endpoint or "unknown"
        elapsed = time.monotonic() - getattr(g, "_req_start", time.monotonic())
        http_requests_total.labels(
            method=request.method,
            endpoint=endpoint,
            status=str(response.status_code),
        ).inc()
        http_request_duration_seconds.labels(
            method=request.method,
            endpoint=endpoint,
        ).observe(elapsed)
        return response
