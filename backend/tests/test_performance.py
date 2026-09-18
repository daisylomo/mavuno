from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import text

from mavuno.auth.rate_limit import (
    AuthRateLimiter,
    AuthRateLimitExceeded,
    DistributedAuthRateLimiter,
)
from mavuno.core.config import Settings
from mavuno.core.performance import CatalogCache, PerformanceMetrics, RedisBackend, record_query
from mavuno.db import Database
from mavuno.main import create_app


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.counts: dict[str, int] = {}
        self.ttls: dict[str, int] = {}
        self.generations: dict[str, int] = {}
        self.closed = False

    async def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ex: int) -> object:
        assert ex > 0
        self.values[key] = value.encode()
        return True

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            deleted += int(self.values.pop(key, None) is not None)
        return deleted

    async def eval(self, script: str, numkeys: int, *keys_and_args: str | int) -> object:
        keys = [str(key) for key in keys_and_args[:numkeys]]
        if "local maximum" in script:
            for key in keys:
                self.counts[key] = self.counts.get(key, 0) + 1
                self.ttls.setdefault(key, int(keys_and_args[-1]))
            maximum_key = max(keys, key=lambda key: self.counts[key])
            return [self.counts[maximum_key], self.ttls[maximum_key]]
        if "local value" in script:
            return [self.values.get(keys[0]), str(self.generations.get(keys[1], 0)).encode()]
        if "generation ~= ARGV" in script:
            generation = str(keys_and_args[numkeys])
            if generation != str(self.generations.get(keys[1], 0)):
                return 0
            self.values[keys[0]] = str(keys_and_args[numkeys + 1]).encode()
            return 1
        self.generations[keys[1]] = self.generations.get(keys[1], 0) + 1
        self.values.pop(keys[0], None)
        return 1

    async def aclose(self) -> None:
        self.closed = True


class BrokenRedis(FakeRedis):
    async def eval(self, script: str, numkeys: int, *keys_and_args: str | int) -> object:
        raise RedisConnectionError(script)


@pytest.mark.anyio
async def test_catalog_cache_round_trip_and_invalidation() -> None:
    metrics = PerformanceMetrics()
    client = FakeRedis()
    backend = RedisBackend(Settings(environment="test"), metrics, client=client)
    cache = CatalogCache(backend, Settings(environment="test"))
    listing_id = str(uuid4())

    value, generation = await cache.get_listing(listing_id)
    assert value is None and generation == "0"
    await cache.set_listing(listing_id, {"version": 1, "available_quantity": "8.000"}, generation)
    assert (await cache.get_listing(listing_id))[0] == {
        "version": 1,
        "available_quantity": "8.000",
    }
    await cache.invalidate_listing(listing_id)
    assert (await cache.get_listing(listing_id))[0] is None

    snapshot = metrics.snapshot()
    assert snapshot["catalog_cache_hits_total"] == 1
    assert snapshot["catalog_cache_misses_total"] == 2
    assert snapshot["catalog_cache_invalidations_total"] == 1


@pytest.mark.anyio
async def test_bad_cache_entry_is_deleted_and_redis_outage_bypasses_reads() -> None:
    settings = Settings(environment="test", redis_failure_cooldown_seconds=5)
    metrics = PerformanceMetrics()
    client = FakeRedis()
    backend = RedisBackend(settings, metrics, client=client)
    cache = CatalogCache(backend, settings)
    key = cache._key("bad")
    client.values[key] = b"[]"

    assert (await cache.get_listing("bad"))[0] is None
    assert key not in client.values

    now = [10.0]
    broken = RedisBackend(settings, metrics, client=BrokenRedis(), clock=lambda: now[0])
    assert await broken.cache_lookup("key", "generation") is None
    assert await broken.cache_lookup("key", "generation") is None
    assert metrics.snapshot()["redis_errors_total"] == 1


@pytest.mark.anyio
async def test_distributed_rate_limit_is_atomic_and_falls_back_locally() -> None:
    settings = Settings(environment="test", auth_login_rate_limit=1)
    metrics = PerformanceMetrics()
    redis = RedisBackend(settings, metrics, client=FakeRedis())
    limiter = DistributedAuthRateLimiter(settings, redis, metrics)

    await limiter.check("login", "192.0.2.1", "person@example.test")
    with pytest.raises(AuthRateLimitExceeded) as blocked:
        await limiter.check("login", "192.0.2.1", "person@example.test")
    assert blocked.value.retry_after == 60

    fallback = AuthRateLimiter(settings)
    no_redis = RedisBackend(settings, metrics)
    local = DistributedAuthRateLimiter(settings, no_redis, metrics, fallback=fallback)
    await local.check("login", "192.0.2.2", "other@example.test")
    with pytest.raises(AuthRateLimitExceeded):
        await local.check("login", "192.0.2.2", "other@example.test")
    assert metrics.snapshot()["auth_rate_limit_local_fallback_total"] == 2


@pytest.mark.anyio
async def test_rate_limit_retry_after_comes_from_maximum_counter() -> None:
    settings = Settings(environment="test")
    client = FakeRedis()
    client.counts.update({"older-subject": 4, "new-client": 0})
    client.ttls.update({"older-subject": 7, "new-client": 50})
    backend = RedisBackend(settings, PerformanceMetrics(), client=client)

    assert await backend.rate_limit(["new-client", "older-subject"], 10, 60) == (5, 7)


