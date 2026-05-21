from datetime import datetime, timezone
from app import db
from app.models.custo_fixo_history import CustoFixoHistory

AUDIT_FIELDS = (
    "nome",
    "categoria",
    "valor_mensal",
    "dia_pagamento",
    "data_inicio",
    "data_fim",
    "ativo",
)

def _to_json_value(v):
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    # Decimal, etc:
    if not isinstance(v, (str, int, float, bool, list, dict)):
        return str(v)
    return v

def serialize_custo_fixo(item):
    return {f: _to_json_value(getattr(item, f, None)) for f in AUDIT_FIELDS}

def diff(before: dict, after: dict):
    changes = {}
    for k in before.keys():
        if before.get(k) != after.get(k):
            changes[k] = {"from": before.get(k), "to": after.get(k)}
    return changes

def log_change(*, item_id: int, action: str, user_id=None, before=None, after=None, note=None):
    payload_diff = None
    payload_snapshot = None

    if before is not None or after is not None:
        b = before or {}
        a = after or {}
        payload_diff = diff(b, a)
        payload_snapshot = {"before": b, "after": a}

    row = CustoFixoHistory(
        item_id=item_id,
        action=action,
        diff=payload_diff if payload_diff else None,
        snapshot=payload_snapshot,
        note=note,
        changed_by=user_id,
        changed_at=datetime.now(timezone.utc),
    )
    db.session.add(row)
