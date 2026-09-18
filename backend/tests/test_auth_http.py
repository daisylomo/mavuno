from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from mavuno.api.dependencies import get_current_user, get_database, get_token_manager, require_roles
from mavuno.api.errors import ApiError
from mavuno.auth.context import AuthenticatedUser
from mavuno.core.config import Settings
from mavuno.main import create_app


def test_protected_endpoint_requires_bearer_token() -> None:
    app = create_app(Settings(environment="test"))
    with TestClient(app) as client:
        response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "invalid_access_token"


def test_me_uses_shared_current_user_contract() -> None:
    app = create_app(Settings(environment="test"))
    expected = AuthenticatedUser(
        id=uuid4(),
        email="buyer@example.com",
        phone_e164=None,
        roles=frozenset({"buyer"}),
        token_version=2,
    )
    app.dependency_overrides[get_current_user] = lambda: expected
    with TestClient(app) as client:
        response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json() == {
        "id": str(expected.id),
        "email": "buyer@example.com",
        "phone_e164": None,
        "roles": ["buyer"],
    }


def test_request_dependencies_use_application_state() -> None:
    app = create_app(Settings(environment="test"))
    request = Request({"type": "http", "app": app, "headers": []})
    with pytest.raises(ApiError, match="temporarily unavailable"):
        get_database(request)

    sentinel = object()
    app.state.database = sentinel

    assert get_database(request) is sentinel
    assert get_token_manager(request).access_ttl.total_seconds() == 900


@pytest.mark.anyio
async def test_role_dependency_allows_and_denies() -> None:
    admin_dependency = require_roles("administrator")
    user = AuthenticatedUser(uuid4(), None, None, frozenset({"buyer"}), 0)

    with pytest.raises(ApiError, match="permission") as denied:
        await admin_dependency(user)
    assert denied.value.code == "insufficient_permissions"

    administrator = AuthenticatedUser(user.id, None, None, frozenset({"administrator"}), 0)
    assert await admin_dependency(administrator) == administrator
