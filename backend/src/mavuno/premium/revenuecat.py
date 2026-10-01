from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, cast
from urllib.parse import quote

import httpx2 as httpx

from mavuno.core.config import Settings

REVENUECAT_PROVIDER = "revenuecat"
# Store purchases are recorded against these seeded plans so entitlement checks stay uniform.
STORE_PLAN_CODES = {"buyer": "revenuecat_buyer", "farmer": "revenuecat_farmer"}
# A lifetime store purchase has no expiry; MySQL DATETIME tops out at the end of year 9999.
LIFETIME_PERIOD_END = datetime(9999, 12, 31)


class RevenueCatError(RuntimeError):
    """Safe RevenueCat error without credentials or raw customer payloads."""


@dataclass(frozen=True, slots=True)
class StoreEntitlement:
    product_identifier: str
    purchased_at: datetime | None
    # None means a non-expiring (lifetime) purchase.
    expires_at: datetime | None

    def active(self, now: datetime) -> bool:
        return self.expires_at is None or self.expires_at > now


class StoreClient(Protocol):
    async def entitlement(self, app_user_id: str) -> StoreEntitlement | None: ...


class RevenueCatClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        if settings.revenuecat_secret_api_key is None:
            raise RevenueCatError("RevenueCat is not configured")
        self.settings = settings
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(
            base_url=settings.revenuecat_api_base_url.rstrip("/"),
            timeout=settings.revenuecat_timeout_seconds,
        )

    async def entitlement(self, app_user_id: str) -> StoreEntitlement | None:
        """Return the Mavuno entitlement RevenueCat holds for the user, active or lapsed."""
        key = self.settings.revenuecat_secret_api_key
        assert key is not None
        try:
            response = await self.client.get(
                f"/v1/subscribers/{quote(app_user_id, safe='')}",
                headers={"Authorization": f"Bearer {key.get_secret_value()}"},
            )
            response.raise_for_status()
            data = cast(dict[str, Any], response.json())
            entitlements = cast(dict[str, Any], data["subscriber"].get("entitlements") or {})
        except (httpx.HTTPError, ValueError, KeyError, AttributeError, TypeError) as exc:
            raise RevenueCatError("RevenueCat request failed") from exc
        value = entitlements.get(self.settings.revenuecat_entitlement_id)
        if not isinstance(value, dict):
            return None
        expires_at = self._datetime(value.get("expires_date"))
        grace_until = self._datetime(value.get("grace_period_expires_date"))
        if expires_at is not None and grace_until is not None:
            # RevenueCat keeps access during a billing grace period; so does Mavuno.
            expires_at = max(expires_at, grace_until)
        return StoreEntitlement(
            product_identifier=str(value.get("product_identifier", "")),
            purchased_at=self._datetime(value.get("purchase_date")),
            expires_at=expires_at,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    @staticmethod
    def _datetime(value: object) -> datetime | None:
        if value is None or value == "":
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError as exc:
            raise RevenueCatError("RevenueCat returned an invalid date") from exc
