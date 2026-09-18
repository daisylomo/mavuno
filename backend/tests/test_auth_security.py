from __future__ import annotations

from uuid import uuid4

import jwt
import pytest
from pydantic import SecretStr, ValidationError

from mavuno.auth.context import AuthenticatedUser
from mavuno.auth.normalization import normalize_email, normalize_login_identifier, normalize_phone
from mavuno.auth.schemas import RegisterRequest
from mavuno.auth.security import InvalidAccessTokenError, PasswordManager, TokenManager
from mavuno.core.config import Settings


def auth_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "auth_active_key_id": "current",
        "auth_signing_keys": {
            "old": SecretStr("o" * 32),
            "current": SecretStr("c" * 32),
        },
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_password_hash_and_verification() -> None:
    manager = PasswordManager()
    hashed = manager.hash("correct horse battery staple")

    assert hashed.startswith("$argon2id$")
    assert manager.verify(hashed, "correct horse battery staple") is True
    assert manager.verify(hashed, "wrong") is False
    assert manager.verify("not-a-hash", "wrong") is False
    manager.verify_unknown("some-password")


def test_access_token_round_trip_and_active_kid() -> None:
    manager = TokenManager(auth_settings())
    user_id = uuid4()
    token = manager.create_access_token(user_id, 7)

    assert jwt.get_unverified_header(token)["kid"] == "current"
    assert manager.decode_access_token(token).user_id == user_id
    assert manager.decode_access_token(token).token_version == 7


@pytest.mark.parametrize(
    "token",
    [
        "not-a-jwt",
        jwt.encode(
            {
                "sub": str(uuid4()),
                "ver": 0,
                "iss": "mavuno-api",
                "aud": "mavuno-mobile",
                "iat": 1,
                "exp": 4_000_000_000,
                "jti": str(uuid4()),
            },
            "x" * 32,
            algorithm="HS256",
            headers={"kid": "unknown"},
        ),
    ],
)
def test_invalid_access_tokens_are_rejected(token: str) -> None:
    with pytest.raises(InvalidAccessTokenError):
        TokenManager(auth_settings()).decode_access_token(token)


def test_access_token_rejects_non_integer_version() -> None:
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "ver": "zero",
            "iss": "mavuno-api",
            "aud": "mavuno-mobile",
            "iat": 1,
            "exp": 4_000_000_000,
            "jti": str(uuid4()),
        },
        "c" * 32,
        algorithm="HS256",
        headers={"kid": "current"},
    )
    with pytest.raises(InvalidAccessTokenError, match="version"):
        TokenManager(auth_settings()).decode_access_token(token)


def test_refresh_tokens_are_opaque_random_and_hashable() -> None:
    first = TokenManager.create_refresh_token()
    second = TokenManager.create_refresh_token()

    assert first != second
    assert len(first) >= 64
    assert len(TokenManager.hash_refresh_token(first)) == 32
    assert TokenManager.hash_refresh_token(first) == TokenManager.hash_refresh_token(first)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0712 345 678", "+254712345678"),
        ("+254712345678", "+254712345678"),
        ("+12025550123", "+12025550123"),
    ],
)
def test_phone_normalization(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected


def test_identifier_normalization_and_validation() -> None:
    assert normalize_email(" Person@Example.COM ") == "person@example.com"
    assert normalize_login_identifier("Person@Example.COM") == ("email", "person@example.com")
    assert normalize_login_identifier("0712345678") == ("phone_e164", "+254712345678")
    with pytest.raises(ValueError):
        normalize_phone("123")
    with pytest.raises(ValueError):
        normalize_phone("not a phone number")


def test_registration_requires_identifier() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(password="long-enough-password")


def test_authenticated_user_role_check() -> None:
    user = AuthenticatedUser(uuid4(), None, "+254712345678", frozenset({"farmer"}), 0)
    assert user.has_role("farmer") is True
    assert user.has_role("buyer", "support") is False


def test_auth_settings_validate_rotation_configuration() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="production")
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            auth_active_key_id="missing",
            auth_signing_keys={"other": SecretStr("x" * 32)},
        )
    with pytest.raises(ValidationError):
        auth_settings(auth_signing_keys={"current": SecretStr("short")})
