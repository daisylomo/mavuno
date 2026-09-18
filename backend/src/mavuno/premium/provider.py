from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Protocol, cast

import httpx2 as httpx

from mavuno.core.config import Settings

SubscriptionOutcome = Literal["pending", "active", "past_due", "cancelled", "expired"]


class PremiumProviderError(RuntimeError):
    """Safe provider error without credentials or raw customer payloads."""


@dataclass(frozen=True, slots=True)
class SubscriptionInitiation:
    account_reference: str
    user_reference: str
    plan_code: str
    amount: Decimal
    currency: str
    interval: str


@dataclass(frozen=True, slots=True)
class SubscriptionStatus:
    provider_subscription_ref: str
    account_reference: str
    plan_code: str
    amount: Decimal
    currency: str
    outcome: SubscriptionOutcome
    period_start: datetime | None
    period_end: datetime | None


@dataclass(frozen=True, slots=True)
class SubscriptionCallback:
    provider_event_ref: str
    provider_subscription_ref: str
    account_reference: str
    event_type: str
    redacted_payload: dict[str, object]


class PremiumProvider(Protocol):
    name: str

    async def initiate(self, request: SubscriptionInitiation) -> str: ...

    async def query_status(self, provider_subscription_ref: str) -> SubscriptionStatus: ...

    def parse_callback(
        self, raw_body: bytes, payload: dict[str, object], signature: str
    ) -> SubscriptionCallback: ...


class HttpPremiumProvider:
    name = "premium_http"

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        if (
            settings.premium_provider_base_url is None
            or settings.premium_provider_api_key is None
            or settings.premium_webhook_secret is None
        ):
            raise PremiumProviderError("Premium provider is not configured")
        self.settings = settings
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(
            base_url=str(settings.premium_provider_base_url).rstrip("/"),
            timeout=settings.premium_provider_timeout_seconds,
        )

    async def initiate(self, request: SubscriptionInitiation) -> str:
        data = await self._request(
            "POST",
            "/subscriptions",
            {
                "account_reference": request.account_reference,
                "user_reference": request.user_reference,
                "plan_code": request.plan_code,
                "amount": str(request.amount),
                "currency": request.currency,
                "interval": request.interval,
            },
        )
        reference = str(data.get("subscription_reference", ""))
        if not reference:
            raise PremiumProviderError("Premium provider returned no subscription reference")
        return reference

    async def query_status(self, provider_subscription_ref: str) -> SubscriptionStatus:
        data = await self._request("GET", f"/subscriptions/{provider_subscription_ref}", None)
        outcome = str(data.get("status", "pending"))
        if outcome not in {"pending", "active", "past_due", "cancelled", "expired"}:
            raise PremiumProviderError("Premium provider returned an unknown status")
        try:
            amount = Decimal(str(data["amount"]))
            currency = str(data["currency"])
            account_reference = str(data["account_reference"])
            plan_code = str(data["plan_code"])
        except (KeyError, ValueError) as exc:
            raise PremiumProviderError("Premium provider status is incomplete") from exc
        return SubscriptionStatus(
            provider_subscription_ref=provider_subscription_ref,
            account_reference=account_reference,
            plan_code=plan_code,
            amount=amount,
            currency=currency,
            outcome=cast(SubscriptionOutcome, outcome),
            period_start=self._datetime(data.get("period_start")),
            period_end=self._datetime(data.get("period_end")),
        )

    def parse_callback(
        self, raw_body: bytes, payload: dict[str, object], signature: str
    ) -> SubscriptionCallback:
        secret = self.settings.premium_webhook_secret
        assert secret is not None
        expected = hmac.new(
            secret.get_secret_value().encode(), raw_body, hashlib.sha256
        ).hexdigest()
        supplied = signature.removeprefix("sha256=")
        if not hmac.compare_digest(expected, supplied):
            raise PremiumProviderError("Premium callback signature is invalid")
        try:
            event_ref = str(payload["event_reference"])
            subscription_ref = str(payload["subscription_reference"])
            account_reference = str(payload["account_reference"])
            event_type = str(payload["event_type"])
        except KeyError as exc:
            raise PremiumProviderError("Premium callback is malformed") from exc
        return SubscriptionCallback(
            provider_event_ref=event_ref,
            provider_subscription_ref=subscription_ref,
            account_reference=account_reference,
            event_type=event_type,
            redacted_payload={
                "event_reference": event_ref,
                "subscription_reference": subscription_ref,
                "account_reference": account_reference,
                "event_type": event_type,
            },
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def _request(
        self, method: str, path: str, payload: dict[str, object] | None
    ) -> dict[str, Any]:
        key = self.settings.premium_provider_api_key
        assert key is not None
        try:
            response = await self.client.request(
                method,
                path,
                json=payload,
                headers={"Authorization": f"Bearer {key.get_secret_value()}"},
            )
            response.raise_for_status()
            return cast(dict[str, Any], response.json())
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            raise PremiumProviderError("Premium provider request failed") from exc

    @staticmethod
    def _datetime(value: object) -> datetime | None:
        if value is None or value == "":
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError as exc:
            raise PremiumProviderError("Premium provider returned an invalid date") from exc
