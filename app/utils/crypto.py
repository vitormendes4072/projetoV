# app/utils/crypto.py
import os
from cryptography.fernet import Fernet


def _get_fernet() -> Fernet:
    key = os.environ.get("CREDENTIALS_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("CREDENTIALS_ENCRYPTION_KEY não configurada.")
    return Fernet(key.encode())


def encrypt(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    f = _get_fernet()
    return f.encrypt(value.encode()).decode()


def decrypt(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    f = _get_fernet()
    return f.decrypt(value.encode()).decode()
