from typing import cast
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_liveness(client: TestClient) -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    assert response.headers["X-Request-ID"]


def test_readiness_after_startup(client: TestClient) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_reports_unavailable(client: TestClient) -> None:
    app = cast(FastAPI, client.app)
    app.state.ready = False

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


def test_readiness_reports_database_failure(client: TestClient) -> None:
    app = cast(FastAPI, client.app)
    app.state.database = AsyncMock()
    app.state.database.is_ready.return_value = False

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    app.state.database.is_ready.assert_awaited_once()
