from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from mavuno.core.config import Settings
from mavuno.core.performance import CatalogCache, PerformanceMetrics, record_query

logger = logging.getLogger(__name__)


class Database:
    def __init__(
        self,
        settings: Settings,
        *,
        engine: AsyncEngine | None = None,
        metrics: PerformanceMetrics | None = None,
    ) -> None:
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
        self._metrics = metrics
        self.catalog_cache: CatalogCache | None = None
        self._slow_query_seconds = settings.database_slow_query_ms / 1000
        if isinstance(self.engine.sync_engine, Engine):
            self._install_observers()

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

    def _install_observers(self) -> None:
        @event.listens_for(self.engine.sync_engine, "before_cursor_execute")
        def before_cursor_execute(
            _connection: Any,
            _cursor: Any,
            _statement: str,
            _parameters: Any,
            context: Any,
            _executemany: bool,
        ) -> None:
            record_query()
            context._mavuno_started_at = perf_counter()

        @event.listens_for(self.engine.sync_engine, "after_cursor_execute")
        def after_cursor_execute(
            _connection: Any,
            _cursor: Any,
            statement: str,
            _parameters: Any,
            context: Any,
            _executemany: bool,
        ) -> None:
            started_at = getattr(context, "_mavuno_started_at", None)
            if started_at is None:
                return
            duration = perf_counter() - started_at
            if duration < self._slow_query_seconds:
                return
            if self._metrics is not None:
                self._metrics.increment("database_slow_queries_total")
            operation = (
                statement.lstrip().split(maxsplit=1)[0].upper() if statement.strip() else "UNKNOWN"
            )
            logger.warning(
                "Slow database query",
                extra={"duration_ms": round(duration * 1000, 3), "operation": operation},
            )
