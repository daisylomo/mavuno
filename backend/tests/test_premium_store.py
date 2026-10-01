from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, create_autospec
from uuid import uuid4

import httpx2 as httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.exc import IntegrityError

from mavuno.api.errors import ApiError
from mavuno.api.v1 import premium
from mavuno.auth.context import AuthenticatedUser
from mavuno.core.config import Settings
from mavuno.db.models import Plan, Subscription, SubscriptionEvent
from mavuno.premium.repository import PremiumRepository
from mavuno.premium.revenuecat import (
    LIFETIME_PERIOD_END,
    REVENUECAT_PROVIDER,
    RevenueCatClient,
    RevenueCatError,
    StoreEntitlement,
)
from mavuno.premium.service import (
    EntitlementService,
    StoreSubscriptionService,
    SubscriptionService,
    _now,
)

WEBHOOK_SECRET = "r" * 32


def settings() -> Settings:
    return Settings(
        environment="test",
        revenuecat_secret_api_key=SecretStr("sk_secret"),
        revenuecat_webhook_authorization=SecretStr(WEBHOOK_SECRET),
    )


def store_plan(audience: str = "buyer") -> Plan:
    return Plan(
        id=uuid4(),
        code=f"revenuecat_{audience}",
        name="Mavuno Premium",
        audience=audience,
        price_amount=Decimal("0"),
        currency="KES",
        billing_interval="month",
        features=["insights", "prebooking"],
        active=True,
    )


class FakeStore:
    def __init__(self, entitlement: StoreEntitlement | None = None, error: bool = False) -> None:
        self.value = entitlement
        self.error = error
        self.calls: list[str] = []

    async def entitlement(self, app_user_id: str) -> StoreEntitlement | None:
        self.calls.append(app_user_id)
        if self.error:
            raise RevenueCatError("RevenueCat request failed")
        return self.value


def entitlement(days: int = 30) -> StoreEntitlement:
    now = _now()
    return StoreEntitlement("mavuno_monthly", now - timedelta(days=1), now + timedelta(days=days))


@pytest.fixture
def repository() -> Any:
    value = create_autospec(PremiumRepository, instance=True)
    value.add = MagicMock()
    value.commit = AsyncMock()
    value.rollback = AsyncMock()
    value.refresh = AsyncMock()
    value.provider_subscription = AsyncMock(return_value=None)
    value.user_has_role = AsyncMock(return_value=False)
    value.plan_by_code = AsyncMock(side_effect=lambda code: store_plan(code.split("_")[1]))
    value.user_exists = AsyncMock(return_value=True)
    return value


