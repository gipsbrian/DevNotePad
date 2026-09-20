"""Encryption for GitHub tokens at rest.

Tokens are encrypted rather than hashed: the app has to present the real
token to GitHub, so the transformation has to be reversible. Fernet
(AES-CBC + HMAC, from `cryptography`) is the standard primitive for that,
keyed by SECRET_KEY in the environment.
"""

from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from .config import settings

# Marks a value this module wrote. Anything without it was stored before
# encryption existed and is handed back as-is, so an existing database
# keeps working until `encrypt_stored_tokens` rewrites it.
PREFIX = "enc.v1."

GENERATE_HINT = (
    "Generate one with: python -c "
    "'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
)


class MissingEncryptionKey(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = settings.secret_key
    if not key:
        raise MissingEncryptionKey(f"SECRET_KEY is not set. {GENERATE_HINT}")
    return Fernet(key.encode())


def encrypt(value: str) -> str:
    return PREFIX + _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> Optional[str]:
    if not value.startswith(PREFIX):
        return value
    try:
        return _fernet().decrypt(value[len(PREFIX) :].encode()).decode()
    except (InvalidToken, MissingEncryptionKey):
        # A rotated or lost key shouldn't take the app down with it. The
        # token reads as absent, which the UI already handles, and can be
        # entered again.
        return None


class EncryptedToken(TypeDecorator):
    """Encrypts on the way into SQLite and decrypts on the way back, so
    callers keep handling a plain string and no call site can forget."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Optional[str], dialect) -> Optional[str]:
        return None if value is None else encrypt(value)

    def process_result_value(self, value: Optional[str], dialect) -> Optional[str]:
        return None if value is None else decrypt(value)
