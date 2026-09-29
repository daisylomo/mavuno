from fastapi.testclient import TestClient
from pydantic import AnyHttpUrl

from mavuno.core.config import Settings
from mavuno.main import create_app


def test_configured_browser_origin_is_allowed() -> None:
    app = create_app(
        Settings(environment="test", cors_origins=[AnyHttpUrl("http://localhost:8081")])
    )
    with TestClient(app) as client:
        response = client.get("/health/live", headers={"Origin": "http://localhost:8081"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:8081"