@pytest.mark.anyio
async def test_backend_operations_and_close() -> None:
    settings = Settings(environment="test")
    client = FakeRedis()
    backend = RedisBackend(settings, PerformanceMetrics(), client=client)

    assert backend.configured
    assert await backend.set("k", "v", 2)
    assert await backend.get("k") == b"v"
    assert await backend.rate_limit(["a", "b"], 2, 30) == (1, 30)
    assert await backend.delete("k")
    await backend.close()
    assert client.closed


@pytest.mark.anyio
async def test_generation_guard_prevents_stale_stock_refill() -> None:
    settings = Settings(environment="test")
    cache = CatalogCache(RedisBackend(settings, PerformanceMetrics(), client=FakeRedis()), settings)
    listing_id = str(uuid4())
    _, old_generation = await cache.get_listing(listing_id)

    await cache.invalidate_listing(listing_id)
    await cache.set_listing(listing_id, {"available_quantity": "10.000"}, old_generation)

    value, new_generation = await cache.get_listing(listing_id)
    assert value is None
    assert new_generation == "1"
    assert cache.metrics.snapshot()["catalog_cache_stale_fills_prevented_total"] == 1


def test_query_budget_header_and_metrics_endpoint() -> None:
    app = create_app(Settings(environment="test", database_query_budget=1))

    @app.get("/query-budget-probe")
    async def query_budget_probe() -> dict[str, bool]:
        record_query()
        record_query()
        return {"ok": True}

    with TestClient(app) as client:
        live = client.get("/health/live")
        budget = client.get("/query-budget-probe")
        metrics = client.get("/health/metrics")

    assert live.headers["X-DB-Query-Count"] == "0"
    assert budget.headers["X-DB-Query-Count"] == "2"
    assert metrics.status_code == 200
    assert metrics.json()["database_query_budget_exceeded_total"] == 1
    assert metrics.json()["http_requests_total"] == 2
    assert metrics.json()["http_responses_2xx_total"] == 2
    assert metrics.json()["http_request_duration_le_inf_total"] == 2


@pytest.mark.anyio
async def test_checkout_cache_hook_invalidates_each_changed_listing() -> None:
    from mavuno.commerce.repository import CommerceRepository
    from mavuno.commerce.service import CheckoutService

    cache = SimpleNamespace(invalidate_listing=AsyncMock())
    service = CheckoutService(
        cast(CommerceRepository, object()),
        Settings(environment="test"),
        cache,  # type: ignore[arg-type]
    )
    first, second = uuid4(), uuid4()

    await service._invalidate_listings([first, second])

    assert cache.invalidate_listing.await_count == 2


@pytest.mark.integration
@pytest.mark.anyio
async def test_real_redis_cache_and_atomic_limit() -> None:
    url = os.getenv("MAVUNO_TEST_REDIS_URL")
    if url is None:
        pytest.skip("MAVUNO_TEST_REDIS_URL is not configured")
    settings = Settings(environment="test", redis_url=SecretStr(url))
    backend = RedisBackend(settings, PerformanceMetrics())
    cache = CatalogCache(backend, settings)
    unique = str(uuid4())
    try:
        assert await backend.set(f"feature09:{unique}:value", "ok", 5)
        assert await backend.get(f"feature09:{unique}:value") == b"ok"
        result = await backend.rate_limit(
            [f"feature09:{unique}:client", f"feature09:{unique}:subject"], 2, 5
        )
        assert result == (1, 5)
        older = f"feature09:{unique}:older"
        newer = f"feature09:{unique}:newer"
        assert await backend.rate_limit([older], 3, 5) == (1, 5)
        await asyncio.sleep(1.1)
        mismatched = await backend.rate_limit([newer, older], 3, 5)
        assert mismatched is not None
        assert mismatched[0] == 2
        assert 1 <= mismatched[1] <= 4
        _, generation = await cache.get_listing(unique)
        await cache.invalidate_listing(unique)
        await cache.set_listing(unique, {"available_quantity": "10.000"}, generation)
        assert (await cache.get_listing(unique))[0] is None
    finally:
        await backend.delete(
            f"feature09:{unique}:value",
            f"feature09:{unique}:client",
            f"feature09:{unique}:subject",
            f"feature09:{unique}:older",
            f"feature09:{unique}:newer",
            f"mavuno:v1:catalog:listing:{unique}",
            f"mavuno:v1:catalog:listing-generation:{unique}",
        )
        await backend.close()


@pytest.mark.integration
@pytest.mark.anyio
async def test_slow_query_observation_records_metric() -> None:
    url = os.getenv("MAVUNO_TEST_DATABASE_URL")
    if url is None:
        pytest.skip("MAVUNO_TEST_DATABASE_URL is not configured")
    metrics = PerformanceMetrics()
    database = Database(
        Settings(
            environment="test",
            database_url=SecretStr(url),
            database_slow_query_ms=10,
        ),
        metrics=metrics,
    )
    try:
        async with database.session() as session:
            await session.execute(text("SELECT SLEEP(0.02)"))
        assert metrics.snapshot()["database_slow_queries_total"] == 1
    finally:
        await database.dispose()
