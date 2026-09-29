from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, create_autospec
from uuid import uuid4

import httpx2 as httpx
import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy.exc import IntegrityError

from mavuno.api.errors import ApiError
from mavuno.auth.context import AuthenticatedUser
from mavuno.core.config import Settings
from mavuno.db.models import Plan, Prebooking, Subscription
from mavuno.premium.provider import (
    HttpPremiumProvider,
    PremiumProviderError,
    SubscriptionCallback,
    SubscriptionInitiation,
    SubscriptionStatus,
)
from mavuno.premium.repository import PremiumRepository
from mavuno.premium.schemas import PlanCreate, PrebookingCreate, PrebookingTransition
from mavuno.premium.service import InsightsService, PrebookingService, SubscriptionService, _now


def settings() -> Settings:
    return Settings(
        environment="test",
        premium_enabled=True,
        premium_provider_base_url="https://billing.example.test",
        premium_provider_api_key=SecretStr("provider-api-key"),
        premium_webhook_secret=SecretStr("w" * 32),
        premium_callback_token=SecretStr("t" * 32),
    )


def user(role: str = "buyer") -> AuthenticatedUser:
    return AuthenticatedUser(uuid4(), "member@example.test", None, frozenset({role}), 0)


def plan(audience: str = "buyer") -> Plan:
    value = Plan(
        id=uuid4(),
        code=f"{audience}-pro",
        name="Pro",
        audience=audience,
        price_amount=Decimal("500"),
        currency="KES",
        billing_interval="month",
        features=["prebooking", "insights"],
        active=True,
    )
    value.created_at = value.updated_at = _now()
    return value


class FakeProvider:
    name = "premium_http"

    def __init__(self, status: SubscriptionStatus | None = None) -> None:
        self.status = status

    async def initiate(self, request: SubscriptionInitiation) -> str:
        assert request.currency == "KES"
        return "provider-subscription-1"

    async def query_status(self, provider_subscription_ref: str) -> SubscriptionStatus:
        assert self.status is not None
        return self.status

    def parse_callback(
        self, raw_body: bytes, payload: dict[str, object], signature: str
    ) -> SubscriptionCallback:
        return SubscriptionCallback(
            "event-1",
            "provider-subscription-1",
            "MVSREFERENCE",
            "subscription.updated",
            {"event_reference": "event-1"},
        )


@pytest.fixture
def repository() -> Any:
    value = create_autospec(PremiumRepository, instance=True)
    value.add = MagicMock()
    value.commit = AsyncMock()
    value.rollback = AsyncMock()
    value.refresh = AsyncMock()
    return value


@pytest.mark.anyio
async def test_http_premium_provider_contract_and_signed_callback() -> None:
    with pytest.raises(PremiumProviderError, match="not configured"):
        HttpPremiumProvider(Settings(environment="test"))

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"subscription_reference": "provider-subscription-1"})
        return httpx.Response(
            200,
            json={
                "status": "active",
                "amount": "500",
                "currency": "KES",
                "account_reference": "MVSREFERENCE",
                "plan_code": "buyer-pro",
                "period_start": "2026-09-01T00:00:00Z",
                "period_end": "2026-10-01T00:00:00Z",
            },
        )

    client = httpx.AsyncClient(
        base_url="https://billing.example.test", transport=httpx.MockTransport(handler)
    )
    provider = HttpPremiumProvider(settings(), client)
    reference = await provider.initiate(
        SubscriptionInitiation(
            "MVSREFERENCE", str(uuid4()), "buyer-pro", Decimal("500"), "KES", "month"
        )
    )
    assert reference == "provider-subscription-1"
    status = await provider.query_status(reference)
    assert status.outcome == "active" and status.period_end is not None
    raw = json.dumps(
        {
            "event_reference": "event-1",
            "subscription_reference": reference,
            "account_reference": "MVSREFERENCE",
            "event_type": "subscription.updated",
        },
        separators=(",", ":"),
    ).encode()
    signature = hmac.new(b"w" * 32, raw, hashlib.sha256).hexdigest()
    event = provider.parse_callback(raw, json.loads(raw), f"sha256={signature}")
    assert event.provider_event_ref == "event-1"
    with pytest.raises(PremiumProviderError):
        provider.parse_callback(raw, json.loads(raw), "bad")
    malformed = b"{}"
    malformed_signature = hmac.new(b"w" * 32, malformed, hashlib.sha256).hexdigest()
    with pytest.raises(PremiumProviderError, match="malformed"):
        provider.parse_callback(malformed, {}, malformed_signature)
    assert all("provider-api-key" not in str(request.content) for request in requests)
    await client.aclose()


