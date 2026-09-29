from __future__ import annotations

import hashlib
import hmac

from cryptography.fernet import Fernet
from pydantic import SecretStr


def validate_fernet_key(value: str) -> None:
    try:
        Fernet(value.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise ValueError("push_token_encryption_key must be a URL-safe base64 Fernet key") from exc


class PushTokenProtector:
    """Encrypt delivery tokens and derive a separate stable lookup digest."""

    def __init__(self, *, encryption_key: SecretStr, hash_key: SecretStr) -> None:
        encryption_value = encryption_key.get_secret_value()
        hash_value = hash_key.get_secret_value()
        validate_fernet_key(encryption_value)
        if encryption_value == hash_value:
            raise ValueError("Push-token hash and encryption keys must be distinct")
        self._fernet = Fernet(encryption_value.encode("ascii"))
        self._hash_key = hash_value.encode("utf-8")

    def protect(self, token: str) -> tuple[bytes, bytes]:
        plaintext = token.encode("utf-8")
        return self._fernet.encrypt(plaintext), hmac.new(
            self._hash_key, plaintext, hashlib.sha256
        ).digest()

    def decrypt(self, ciphertext: bytes) -> str:
        """Decrypt for the notification provider boundary; never use in logs or API responses."""
        return self._fernet.decrypt(ciphertext).decode("utf-8")