@pytest.mark.anyio
async def test_revenuecat_client_reads_entitlement_with_secret_key_and_grace_period() -> None:
    with pytest.raises(RevenueCatError, match="not configured"):
        RevenueCatClient(Settings(environment="test"))
    requests: list[httpx.Request] = []
    responses = iter(
        [
            httpx.Response(
                200,
                json={
                    "subscriber": {
                        "entitlements": {
                            "mavuno_premium": {
                                "product_identifier": "mavuno_monthly",
                                "purchase_date": "2026-09-01T00:00:00Z",
                                "expires_date": "2026-10-01T00:00:00Z",
                                "grace_period_expires_date": "2026-10-08T00:00:00Z",
                            }
                        }
                    }
                },
            ),
            httpx.Response(200, json={"subscriber": {"entitlements": {}}}),
            httpx.Response(
                200,
                json={
                    "subscriber": {
                        "entitlements": {
                            "mavuno_premium": {
                                "product_identifier": "lifetime",
                                "expires_date": None,
                            }
                        }
                    }
                },
            ),
            httpx.Response(500),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return next(responses)

    client = httpx.AsyncClient(
        base_url="https://api.revenuecat.com", transport=httpx.MockTransport(handler)
    )
    store = RevenueCatClient(settings(), client)
    value = await store.entitlement("user/1")
    assert value is not None
    assert value.expires_at == datetime(2026, 10, 8)
    assert value.active(datetime(2026, 10, 5)) and not value.active(datetime(2026, 10, 9))
    assert requests[0].url.raw_path == b"/v1/subscribers/user%2F1"
    assert requests[0].headers["Authorization"] == "Bearer sk_secret"
    assert await store.entitlement("user") is None
    lifetime = await store.entitlement("user")
    assert lifetime is not None and lifetime.expires_at is None and lifetime.active(_now())
    with pytest.raises(RevenueCatError):
        await store.entitlement("user")
    await store.aclose()
    await client.aclose()


@pytest.mark.anyio
async def test_store_purchase_becomes_verified_subscription_on_role_plan(repository: Any) -> None:
    user_id = uuid4()
    store = FakeStore(entitlement())
    subscription = await StoreSubscriptionService(
        cast(PremiumRepository, repository), settings(), store
    ).sync(user_id)
    assert subscription is not None
    assert store.calls == [str(user_id)]
    assert subscription.provider == REVENUECAT_PROVIDER
    assert subscription.status == "active" and subscription.verified_at is not None
    assert subscription.account_reference == f"RC{user_id.hex.upper()}"
    repository.plan_by_code.assert_awaited_with("revenuecat_buyer")
    repository.add.assert_called_once_with(subscription)

    repository.user_has_role = AsyncMock(return_value=True)
    repository.add.reset_mock()
    await StoreSubscriptionService(cast(PremiumRepository, repository), settings(), store).sync(
        uuid4()
    )
    repository.plan_by_code.assert_awaited_with("revenuecat_farmer")

    lifetime = FakeStore(StoreEntitlement("lifetime", None, None))
    value = await StoreSubscriptionService(
        cast(PremiumRepository, repository), settings(), lifetime
    ).sync(uuid4())
    assert value is not None and value.current_period_end == LIFETIME_PERIOD_END


@pytest.mark.anyio
async def test_store_lapse_and_missing_entitlement_revoke_access(repository: Any) -> None:
    existing = Subscription(
        id=uuid4(), user_id=uuid4(), plan_id=uuid4(), status="active", provider=REVENUECAT_PROVIDER
    )
    repository.provider_subscription = AsyncMock(return_value=existing)
    lapsed = await StoreSubscriptionService(
        cast(PremiumRepository, repository), settings(), FakeStore(entitlement(days=-2))
    ).sync(existing.user_id)
    assert lapsed is existing and existing.status == "expired"
    repository.add.assert_not_called()

    existing.status = "active"
    gone = await StoreSubscriptionService(
        cast(PremiumRepository, repository), settings(), FakeStore(None)
    ).sync(existing.user_id)
    assert gone is existing and existing.status == "expired"

    repository.provider_subscription = AsyncMock(return_value=None)
    assert (
        await StoreSubscriptionService(
            cast(PremiumRepository, repository), settings(), FakeStore(None)
        ).sync(uuid4())
        is None
    )


@pytest.mark.anyio
async def test_store_sync_fails_closed(repository: Any) -> None:
    with pytest.raises(ApiError) as unconfigured:
        await StoreSubscriptionService(
            cast(PremiumRepository, repository), Settings(environment="test")
        ).sync(uuid4())
    assert unconfigured.value.code == "store_purchases_unavailable"
    with pytest.raises(ApiError) as unavailable:
        await StoreSubscriptionService(
            cast(PremiumRepository, repository), settings(), FakeStore(error=True)
        ).sync(uuid4())
    assert unavailable.value.status_code == 503
    repository.plan_by_code = AsyncMock(return_value=None)
    with pytest.raises(ApiError, match="not set up"):
        await StoreSubscriptionService(
            cast(PremiumRepository, repository), settings(), FakeStore(entitlement())
        ).sync(uuid4())
    repository.commit.assert_not_awaited()


@pytest.mark.anyio
async def test_concurrent_store_sync_returns_the_winning_record(repository: Any) -> None:
    winner = Subscription(id=uuid4(), user_id=uuid4(), plan_id=uuid4(), status="active")
    repository.commit = AsyncMock(side_effect=IntegrityError("insert", {}, Exception()))
    repository.provider_subscription = AsyncMock(side_effect=[None, winner])
    value = await StoreSubscriptionService(
        cast(PremiumRepository, repository), settings(), FakeStore(entitlement())
    ).sync(winner.user_id)
    assert value is winner
    repository.rollback.assert_awaited_once()


@pytest.mark.anyio
async def test_webhook_is_authenticated_and_resyncs_known_users_only(repository: Any) -> None:
    service = StoreSubscriptionService(
        cast(PremiumRepository, repository), settings(), FakeStore(entitlement())
    )
    with pytest.raises(ApiError) as forbidden:
        await service.webhook("Bearer wrong", {"event": {}})
    assert forbidden.value.status_code == 404
    with pytest.raises(ApiError) as unconfigured:
        await StoreSubscriptionService(
            cast(PremiumRepository, repository), Settings(environment="test")
        ).webhook(WEBHOOK_SECRET, {"event": {}})
    assert unconfigured.value.code == "webhook_not_found"
    with pytest.raises(ApiError) as malformed:
        await service.webhook(WEBHOOK_SECRET, {})
    assert malformed.value.status_code == 422

    member, stranger = uuid4(), uuid4()
    repository.user_exists = AsyncMock(side_effect=lambda user_id: user_id == member)
    store = FakeStore(entitlement())
    service = StoreSubscriptionService(cast(PremiumRepository, repository), settings(), store)
    await service.webhook(
        f"Bearer {WEBHOOK_SECRET}",
        {
            "event": {
                "id": "evt-1",
                "type": "INITIAL_PURCHASE",
                "app_user_id": "$RCAnonymousID:abc",
                "original_app_user_id": str(member),
                "aliases": [str(member), str(stranger)],
                "product_id": "mavuno_monthly",
                "store": "PLAY_STORE",
            }
        },
    )
    assert store.calls == [str(member)]
    recorded = [
        call.args[0]
        for call in repository.add.call_args_list
        if isinstance(call.args[0], SubscriptionEvent)
    ]
    assert len(recorded) == 1 and recorded[0].provider_event_ref == f"evt-1:{member}"
    assert recorded[0].payload_redacted["store"] == "PLAY_STORE"

    repository.commit = AsyncMock(side_effect=[None, IntegrityError("insert", {}, Exception())])
    await service.webhook(WEBHOOK_SECRET, {"event": {"id": "evt-1", "app_user_id": str(member)}})
    repository.rollback.assert_awaited()


@pytest.mark.anyio
async def test_entitlements_report_backend_decision(repository: Any) -> None:
    user_id = uuid4()
    repository.active_subscriptions = AsyncMock(return_value=[])
    empty = await EntitlementService(cast(PremiumRepository, repository), settings()).current(
        user_id
    )
    assert not empty.premium and empty.features == [] and empty.purchases_available

    end = _now() + timedelta(days=10)
    short = Subscription(provider="premium_http", current_period_end=end)
    lifetime = Subscription(provider=REVENUECAT_PROVIDER, current_period_end=LIFETIME_PERIOD_END)
    repository.active_subscriptions = AsyncMock(
        return_value=[(short, store_plan()), (lifetime, store_plan())]
    )
    value = await EntitlementService(
        cast(PremiumRepository, repository), Settings(environment="test")
    ).current(user_id)
    assert value.premium and value.features == ["insights", "prebooking"]
    assert value.provider == REVENUECAT_PROVIDER and value.expires_at is None
    assert not value.purchases_available


@pytest.mark.anyio
async def test_store_plans_cannot_be_bought_directly(repository: Any) -> None:
    repository.subscription_by_idempotency = AsyncMock(return_value=None)
    repository.plan = AsyncMock(return_value=store_plan())
    direct = Settings(
        environment="test",
        premium_enabled=True,
        premium_provider_base_url="https://billing.example.test",
        premium_provider_api_key=SecretStr("provider-api-key"),
        premium_webhook_secret=SecretStr("w" * 32),
        premium_callback_token=SecretStr("t" * 32),
    )
    member = AuthenticatedUser(uuid4(), "buyer@example.test", None, frozenset({"buyer"}), 0)
    with pytest.raises(ApiError) as missing:
        await SubscriptionService(cast(PremiumRepository, repository), direct).initiate(
            member, uuid4(), "subscription-key"
        )
    assert missing.value.code == "plan_not_found"


@pytest.mark.anyio
async def test_store_routes_delegate_to_services(monkeypatch: pytest.MonkeyPatch) -> None:
    current = AuthenticatedUser(uuid4(), "buyer@example.test", None, frozenset({"buyer"}), 0)
    request = cast(
        Any,
        SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(settings=settings())),
            body=AsyncMock(return_value=json.dumps({"event": {"id": "evt"}}).encode()),
        ),
    )
    entitlements = MagicMock()
    entitlements.current = AsyncMock(return_value="entitlements")
    store = MagicMock()
    store.sync = AsyncMock()
    store.webhook = AsyncMock()
    monkeypatch.setattr(premium, "EntitlementService", lambda *_args: entitlements)
    monkeypatch.setattr(premium, "StoreSubscriptionService", lambda *_args: store)
    session = MagicMock()

    assert await premium.current_entitlements(current, session, request) == "entitlements"
    assert await premium.sync_store_purchases(current, session, request) == "entitlements"
    store.sync.assert_awaited_once_with(current.id)
    assert await premium.revenuecat_webhook(request, session, "Bearer token") == {"accepted": True}
    store.webhook.assert_awaited_with("Bearer token", {"event": {"id": "evt"}})
    for body in (b"not-json", b"[1]"):
        request.body = AsyncMock(return_value=body)
        await premium.revenuecat_webhook(request, session, "Bearer token")
        store.webhook.assert_awaited_with("Bearer token", {})


def test_store_entitlement_activity() -> None:
    assert StoreEntitlement("x", None, None).active(_now())
    assert not StoreEntitlement("x", None, _now() - timedelta(seconds=1)).active(_now())
