from __future__ import annotations

import json
import logging
import time
from collections import Counter
from collections.abc import Callable, Mapping
from contextvars import ContextVar, Token
from typing import Any, Protocol, cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

from mavuno.core.config import Settings

logger = logging.getLogger(__name__)

_RATE_LIMIT_SCRIPT = """
local limit = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
local maximum = 0
local maximum_ttl = ttl
for _, key in ipairs(KEYS) do
  local value = redis.call('INCR', key)
  if value == 1 then redis.call('EXPIRE', key, ttl) end
  if value > maximum then
    maximum = value
    maximum_ttl = redis.call('TTL', key)
  end
end
return {maximum, maximum_ttl}
"""

_CACHE_LOOKUP_SCRIPT = """
local value = redis.call('GET', KEYS[1])
local generation = redis.call('GET', KEYS[2]) or '0'
return {value, generation}
"""

_CACHE_SET_SCRIPT = """
local generation = redis.call('GET', KEYS[2]) or '0'
if generation ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
return 1
"""

_CACHE_INVALIDATE_SCRIPT = """
redis.call('INCR', KEYS[2])
redis.call('EXPIRE', KEYS[2], ARGV[1])
return redis.call('DEL', KEYS[1])
"""


class RedisCommands(Protocol):
    async def get(self, key: str) -> bytes | str | None: ...

    async def set(self, key: str, value: str, *, ex: int) -> object: ...

    async def delete(self, *keys: str) -> int: ...

    async def eval(self, script: str, numkeys: int, *keys_and_args: str | int) -> Any: ...

    async def aclose(self) -> None: ...


class PerformanceMetrics:
    """Low-cardinality process metrics suitable for logs or a future metrics exporter."""

    def __init__(self) -> None:
        self._counters: Counter[str] = Counter()

    def increment(self, name: str, amount: int = 1) -> None:
        self._counters[name] += amount

    def snapshot(self) -> Mapping[str, int]:
        return dict(sorted(self._counters.items()))


