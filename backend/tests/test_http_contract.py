from typing import cast
from uuid import UUID

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from mavuno.core.config import API_V1_PREFIX, Settings
from mavuno.main import create_app


class QueryInput(BaseModel):
    count: int


def test_request_id_is_preserved(client: TestClient) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "mobile-request-42"})

    assert response.headers["X-Request-ID"] == "mobile-request-42"


def test_invalid_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "invalid request id"})

    UUID(response.headers["X-Request-ID"])


def test_error_envelope_contains_request_id(client: TestClient) -> None:
    response = client.get("/does-not-exist", headers={"X-Request-ID": "not-found-1"})

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "http_404",
            "message": "Not Found",
            "request_id": "not-found-1",
        }
    }


def test_validation_error_uses_error_envelope(client: TestClient) -> None:
    router = APIRouter()

    @router.post("/validation-probe")
    async def validation_probe(payload: QueryInput) -> QueryInput:
        return payload

    app = cast(FastAPI, client.app)
    app.include_router(router, prefix=API_V1_PREFIX)
    response = client.post(
        f"{API_V1_PREFIX}/validation-probe",
        json={"count": "not-an-integer"},
        headers={"X-Request-ID": "validation-1"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["request_id"] == "validation-1"
    assert body["error"]["details"]


def test_unhandled_error_is_redacted() -> None:
    app = create_app(Settings(environment="test"))

    @app.get("/error-probe")
    async def error_probe() -> None:
        raise RuntimeError("sensitive internal detail")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/error-probe", headers={"X-Request-ID": "error-1"})

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "An unexpected error occurred",
            "request_id": "error-1",
        }
    }
    assert "sensitive internal detail" not in response.text
