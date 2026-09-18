from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from mavuno.core.config import Settings
from mavuno.db import Database
from mavuno.db.models import DeviceInstallation, ProfileAuditEvent, User
from mavuno.main import create_app

TEST_DATABASE_URL = os.getenv("MAVUNO_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="MAVUNO_TEST_DATABASE_URL is not set"),
]


@pytest.mark.anyio
async def test_database_connectivity_and_baseline_tables() -> None:
    assert TEST_DATABASE_URL is not None
    database = Database(
        Settings(environment="test", database_url=SecretStr(TEST_DATABASE_URL)),
    )

    try:
        assert await database.is_ready() is True
        async with database.session() as session:
            result = await session.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = DATABASE() AND table_name IN "
                    "('users', 'roles', 'profiles', 'refresh_tokens')"
                )
            )
            assert result.scalar_one() == 4

            roles = await session.execute(text("SELECT COUNT(*) FROM roles"))
            assert roles.scalar_one() == 4
    finally:
        await database.dispose()


@pytest.mark.anyio
async def test_identity_constraints_are_enforced() -> None:
    assert TEST_DATABASE_URL is not None
    database = Database(
        Settings(environment="test", database_url=SecretStr(TEST_DATABASE_URL)),
    )

    try:
        async with database.session() as session:
            session.add(
                User(
                    email=f"constraint-{uuid4()}@example.test",
                    password_hash="not-a-real-hash",
                    status="active",
                )
            )
            await session.commit()

        async with database.session() as session:
            session.add(User(password_hash="not-a-real-hash", status="active"))
            with pytest.raises(DBAPIError):
                await session.commit()
            await session.rollback()
    finally:
        await database.dispose()


def test_readiness_endpoint_checks_mysql() -> None:
    assert TEST_DATABASE_URL is not None
    app = create_app(
        Settings(environment="test", database_url=SecretStr(TEST_DATABASE_URL)),
    )

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@pytest.mark.anyio
async def test_profile_audit_and_installation_uniqueness() -> None:
    assert TEST_DATABASE_URL is not None
    database = Database(
        Settings(environment="test", database_url=SecretStr(TEST_DATABASE_URL)),
    )
    user_id = uuid4()
    installation_id = uuid4()

    try:
        async with database.session() as session:
            session.add(
                User(
                    id=user_id,
                    email=f"profile-{user_id}@example.test",
                    password_hash="not-a-real-hash",
                    status="active",
                )
            )
            await session.flush()
            session.add(
                DeviceInstallation(
                    user_id=user_id,
                    installation_id=installation_id,
                    platform="android",
                    push_token_ciphertext=b"c" * 6000,
                    push_token_hash=b"a" * 32,
                )
            )
            session.add(
                ProfileAuditEvent(
                    user_id=user_id,
                    actor_user_id=user_id,
                    action="created",
                    entity_type="device_installation",
                    entity_id=installation_id,
                    changed_fields=["platform", "push_token"],
                )
            )
            await session.commit()

        async with database.session() as session:
            audit_count = await session.execute(
                text("SELECT COUNT(*) FROM profile_audit_events WHERE user_id = :user_id"),
                {"user_id": user_id.bytes},
            )
            assert audit_count.scalar_one() == 1
            session.add(
                DeviceInstallation(
                    user_id=user_id,
                    installation_id=installation_id,
                    platform="ios",
                )
            )
            with pytest.raises(IntegrityError):
                await session.commit()
            await session.rollback()
    finally:
        async with database.session() as session:
            await session.execute(
                text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id.bytes}
            )
            await session.commit()
        await database.dispose()