@pytest.mark.anyio
async def test_subscription_initiation_is_idempotent_and_fail_closed(repository: Any) -> None:
    member, selected = user(), plan()
    repository.subscription_by_idempotency = AsyncMock(return_value=None)
    repository.plan = AsyncMock(return_value=selected)

    async def stamp(value: Subscription) -> None:
        value.created_at = value.updated_at = _now()

    repository.refresh = AsyncMock(side_effect=stamp)
    service = SubscriptionService(cast(PremiumRepository, repository), settings(), FakeProvider())
    subscription = await service.initiate(member, selected.id, "subscription-key")
    assert subscription.status == "pending"
    assert subscription.provider_subscription_ref == "provider-subscription-1"
    assert repository.add.call_count == 2

    repository.subscription_by_idempotency = AsyncMock(return_value=subscription)
    assert await service.initiate(member, selected.id, "subscription-key") is subscription

    disabled = SubscriptionService(
        cast(PremiumRepository, repository), Settings(environment="test"), FakeProvider()
    )
    with pytest.raises(ApiError) as unavailable:
        await disabled.initiate(member, selected.id, "other-key")
    assert unavailable.value.code == "premium_provider_unavailable"


@pytest.mark.anyio
async def test_plan_and_subscription_validation_paths(repository: Any) -> None:
    service = SubscriptionService(cast(PremiumRepository, repository), settings(), FakeProvider())
    payload = PlanCreate(
        code="buyer-pro",
        name="Buyer Pro",
        audience="buyer",
        price_amount=500,
        billing_interval="month",
        features=["prebooking", "prebooking"],
    )

    async def stamp(value: Plan) -> None:
        value.created_at = value.updated_at = _now()

    repository.refresh = AsyncMock(side_effect=stamp)
    created = await service.create_plan(payload)
    assert created.features == ["prebooking"]
    repository.plans = AsyncMock(return_value=[created])
    assert await service.plans() == [created]
    repository.subscriptions = AsyncMock(return_value=[])
    assert await service.subscriptions(user()) == []

    repository.commit = AsyncMock(
        side_effect=IntegrityError("insert", {}, RuntimeError("duplicate"))
    )
    with pytest.raises(ApiError) as duplicate:
        await service.create_plan(payload)
    assert duplicate.value.code == "plan_exists"
    repository.commit = AsyncMock()

    repository.subscription_by_idempotency = AsyncMock(return_value=None)
    repository.plan = AsyncMock(return_value=None)
    with pytest.raises(ApiError) as missing:
        await service.initiate(user(), uuid4(), "subscription-key")
    assert missing.value.code == "plan_not_found"

    farmer_plan = plan("farmer")
    repository.plan = AsyncMock(return_value=farmer_plan)
    with pytest.raises(ApiError) as audience:
        await service.initiate(user("buyer"), farmer_plan.id, "subscription-key")
    assert audience.value.code == "plan_not_available"


@pytest.mark.anyio
async def test_callback_queues_reconciliation_without_granting_access(repository: Any) -> None:
    selected = plan()
    subscription = Subscription(
        id=uuid4(),
        user_id=uuid4(),
        plan_id=selected.id,
        status="pending",
        provider="premium_http",
        account_reference="MVSREFERENCE",
        idempotency_key="key",
    )
    repository.subscription_by_reference = AsyncMock(return_value=subscription)
    await SubscriptionService(
        cast(PremiumRepository, repository), settings(), FakeProvider()
    ).callback("t" * 32, b"{}", {}, "signature")
    assert subscription.status == "pending"
    assert subscription.provider_subscription_ref == "provider-subscription-1"
    assert repository.add.call_count == 2

    with pytest.raises(ApiError) as hidden:
        await SubscriptionService(
            cast(PremiumRepository, repository), settings(), FakeProvider()
        ).callback("wrong", b"{}", {}, "signature")
    assert hidden.value.code == "webhook_not_found"

    repository.subscription_by_reference = AsyncMock(return_value=None)
    with pytest.raises(ApiError) as unmatched:
        await SubscriptionService(
            cast(PremiumRepository, repository), settings(), FakeProvider()
        ).callback("t" * 32, b"{}", {}, "signature")
    assert unmatched.value.code == "premium_callback_unmatched"

    subscription.provider_subscription_ref = "different-reference"
    repository.subscription_by_reference = AsyncMock(return_value=subscription)
    with pytest.raises(ApiError) as mismatch:
        await SubscriptionService(
            cast(PremiumRepository, repository), settings(), FakeProvider()
        ).callback("t" * 32, b"{}", {}, "signature")
    assert mismatch.value.code == "premium_reference_mismatch"


