from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from mavuno.core.config import Settings


class InvalidAccessTokenError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AccessClaims:
    user_id: UUID
    token_version: int


class PasswordManager:
    def __init__(self) -> None:
        self._hasher = PasswordHasher()
        self._dummy_hash = self._hasher.hash("mavuno-dummy-password-never-used")

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False

    def verify_unknown(self, password: str) -> None:
        """Spend an Argon2 verification for identifiers that do not exist."""
        self.verify(self._dummy_hash, password)


class TokenManager:
    def __init__(self, settings: Settings) -> None:
        self._issuer = settings.auth_issuer
        self._audience = settings.auth_audience
        self._active_key_id = settings.auth_active_key_id
        self._keys = {
            key_id: secret.get_secret_value()
            for key_id, secret in settings.auth_signing_keys.items()
        }
        self.access_ttl = timedelta(minutes=settings.auth_access_token_minutes)
        self.refresh_ttl = timedelta(days=settings.auth_refresh_token_days)

    def create_access_token(self, user_id: UUID, token_version: int) -> str:
        now = datetime.now(UTC)
        payload: dict[str, Any] = {
            "sub": str(user_id),
            "ver": token_version,
            "iss": self._issuer,
            "aud": self._audience,
            "iat": now,
            "exp": now + self.access_ttl,
            "jti": str(uuid4()),
        }
        return jwt.encode(
            payload,
            self._keys[self._active_key_id],
            algorithm="HS256",
            headers={"kid": self._active_key_id},
        )

    def decode_access_token(self, token: str) -> AccessClaims:
        try:
            header = jwt.get_unverified_header(token)
            key_id = header.get("kid")
            if not isinstance(key_id, str) or key_id not in self._keys:
                raise InvalidAccessTokenError("Unknown signing key")
            payload = jwt.decode(
                token,
                self._keys[key_id],
                algorithms=["HS256"],
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["sub", "ver", "iss", "aud", "iat", "exp", "jti"]},
            )
            token_version = payload["ver"]
            if not isinstance(token_version, int) or isinstance(token_version, bool):
                raise InvalidAccessTokenError("Invalid token version")
            return AccessClaims(user_id=UUID(payload["sub"]), token_version=token_version)
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, InvalidAccessTokenError):
                raise
            raise InvalidAccessTokenError("Invalid access token") from exc

    @staticmethod
    def create_refresh_token() -> str:
        return secrets.token_urlsafe(48)

    @staticmethod
    def hash_refresh_token(token: str) -> bytes:
        return hashlib.sha256(token.encode("utf-8")).digest()
