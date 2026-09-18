from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from mavuno.core.config import Settings
from mavuno.db import Base, Database
from mavuno.db.base import UUIDBinary
from mavuno.db.models import identity as identity_models


def database_settings() -> Settings:
    return Settings(
        environment="test",
        database_url=SecretStr("mysql+aiomysql://user:password@database/mavuno"),
    )


def engine_mock() -> tuple[MagicMock, AsyncMock]:
    engine = MagicMock(spec=AsyncEngine)
    connection = AsyncMock()
    connection_context = MagicMock()
    connection_context.__aenter__ = AsyncMock(return_value=connection)
    connection_context.__aexit__ = AsyncMock(return_value=None)
    engine.connect.return_value = connection_context
    engine.dispose = AsyncMock()
    return engine, connection


def test_database_url_is_required() -> None:
    with pytest.raises(ValueError, match="MAVUNO_DATABASE_URL"):
        Database(Settings(environment="test"))


@pytest.mark.anyio
async def test_database_readiness_and_disposal() -> None:
    engine, connection = engine_mock()
    database = Database(database_settings(), engine=engine)

    assert await database.is_ready() is True
    connection.execute.assert_awaited_once()

    async with database.session() as session:
        assert isinstance(session, AsyncSession)

    await database.dispose()
    engine.dispose.assert_awaited_once()


@pytest.mark.anyio
async def test_database_readiness_handles_driver_errors() -> None:
    engine, connection = engine_mock()
    connection.execute.side_effect = OperationalError("SELECT 1", {}, RuntimeError("offline"))
    database = Database(database_settings(), engine=engine)

    assert await database.is_ready() is False


def test_uuid_binary_round_trip() -> None:
    value = uuid4()
    uuid_type = UUIDBinary()

    stored = uuid_type.process_bind_param(str(value), object())

    assert stored == value.bytes
    assert uuid_type.process_result_value(stored, object()) == value
    assert uuid_type.process_bind_param(None, object()) is None
    assert uuid_type.process_result_value(None, object()) is None


def test_identity_metadata_contains_baseline_tables() -> None:
    assert identity_models
    assert set(Base.metadata.tables) == {
        "addresses",
        "buyer_profiles",
        "device_installations",
        "farmer_profiles",
        "inventory_movements",
        "listing_images",
        "listings",
        "produce_categories",
        "products",
        "profiles",
        "profile_audit_events",
        "refresh_tokens",
        "roles",
        "user_roles",
        "users",
    }
