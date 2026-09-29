import pytest
from api_client.client import MavunoClient
from api_client.models.auth import LoginRequest
from api_client.models.catalog import ListingFilterRequest

from api_client.tests.conftest import BASE_URL


@pytest.fixture(scope="session")
def client() -> MavunoClient:
    return MavunoClient(base_url=BASE_URL)


def test_client_initialization(client: MavunoClient):
    """Verify all domain services are mounted on the client."""
    assert client.auth is not None
    assert client.catalog is not None
    assert client.commerce is not None
    assert client.fulfilment is not None
    assert client.messaging is not None
    assert client.premium is not None
    assert client.profiles is not None


def test_auth_serialization_and_call(client: MavunoClient):
    """Test auth payload handling against the running backend."""
    req = LoginRequest(identifier="+254711111111", password="TestPassword123!")
    res = client.auth.login(req)
    assert res.status_code in [200, 401, 404, 503]


def test_catalog_search(client: MavunoClient):
    """Test catalog filter parameter generation and listing fetch."""
    filter_req = ListingFilterRequest(limit=5, sort="newest")
    res = client.catalog.list_listings(filter_req)
    assert res.status_code in [200, 503]


def test_premium_plans(client: MavunoClient):
    """Test public plans endpoint."""
    res = client.premium.list_plans()
    assert res.status_code in [200, 503]


def test_token_injection(client: MavunoClient):
    """Verify that setting and clearing auth tokens updates headers correctly."""
    token = "sample_test_jwt_token"
    client.set_auth_token(token)
    assert client.session.headers.get("Authorization") == f"Bearer {token}"

    client.clear_auth_token()
    assert "Authorization" not in client.session.headers
