from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from mavuno.api.dependencies import get_auth_service
from mavuno.auth.rate_limit import AuthRateLimiter, AuthRateLimitExceeded
from mavuno.auth.schemas import TokenResponse, UserResponse
from mavuno.core.config import Settings
from mavuno.main import create_app


class StubAuthService:
    def _response(self) -> TokenResponse:
        return TokenResponse(
            access_token="access",
            refresh_token="refresh",
            expires_in=900,
            user=UserResponse(
                id=uuid4(), email="person@example.com", phone_e164=None, roles=["buyer"]
            ),
        )

    async def register(self, _request: object) -> TokenResponse:
        return self._response()

    async def login(self, _identifier: str, _password: str) -> TokenResponse:
        return self._response()

    async def refresh(self, _token: str) -> TokenResponse:
        return self._response()


def test_limiter_is_deterministic_and_expires_windows() -> None:
    now = [100.0]
    settings = Settings(
        environment="test", auth_login_rate_limit=2, auth_rate_limit_window_seconds=10
    )
    limiter = AuthRateLimiter(settings, clock=lambda: now[0])

    limiter.check("login", "192.0.2.10", "person@example.com")
    limiter.check("login", "192.0.2.10", "person@example.com")
    with pytest.raises(AuthRateLimitExceeded) as exceeded:
        limiter.check("login", "192.0.2.10", "person@example.com")
    assert exceeded.value.retry_after == 10

    now[0] = 110.0
    limiter.check("login", "192.0.2.10", "person@example.com")
    assert limiter.entry_count == 2


def test_limiter_bounds_memory_and_stores_only_digest_keys() -> None:
    settings = Settings(environment="test", auth_rate_limit_max_entries=100)
    limiter = AuthRateLimiter(settings)

    for index in range(120):
        limiter.check("register", f"192.0.2.{index}", f"person-{index}@example.com")

    assert limiter.entry_count == 100
    assert all(isinstance(key, bytes) and len(key) == 32 for key in limiter._windows)
    assert "person-119@example.com" not in repr(limiter._windows)


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/api/v1/auth/register",
            {"email": "person@example.com", "password": "long-enough-password"},
        ),
        (
            "/api/v1/auth/login",
            {"identifier": "person@example.com", "password": "long-enough-password"},
        ),
        ("/api/v1/auth/refresh", {"refresh_token": "r" * 64}),
    ],
)
def test_auth_routes_return_stable_rate_limit_error(path: str, payload: dict[str, str]) -> None:
    settings = Settings(
        environment="test",
        auth_register_rate_limit=1,
        auth_login_rate_limit=1,
        auth_refresh_rate_limit=1,
    )
    app = create_app(settings)
    app.dependency_overrides[get_auth_service] = StubAuthService

    with TestClient(app) as client:
        first = client.post(path, json=payload)
        blocked = client.post(path, json=payload)

    assert first.status_code in {200, 201}
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "60"
    assert blocked.json()["error"]["code"] == "auth_rate_limit_exceeded"
