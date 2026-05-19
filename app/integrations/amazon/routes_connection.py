import logging
import uuid
from datetime import timedelta

from flask import request, jsonify
from flask_login import login_required

from app import db
from app.models import AmazonConnection
from app.integrations.amazon import amazon
from app.integrations.amazon.utils import user_key, utcnow, iso_z
from app.integrations.amazon.service import list_orders

logger = logging.getLogger(__name__)


@amazon.get("/status")
@login_required
def status():
    conn = db.session.scalar(db.select(AmazonConnection).filter_by(user_id=user_key()))
    if not conn:
        return jsonify({"ok": True, "connected": False})

    return jsonify({
        "ok": True,
        "connected": True,
        "marketplace_id": conn.marketplace_id,
        "last_sync_at": conn.last_sync_at.isoformat() if conn.last_sync_at else None,
    })


@amazon.post("/connect")
@login_required
def connect():
    data = request.get_json(force=True) or {}
    logger.debug("Amazon connect payload: %s", data)

    required = [
        "marketplace_id",
        "lwa_client_id",
        "lwa_client_secret",
        "lwa_refresh_token",
        "aws_access_key_id",
        "aws_secret_access_key",
    ]
    missing = [k for k in required if not data.get(k)]
    if missing:
        return jsonify({"ok": False, "error": f"Faltando: {', '.join(missing)}"}), 400

    conn = db.session.scalar(db.select(AmazonConnection).filter_by(user_id=user_key()))
    if not conn:
        conn = AmazonConnection(id=uuid.uuid4(), user_id=user_key())

    conn.marketplace_id = data["marketplace_id"].strip()
    conn.seller_id = data.get("seller_id") or None

    conn.lwa_client_id = data["lwa_client_id"].strip()
    conn.lwa_client_secret = data["lwa_client_secret"]
    conn.lwa_refresh_token = data["lwa_refresh_token"]

    conn.aws_access_key_id = data["aws_access_key_id"].strip()
    conn.aws_secret_access_key = data["aws_secret_access_key"]
    conn.aws_region = (data.get("aws_region") or "us-east-1").strip()
    conn.role_arn = data.get("role_arn") or None

    db.session.add(conn)
    db.session.commit()

    return jsonify({"ok": True})


@amazon.post("/test")
@login_required
def test_connection():
    conn = db.session.scalar(db.select(AmazonConnection).filter_by(user_id=user_key()))
    if not conn:
        return jsonify({"ok": False, "error": "Integração Amazon não configurada"}), 400

    created_after = iso_z(utcnow() - timedelta(days=2))

    try:
        orders = list_orders(conn, created_after_iso=created_after)
        return jsonify({"ok": True, "orders_found": len(orders), "created_after": created_after})
    except Exception:
        logger.exception("Erro ao testar conexão Amazon")
        return jsonify({"ok": False, "error": "Falha ao conectar com a SP-API", "created_after": created_after}), 400
