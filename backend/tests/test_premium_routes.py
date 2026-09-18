from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from mavuno.api.v1 import premium
from mavuno.auth.context import AuthenticatedUser
from mavuno.core.config import Settings
from mavuno.premium.schemas import (
    PlanCreate,
    PrebookingCreate,
    PrebookingTransition,
    SubscriptionCreate,
)
from mavuno.premium.service import _now


@pytest.mark.anyio
async def test_premium_routes_delegate_to_domain_services(monkeypatch: pytest.MonkeyPatch) -> None:
    current = AuthenticatedUser(uuid4(), "buyer@example.test", None, frozenset({"buyer"}), 0)
    admin = AuthenticatedUser(uuid4(), "admin@example.test", None, frozenset({"administrator"}), 0)
    session = MagicMock()
    request = cast(
        Any,
        SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(settings=Settings(environment="test"))),
            body=AsyncMock(return_value=json.dumps({"event_reference": "event"}).encode()),
        ),
    )
    subscription = MagicMock()
    subscription.plans = AsyncMock(return_value=["plan"])
    subscription.create_plan = AsyncMock(return_value="created-plan")
    subscription.subscriptions = AsyncMock(return_value=["subscription"])
    subscription.initiate = AsyncMock(return_value="pending-subscription")
    subscription.callback = AsyncMock()
    prebooking = MagicMock()
    prebooking.list = AsyncMock(return_value=["prebooking"])
    prebooking.create = AsyncMock(return_value="created-prebooking")
    prebooking.transition = AsyncMock(return_value="accepted-prebooking")
    insights = MagicMock()
    insights.farmer = AsyncMock(return_value="insights")
    monkeypatch.setattr(premium, "SubscriptionService", lambda *_args: subscription)
    monkeypatch.setattr(premium, "PrebookingService", lambda *_args: prebooking)
    monkeypatch.setattr(premium, "InsightsService", lambda *_args: insights)

    assert await premium.list_plans(session, request) == ["plan"]
    plan_payload = PlanCreate(
        code="buyer-pro",
        name="Buyer Pro",
        audience="buyer",
        price_amount=500,
        billing_interval="month",
        features=["prebooking"],
    )
    assert await premium.create_plan(plan_payload, admin, session, request) == "created-plan"
    assert await premium.list_subscriptions(current, session, request) == ["subscription"]
    assert (
        await premium.initiate_subscription(
            SubscriptionCreate(plan_id=uuid4()), "subscription-key", current, session, request
        )
        == "pending-subscription"
    )
    assert await premium.premium_callback("token", request, session, "signature") == {
        "accepted": True
    }
    request.body = AsyncMock(return_value=b"not-json")
    assert await premium.premium_callback("token", request, session, "signature") == {
        "accepted": True
    }

    assert await premium.list_prebookings(current, session) == ["prebooking"]
    prebooking_payload = PrebookingCreate(
        farmer_id=uuid4(),
        product_id=uuid4(),
        quantity=1,
        quantity_unit="kg",
        window_start=_now(),
        window_end=_now().replace(year=_now().year + 1),
    )
    assert (
        await premium.create_prebooking(prebooking_payload, current, session)
        == "created-prebooking"
    )
    assert (
        await premium.transition_prebooking(
            uuid4(), PrebookingTransition(status="accepted", expected_version=1), current, session
        )
        == "accepted-prebooking"
    )
    assert await premium.farmer_insights(current, session) == "insights"
