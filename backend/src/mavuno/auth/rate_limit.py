from __future__ import annotations

import hashlib
import hmac
import math
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from mavuno.core.config import Settings


@dataclass(slots=True)
class _Window:
    started_at: float
    count: int


class AuthRateLimitExceeded(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Authentication rate limit exceeded")
        self.retry_after = retry_after


class AuthRateLimiter:
    """Bounded per-process fixed-window limiter for authentication endpoints."""

    def __init__(
        self,
        settings: Settings,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._window_seconds = settings.auth_rate_limit_window_seconds
        self._limits = {
            "register": settings.auth_register_rate_limit,
            "login": settings.auth_login_rate_limit,
            "refresh": settings.auth_refresh_rate_limit,
        }
        self._max_entries = settings.auth_rate_limit_max_entries
        self._clock = clock
        self._digest_key = (
            settings.auth_signing_keys[settings.auth_active_key_id]
            .get_secret_value()
            .encode("utf-8")
        )
        self._windows: OrderedDict[bytes, _Window] = OrderedDict()

    def check(self, scope: str, client_address: str, subject: str) -> None:
        now = self._clock()
        self._prune(now)
        limit = self._limits[scope]
        self._consume(self._key(scope, "client", client_address), limit, now)
        self._consume(self._key(scope, "subject", subject), limit, now)

    @property
    def entry_count(self) -> int:
        return len(self._windows)

    def _consume(self, key: bytes, limit: int, now: float) -> None:
        window = self._windows.get(key)
        if window is None or now - window.started_at >= self._window_seconds:
            self._windows.pop(key, None)
            self._windows[key] = _Window(started_at=now, count=1)
            while len(self._windows) > self._max_entries:
                self._windows.popitem(last=False)
            return
        if window.count >= limit:
            retry_after = max(1, math.ceil(self._window_seconds - (now - window.started_at)))
            raise AuthRateLimitExceeded(retry_after)
        window.count += 1

    def _prune(self, now: float) -> None:
        while self._windows:
            key, window = next(iter(self._windows.items()))
            if now - window.started_at < self._window_seconds:
                return
            del self._windows[key]

    def _key(self, *parts: str) -> bytes:
        message = b"".join(
            len(part.encode("utf-8")).to_bytes(4, "big") + part.encode("utf-8") for part in parts
        )
        return hmac.new(self._digest_key, message, hashlib.sha256).digest()
