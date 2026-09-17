from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from mavuno.core.config import Settings

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, settings: Settings, *, engine: AsyncEngine | None = None) -> None:
        if settings.database_url is None:
            raise ValueError("MAVUNO_DATABASE_URL is required to configure the database")

        self.engine = engine or create_async_engine(
            settings.database_url.get_secret_value(),
            pool_pre_ping=True,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_recycle=settings.database_pool_recycle_seconds,
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session

    async def is_ready(self) -> bool:
        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            logger.warning(
                "Database readiness check failed", extra={"error_type": type(exc).__name__}
            )
            return False
        return True

    async def dispose(self) -> None:
        await self.engine.dispose()
