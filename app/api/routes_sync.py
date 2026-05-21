from flask import current_app
from flask_login import current_user
from flask_smorest import abort

from app import db
from app.api import blp
from app.api.schemas import SyncQueryArgsSchema, JobQueuedSchema, JobStatusSchema
from app.models import AmazonConnection
from app.monitoring import amazon_sync_total


def _queue():
    return current_app.extensions["rq_queue"]


def _get_conn():
    conn = db.session.scalar(db.select(AmazonConnection).filter_by(user_id=current_user.id))
    if not conn:
        abort(400, message="Integração Amazon não configurada")
    return conn


@blp.post("/amazon/sync/orders")
@blp.arguments(SyncQueryArgsSchema, location="query")
@blp.response(202, JobQueuedSchema, description="Job enfileirado com sucesso")
def api_sync_orders(args):
    """Enfileira sincronização de pedidos Amazon.

    Retorna um `job_id` que pode ser consultado em `GET /amazon/jobs/{job_id}`.
    """
    from app.integrations.amazon.jobs import job_sync_orders
    conn = _get_conn()
    job = _queue().enqueue(job_sync_orders, current_user.id, conn.id, args["days"], job_timeout=300)
    amazon_sync_total.labels(type="orders").inc()
    return {"ok": True, "job_id": job.id, "status": "queued"}, 202


@blp.post("/amazon/sync/finances")
@blp.arguments(SyncQueryArgsSchema, location="query")
@blp.response(202, JobQueuedSchema, description="Job enfileirado com sucesso")
def api_sync_finances(args):
    """Enfileira sincronização de eventos financeiros Amazon.

    Retorna um `job_id` que pode ser consultado em `GET /amazon/jobs/{job_id}`.
    """
    from app.integrations.amazon.jobs import job_sync_finances
    conn = _get_conn()
    job = _queue().enqueue(job_sync_finances, current_user.id, conn.id, args.get("days", 7), job_timeout=300)
    amazon_sync_total.labels(type="finances").inc()
    return {"ok": True, "job_id": job.id, "status": "queued"}, 202


@blp.post("/amazon/sync/full")
@blp.arguments(SyncQueryArgsSchema, location="query")
@blp.response(202, JobQueuedSchema, description="Job enfileirado com sucesso")
def api_sync_full(args):
    """Enfileira sincronização completa (pedidos + itens + eventos financeiros).

    Retorna um `job_id` que pode ser consultado em `GET /amazon/jobs/{job_id}`.
    """
    from app.integrations.amazon.jobs import job_sync_full
    conn = _get_conn()
    job = _queue().enqueue(job_sync_full, current_user.id, conn.id, args["days"], job_timeout=600)
    amazon_sync_total.labels(type="full").inc()
    return {"ok": True, "job_id": job.id, "status": "queued"}, 202


@blp.get("/amazon/jobs/<job_id>")
@blp.response(200, JobStatusSchema, description="Status atual do job")
def api_job_status(job_id):
    """Consulta o status de um job assíncrono de sincronização.

    Possíveis valores de `status`: `queued`, `started`, `finished`, `failed`.
    O campo `result` é preenchido quando o job finaliza com sucesso.
    """
    from rq.job import Job
    from rq.exceptions import NoSuchJobError

    queue = _queue()
    try:
        job = Job.fetch(job_id, connection=queue.connection)
    except NoSuchJobError:
        abort(404, message="Job não encontrado")

    status = job.get_status(refresh=True)
    payload = {
        "ok": True,
        "job_id": job_id,
        "status": str(status),
        "result": None,
        "error": None,
    }

    if status.value == "finished":
        payload["result"] = job.result
    elif status.value == "failed":
        payload["error"] = str(job.latest_result().exc_string) if job.latest_result() else "unknown"

    return payload