class RedisBackend:
    """Small Redis boundary with a local circuit breaker and fail-open cache semantics."""

    def __init__(
        self,
        settings: Settings,
        metrics: PerformanceMetrics,
        *,
        client: RedisCommands | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.metrics = metrics
        self._clock = clock
        self._cooldown = settings.redis_failure_cooldown_seconds
        self._disabled_until = 0.0
        self._client: RedisCommands | None
        if client is not None:
            self._client = client
        elif settings.redis_url is not None:
            self._client = cast(
                RedisCommands,
                Redis.from_url(
                    settings.redis_url.get_secret_value(),
                    socket_connect_timeout=settings.redis_connect_timeout_seconds,
                    socket_timeout=settings.redis_operation_timeout_seconds,
                    decode_responses=False,
                ),
            )
        else:
            self._client = None

    @property
    def configured(self) -> bool:
        return self._client is not None

    async def get(self, key: str) -> bytes | str | None:
        if not self._available():
            return None
        try:
            assert self._client is not None
            return await self._client.get(key)
        except (RedisError, OSError, TimeoutError) as exc:
            self._failed("get", exc)
            return None

    async def set(self, key: str, value: str, ttl: int) -> bool:
        if not self._available():
            return False
        try:
            assert self._client is not None
            await self._client.set(key, value, ex=ttl)
            return True
        except (RedisError, OSError, TimeoutError) as exc:
            self._failed("set", exc)
            return False

    async def delete(self, *keys: str) -> bool:
        if not self._available():
            return False
        try:
            assert self._client is not None
            await self._client.delete(*keys)
            return True
        except (RedisError, OSError, TimeoutError) as exc:
            self._failed("delete", exc)
            return False

    async def rate_limit(self, keys: list[str], limit: int, window: int) -> tuple[int, int] | None:
        if not self._available():
            return None
        try:
            assert self._client is not None
            result = await self._client.eval(_RATE_LIMIT_SCRIPT, len(keys), *keys, limit, window)
            return int(result[0]), max(1, int(result[1]))
        except (RedisError, OSError, TimeoutError) as exc:
            self._failed("rate_limit", exc)
            return None

    async def cache_lookup(
        self, value_key: str, generation_key: str
    ) -> tuple[bytes | str | None, str] | None:
        if not self._available():
            return None
        try:
            assert self._client is not None
            result = await self._client.eval(_CACHE_LOOKUP_SCRIPT, 2, value_key, generation_key)
            raw_generation = result[1]
            generation = (
                raw_generation.decode()
                if isinstance(raw_generation, bytes)
                else str(raw_generation)
            )
            value = result[0]
            return (value if isinstance(value, (bytes, str)) else None), generation
        except (RedisError, OSError, TimeoutError) as exc:
            self._failed("cache_lookup", exc)
            return None

    async def cache_set_if_generation(
        self,
        value_key: str,
        generation_key: str,
        generation: str,
        value: str,
        ttl: int,
    ) -> bool:
        if not self._available():
            return False
        try:
            assert self._client is not None
            result = await self._client.eval(
                _CACHE_SET_SCRIPT,
                2,
                value_key,
                generation_key,
                generation,
                value,
                ttl,
            )
            return int(result) == 1
        except (RedisError, OSError, TimeoutError) as exc:
            self._failed("cache_set", exc)
            return False

    async def cache_invalidate(
        self, value_key: str, generation_key: str, generation_ttl: int
    ) -> bool:
        if not self._available():
            return False
        try:
            assert self._client is not None
            await self._client.eval(
                _CACHE_INVALIDATE_SCRIPT, 2, value_key, generation_key, generation_ttl
            )
            return True
        except (RedisError, OSError, TimeoutError) as exc:
            self._failed("cache_invalidate", exc)
            return False

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    def _available(self) -> bool:
        return self._client is not None and self._clock() >= self._disabled_until

    def _failed(self, operation: str, exc: Exception) -> None:
        self.metrics.increment("redis_errors_total")
        self.metrics.increment(f"redis_{operation}_errors_total")
        self._disabled_until = self._clock() + self._cooldown
        logger.warning(
            "Redis operation failed; using safe fallback",
            extra={"operation": operation, "error_type": type(exc).__name__},
        )


class CatalogCache:
    KEY_PREFIX = "mavuno:v1:catalog:listing:"
    GENERATION_PREFIX = "mavuno:v1:catalog:listing-generation:"

    def __init__(self, backend: RedisBackend, settings: Settings) -> None:
        self.backend = backend
        self.metrics = backend.metrics
        self.ttl = settings.catalog_listing_cache_ttl_seconds
        self.generation_ttl = max(60, self.ttl * 4)

    async def get_listing(self, listing_id: str) -> tuple[dict[str, Any] | None, str | None]:
        lookup = await self.backend.cache_lookup(
            self._key(listing_id), self._generation_key(listing_id)
        )
        if lookup is None:
            self.metrics.increment("catalog_cache_misses_total")
            return None, None
        raw, generation = lookup
        if raw is None:
            self.metrics.increment("catalog_cache_misses_total")
            return None, generation
        try:
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError("cached listing is not an object")
        except (TypeError, ValueError, UnicodeDecodeError):
            self.metrics.increment("catalog_cache_decode_errors_total")
            await self.backend.delete(self._key(listing_id))
            return None, generation
        self.metrics.increment("catalog_cache_hits_total")
        return value, generation

    async def set_listing(
        self, listing_id: str, value: Mapping[str, Any], generation: str | None
    ) -> None:
        if generation is None:
            return
        encoded = json.dumps(value, separators=(",", ":"), sort_keys=True)
        if await self.backend.cache_set_if_generation(
            self._key(listing_id),
            self._generation_key(listing_id),
            generation,
            encoded,
            self.ttl,
        ):
            self.metrics.increment("catalog_cache_writes_total")
        else:
            self.metrics.increment("catalog_cache_stale_fills_prevented_total")

    async def invalidate_listing(self, listing_id: str) -> None:
        if await self.backend.cache_invalidate(
            self._key(listing_id), self._generation_key(listing_id), self.generation_ttl
        ):
            self.metrics.increment("catalog_cache_invalidations_total")

    @classmethod
    def _key(cls, listing_id: str) -> str:
        return f"{cls.KEY_PREFIX}{listing_id}"

    @classmethod
    def _generation_key(cls, listing_id: str) -> str:
        return f"{cls.GENERATION_PREFIX}{listing_id}"


query_count: ContextVar[int] = ContextVar("database_query_count", default=0)


def begin_query_budget() -> Token[int]:
    return query_count.set(0)


def record_query() -> None:
    query_count.set(query_count.get() + 1)


def end_query_budget(token: Token[int]) -> None:
    query_count.reset(token)
