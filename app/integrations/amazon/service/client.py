# app/integrations/amazon/service/client.py
"""
Helpers compartilhados: credenciais, factory dos clientes SP-API e retry.
"""
import time

from sp_api.api import Orders, Finances
from sp_api.base import Marketplaces
from sp_api.base.exceptions import SellingApiRequestThrottledException

DEFAULT_SLEEP = 0.8


def _safe_payload(res, ctx: str):
    """Garante que temos um objeto response e payload."""
    if res is None:
        raise RuntimeError(f"SP-API retornou None em {ctx} (sem resposta).")
    payload = getattr(res, "payload", None)
    if payload is None:
        raise RuntimeError(f"SP-API sem payload em {ctx}. res={res!r}")
    return payload or {}


def marketplace_from_id(marketplace_id: str):
    if marketplace_id == Marketplaces.BR.marketplace_id:
        return Marketplaces.BR
    return Marketplaces.BR


def _credentials(conn):
    creds = {
        "refresh_token": conn.lwa_refresh_token,
        "lwa_app_id": conn.lwa_client_id,
        "lwa_client_secret": conn.lwa_client_secret,
        "aws_access_key": conn.aws_access_key_id,
        "aws_secret_key": conn.aws_secret_access_key,
    }
    if getattr(conn, "role_arn", None):
        creds["role_arn"] = conn.role_arn
    return creds


def make_orders_client(conn):
    return Orders(
        marketplace=marketplace_from_id(conn.marketplace_id),
        credentials=_credentials(conn),
    )


def make_finances_client(conn):
    return Finances(
        marketplace=marketplace_from_id(conn.marketplace_id),
        credentials=_credentials(conn),
    )


_RETRYABLE_NETWORK = (ConnectionError, TimeoutError, OSError)


def _with_retry(fn, *, max_retries=8, base_sleep=0.8, ctx=""):
    """
    Retry com backoff apenas para erros transitórios da SP-API:
    - SellingApiRequestThrottledException: backoff exponencial (rate limit)
    - ConnectionError / TimeoutError / OSError: backoff linear (rede)
    - Resposta None da lib: backoff exponencial (timeout interno)
    Qualquer outro erro é re-lançado imediatamente — não é transitório.
    """
    last_exc = None

    for i in range(max_retries):
        try:
            res = fn()

            if res is None:
                time.sleep(base_sleep * (2 ** i))
                continue

            return res

        except SellingApiRequestThrottledException as e:
            last_exc = e
            time.sleep(base_sleep * (2 ** i))

        except _RETRYABLE_NETWORK as e:
            last_exc = e
            time.sleep(base_sleep * (i + 1))

    if last_exc:
        raise last_exc

    raise RuntimeError(f"SP-API retornou None repetidamente {f'em {ctx}' if ctx else ''}.")
