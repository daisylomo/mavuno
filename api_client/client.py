import os
import requests
from api_client.services.auth import AuthService
from api_client.services.catalog import CatalogService
from api_client.services.commerce import CommerceService
from api_client.services.fulfilment import FulfilmentService
from api_client.services.messaging import MessagingService
from api_client.services.premium import PremiumService
from api_client.services.profiles import ProfilesService


class MavunoClient:
    def __init__(self, base_url: str | None = None):
        raw_url = (
            base_url
            or os.getenv("MAVUNO_API_BASE_URL")
            or "http://127.0.0.1:8000/api/v1"
        ).rstrip("/")

        if not raw_url.endswith("/api/v1"):
            raw_url = f"{raw_url}/api/v1"


        self.base_url = raw_url

        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

        # Register services
        self.auth = AuthService(self.base_url, self.session)
        self.catalog = CatalogService(self.base_url, self.session)
        self.commerce = CommerceService(self.base_url, self.session)
        self.fulfilment = FulfilmentService(self.base_url, self.session)
        self.messaging = MessagingService(self.base_url, self.session)
        self.premium = PremiumService(self.base_url,self.session)
        self.profiles =ProfilesService(self.base_url,self.session)

    def set_auth_token(self, token: str) -> None:
        """Injects JWT bearer token into session headers for all calls."""
        self.session.headers["Authorization"] = f"Bearer {token}"

    def clear_auth_token(self) -> None:
        self.session.headers.pop("Authorization", None)