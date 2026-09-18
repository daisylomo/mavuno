from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mavuno import __version__
from mavuno.api.errors import register_exception_handlers
from mavuno.api.middleware import QueryBudgetMiddleware, RequestIdMiddleware
from mavuno.api.router import router
from mavuno.auth.rate_limit import DistributedAuthRateLimiter
from mavuno.core.config import Settings, get_settings
from mavuno.core.logging import configure_logging
from mavuno.core.performance import CatalogCache, PerformanceMetrics, RedisBackend
from mavuno.db import Database


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_config_path, settings.log_level)
    metrics = PerformanceMetrics()
    redis = RedisBackend(settings, metrics)
    catalog_cache = CatalogCache(redis, settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = (
            Database(settings, metrics=metrics) if settings.database_url is not None else None
        )
        app.state.database = database
        app.state.ready = True
        try:
            yield
        finally:
            app.state.ready = False
            if database is not None:
                await database.dispose()
            await redis.close()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.debug,
        lifespan=lifespan,
    )
    app.state.ready = False
    app.state.settings = settings
    app.state.metrics = metrics
    app.state.redis = redis
    app.state.catalog_cache = catalog_cache
    app.state.auth_rate_limiter = DistributedAuthRateLimiter(settings, redis, metrics)

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        QueryBudgetMiddleware, budget=settings.database_query_budget, metrics=metrics
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[str(origin) for origin in settings.cors_origins],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    register_exception_handlers(app)
    app.include_router(router)
    return app


app = create_app()
