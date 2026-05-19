"""
Testes unitários para app/utils/crypto.py — encrypt/decrypt de credenciais.
"""
import os
from unittest.mock import patch
from cryptography.fernet import Fernet

from app.utils.crypto import encrypt, decrypt


# Gera uma chave válida para os testes
_TEST_KEY = Fernet.generate_key().decode()


def _with_key(fn):
    """Decorator: injeta CREDENTIALS_ENCRYPTION_KEY para o teste."""
    def wrapper(*args, **kwargs):
        with patch.dict(os.environ, {"CREDENTIALS_ENCRYPTION_KEY": _TEST_KEY}):
            return fn(*args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper


# ---------------------------------------------------------------------------
# encrypt
# ---------------------------------------------------------------------------

@_with_key
def test_encrypt_returns_string():
    result = encrypt("minha_senha_secreta")
    assert isinstance(result, str)
    assert result != "minha_senha_secreta"


@_with_key
def test_encrypt_none_returns_none():
    assert encrypt(None) is None


@_with_key
def test_encrypt_empty_string_returns_none():
    assert encrypt("") is None


# ---------------------------------------------------------------------------
# decrypt
# ---------------------------------------------------------------------------

@_with_key
def test_decrypt_roundtrip():
    original = "valor_secreto_123"
    encrypted = encrypt(original)
    decrypted = decrypt(encrypted)
    assert decrypted == original


@_with_key
def test_decrypt_none_returns_none():
    assert decrypt(None) is None


@_with_key
def test_decrypt_empty_returns_none():
    assert decrypt("") is None


# ---------------------------------------------------------------------------
# Sem chave configurada → RuntimeError
# ---------------------------------------------------------------------------

def test_encrypt_no_key_raises():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("CREDENTIALS_ENCRYPTION_KEY", None)
        try:
            encrypt("test")
            assert False, "deveria ter levantado RuntimeError"
        except RuntimeError:
            pass
