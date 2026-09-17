from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import delete, select

from mavuno.auth.security import PasswordManager
from mavuno.core.config import Settings
from mavuno.db import Database
from mavuno.db.models import Profile, RefreshToken, User
from mavuno.main import create_app

TEST_DATABASE_URL = os.getenv("MAVUNO_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="MAVUNO_TEST_DATABASE_URL is not set"),
]


@pytest.mark.anyio
async def test_complete_authentication_lifecycle_and_reuse_detection() -> None:
    assert TEST_DATABASE_URL is not None
    email = f"auth-{uuid4()}@example.com"
    phone = "0712345678"
    settings = Settings(environment="test", database_url=SecretStr(TEST_DATABASE_URL))
    app = create_app(settings)

    try:
        with TestClient(app) as client:
            registered = client.post(
                "/api/v1/auth/register",
                json={
                    "email": email.upper(),
                    "phone": phone,
                    "password": "a-long-test-password",
                    "role": "farmer",
                },
            )
            assert registered.status_code == 201, registered.text
            original = registered.json()
            assert original["user"]["email"] == email
            assert original["user"]["phone_e164"] == "+254712345678"
            assert original["user"]["roles"] == ["farmer"]

            invalid_phone = client.post(
                "/api/v1/auth/register",
                json={"phone": "1234567", "password": "another-long-password"},
            )
            assert invalid_phone.status_code == 422
            assert invalid_phone.json()["error"]["code"] == "invalid_phone"

            me = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {original['access_token']}"},
            )
            assert me.status_code == 200
            assert me.json()["id"] == original["user"]["id"]

            duplicate = client.post(
                "/api/v1/auth/register",
                json={"email": email, "password": "another-long-password"},
            )
            assert duplicate.status_code == 409
            assert duplicate.json()["error"]["code"] == "identifier_unavailable"

            bad_login = client.post(
                "/api/v1/auth/login",
                json={"identifier": "absent@example.com", "password": "wrong"},
            )
            assert bad_login.status_code == 401
            assert bad_login.json()["error"]["code"] == "invalid_credentials"
            wrong_password = client.post(
                "/api/v1/auth/login",
                json={"identifier": email, "password": "wrong"},
            )
            assert wrong_password.status_code == 401

            unknown_refresh = client.post("/api/v1/auth/refresh", json={"refresh_token": "x" * 64})
            assert unknown_refresh.status_code == 401
            assert unknown_refresh.json()["error"]["code"] == "invalid_refresh_token"

            refreshed = client.post(
                "/api/v1/auth/refresh", json={"refresh_token": original["refresh_token"]}
            )
            assert refreshed.status_code == 200
            replacement = refreshed.json()
            assert replacement["refresh_token"] != original["refresh_token"]

            reused = client.post(
                "/api/v1/auth/refresh", json={"refresh_token": original["refresh_token"]}
            )
            assert reused.status_code == 401
            assert reused.json()["error"]["code"] == "refresh_token_reuse"

            invalidated = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {replacement['access_token']}"},
            )
            assert invalidated.status_code == 401

            logged_in = client.post(
                "/api/v1/auth/login",
                json={"identifier": phone, "password": "a-long-test-password"},
            )
            assert logged_in.status_code == 200
            current = logged_in.json()
            invalid_logout = client.post(
                "/api/v1/auth/logout",
                json={"refresh_token": "x" * 64},
                headers={"Authorization": f"Bearer {current['access_token']}"},
            )
            assert invalid_logout.status_code == 401
            logged_out = client.post(
                "/api/v1/auth/logout",
                json={"refresh_token": current["refresh_token"]},
                headers={"Authorization": f"Bearer {current['access_token']}"},
            )
            assert logged_out.status_code == 200
            assert logged_out.json() == {"revoked": True}
    finally:
        database = Database(settings)
        try:
            async with database.session() as session:
                user_id = await session.scalar(select(User.id).where(User.email == email))
                if user_id is not None:
                    profile = await session.get(Profile, user_id)
                    assert profile is not None
                    assert profile.display_name == "Mavuno User"
                    await session.execute(
                        delete(RefreshToken).where(RefreshToken.user_id == user_id)
                    )
                    await session.execute(delete(User).where(User.id == user_id))
                    await session.commit()
        finally:
            await database.dispose()


@pytest.mark.anyio
async def test_password_is_stored_as_argon2id_hash() -> None:
    assert TEST_DATABASE_URL is not None
    email = f"hash-{uuid4()}@example.com"
    password = "a-different-long-password"
    settings = Settings(environment="test", database_url=SecretStr(TEST_DATABASE_URL))
    database = Database(settings)
    app = create_app(settings)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/auth/register", json={"email": email, "password": password}
            )
            assert response.status_code == 201
        async with database.session() as session:
            user = await session.scalar(select(User).where(User.email == email))
            assert user is not None
            assert user.password_hash.startswith("$argon2id$")
            assert user.password_hash != password
            assert PasswordManager().verify(user.password_hash, password)
            await session.delete(user)
            await session.commit()
    finally:
        await database.dispose()
