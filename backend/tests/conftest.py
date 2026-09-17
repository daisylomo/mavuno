from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from mavuno.core.config import Settings
from mavuno.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app(Settings(environment="test"))
    with TestClient(app) as test_client:
        yield test_client