@pytest.mark.anyio
async def test_only_matching_provider_status_grants_entitlement(repository: Any) -> None:
    selected = plan()
    subscription = Subscription(
        id=uuid4(),
        user_id=uuid4(),
        plan_id=selected.id,
        status="pending",
        provider="premium_http",
        provider_subscription_ref="provider-subscription-1",
        account_reference="MVSREFERENCE",
        idempotency_key="key",
    )
    active = SubscriptionStatus(
        "provider-subscription-1",
        "MVSREFERENCE",
        selected.code,
        Decimal("500"),
        "KES",
        "active",
        _now(),
        _now() + timedelta(days=30),
    )
    repository.subscription = AsyncMock(side_effect=[subscription, subscription])
    repository.plan = AsyncMock(return_value=selected)
    await SubscriptionService(
        cast(PremiumRepository, repository), settings(), FakeProvider(active)
    ).reconcile(subscription.id)
    assert subscription.status == "active" and subscription.verified_at is not None

    subscription.status = "pending"
    mismatch = SubscriptionStatus(
        "provider-subscription-1",
        "MVSREFERENCE",
        selected.code,
        Decimal("499"),
        "KES",
        "active",
        _now(),
        _now() + timedelta(days=30),
    )
    repository.subscription = AsyncMock(side_effect=[subscription, subscription])
    await SubscriptionService(
        cast(PremiumRepository, repository), settings(), FakeProvider(mismatch)
    ).reconcile(subscription.id)
    assert subscription.status == "past_due"


@pytest.mark.anyio
async def test_prebooking_permissions_transitions_and_insights(repository: Any) -> None:
    buyer, farmer = user("buyer"), user("farmer")
    selected_plan = plan()
    repository.entitlement = AsyncMock(return_value=True)
    repository.user_has_role = AsyncMock(return_value=True)
    repository.product = AsyncMock(return_value=MagicMock())
    repository.listing = AsyncMock(return_value=None)

    async def stamp(value: Prebooking) -> None:
        value.created_at = value.updated_at = _now()

    repository.refresh = AsyncMock(side_effect=stamp)
    payload = PrebookingCreate(
        farmer_id=farmer.id,
        product_id=uuid4(),
        quantity=Decimal("10"),
        quantity_unit="kg",
        window_start=_now() + timedelta(days=7),
        window_end=_now() + timedelta(days=8),
    )
    service = PrebookingService(cast(PremiumRepository, repository))
    value = await service.create(buyer, payload)
    assert value.status == "requested"

    repository.prebooking = AsyncMock(return_value=value)
    value = await service.transition(
        farmer, value.id, PrebookingTransition(status="accepted", expected_version=1)
    )
    assert value.status == "accepted" and value.version == 2
    with pytest.raises(ApiError) as forbidden:
        await service.transition(
            buyer, value.id, PrebookingTransition(status="fulfilled", expected_version=2)
        )
    assert forbidden.value.code == "prebooking_forbidden"

    repository.farmer_insights = AsyncMock(return_value=(2, Decimal("15"), 3, Decimal("2500")))
    insights = await InsightsService(cast(PremiumRepository, repository)).farmer(farmer)
    assert insights.gross_sales == Decimal("2500")
    assert selected_plan.features


def test_premium_configuration_and_window_validation() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="test", premium_enabled=True)
    with pytest.raises(ValidationError):
        PrebookingCreate(
            farmer_id=uuid4(),
            product_id=uuid4(),
            quantity=1,
            quantity_unit="kg",
            window_start=_now(),
            window_end=_now() - timedelta(days=1),
        )
    assert (
        PlanCreate(
            code="buyer-pro",
            name="Buyer Pro",
            audience="buyer",
            price_amount=500,
            billing_interval="month",
            features=["prebooking"],
        ).currency
        == "KES"
    )
