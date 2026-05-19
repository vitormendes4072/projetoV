import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask_login import current_user

SP_TZ = ZoneInfo("America/Sao_Paulo")


def user_key() -> int:
    return current_user.id


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(dt: datetime) -> str:
    """Converte datetime para ISO8601 aceito pela Amazon: sem micros + com 'Z' no final."""
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def extract_amount_currency(ev: dict):
    """
    Tenta extrair (amount, currency) de múltiplos formatos possíveis do payload.
    Retorna (amount: float|None, currency: str|None)
    """
    candidates = ("FeeAmount", "ChargeAmount", "Amount", "AdjustmentAmount")
    for k in candidates:
        v = ev.get(k)
        if isinstance(v, dict):
            if "CurrencyAmount" in v:
                return v.get("CurrencyAmount"), v.get("CurrencyCode")
            if "Amount" in v:
                return v.get("Amount"), v.get("CurrencyCode")
            if "amount" in v:
                return v.get("amount"), v.get("currencyCode") or v.get("currency")
        if isinstance(v, (int, float)):
            return v, None
    return None, None


def parse_iso_dt(s: str):
    """Parse ISO da Amazon (ex: '2026-01-21T00:00:00Z') para datetime timezone-aware."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def to_sp(dt):
    return dt.astimezone(SP_TZ) if dt else None


def compute_sync_start(conn, days_default: int) -> datetime:
    """
    Janela incremental:
      - se last_sync_at existir => last_sync_at - 2 dias (buffer)
      - senão => agora - days_default
    """
    now = utcnow()
    if getattr(conn, "last_sync_at", None):
        return conn.last_sync_at - timedelta(days=2)
    return now - timedelta(days=days_default)


def dev_guard() -> bool:
    """Bloqueia endpoints DEV fora de ambiente dev."""
    dev_only = os.getenv("DEV_ONLY_ENDPOINTS", "false").lower() == "true"
    flask_env = os.getenv("FLASK_ENV", "").lower()
    if not dev_only or flask_env not in ("development", "dev"):
        return False
    return True
