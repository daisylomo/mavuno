from __future__ import annotations

import os
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import delete

from mavuno.auth.context import AuthenticatedUser
from mavuno.core.config import Settings
from mavuno.db import Database
from mavuno.db.models import (
    Listing,
    Plan,
    Prebooking,
    ProduceCategory,
    Product,
    Subscription,
    User,
    UserRole,
)
from mavuno.premium.repository import PremiumRepository
from mavuno.premium.schemas import PrebookingCreate, PrebookingTransition
from mavuno.premium.service import InsightsService, PrebookingService, _now

TEST_DATABASE_URL = os.getenv("MAVUNO_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="MAVUNO_TEST_DATABASE_URL is not set"),
]


@pytest.mark.anyio
async def test_verified_entitlements_drive_prebooking_and_insights() -> None:
    assert TEST_DATABASE_URL is not None
    database = Database(Settings(environment="test", database_url=SecretStr(TEST_DATABASE_URL)))
    buyer_id, farmer_id, category_id, product_id, listing_id = (uuid4() for _ in range(5))
    buyer_plan_id, farmer_plan_id = uuid4(), uuid4()
    buyer_subscription_id, farmer_subscription_id = uuid4(), uuid4()
    buyer = AuthenticatedUser(buyer_id, "buyer-premium@example.test", None, frozenset({"buyer"}), 0)
    farmer = AuthenticatedUser(
        farmer_id, "farmer-premium@example.test", None, frozenset({"farmer"}), 0
    )
    now = _now()
    try:
        async with database.session() as session:
            session.add_all(
                [
                    User(
                        id=buyer_id,
                        email=f"{buyer_id}@example.test",
                        password_hash="x",
                        status="active",
                    ),
                    User(
                        id=farmer_id,
                        email=f"{farmer_id}@example.test",
                        password_hash="x",
                        status="active",
                    ),
                    ProduceCategory(
                        id=category_id, name="Premium grain", slug=f"grain-{category_id}"
                    ),
                ]
            )
            await session.flush()
            session.add(UserRole(user_id=farmer_id, role_name="farmer"))
            session.add(
                Product(
                    id=product_id,
                    category_id=category_id,
                    name="Premium maize",
                    slug=f"maize-{product_id}",
                    default_unit="kg",
                )
            )
            session.add_all(
                [
                    Plan(
                        id=buyer_plan_id,
                        code=f"buyer-{buyer_plan_id}",
                        name="Buyer Pro",
                        audience="buyer",
                        price_amount=Decimal("500"),
                        currency="KES",
                        billing_interval="month",
                        features=["prebooking"],
                        active=True,
                    ),
                    Plan(
                        id=farmer_plan_id,
                        code=f"farmer-{farmer_plan_id}",
                        name="Farmer Pro",
                        audience="farmer",
                        price_amount=Decimal("700"),
                        currency="KES",
                        billing_interval="month",
                        features=["insights"],
                        active=True,
                    ),
                ]
            )
            await session.flush()
            session.add(
                Listing(
                    id=listing_id,
                    farmer_id=farmer_id,
                    product_id=product_id,
                    title="Premium maize",
                    price_amount=Decimal("100"),
                    currency="KES",
                    available_quantity=Decimal("20"),
                    quantity_unit="kg",
                    status="active",
                    version=1,
                )
            )
            session.add_all(
                [
                    Subscription(
                        id=buyer_subscription_id,
                        user_id=buyer_id,
                        plan_id=buyer_plan_id,
                        status="active",
                        provider="test",
                        provider_subscription_ref="buyer-provider",
                        account_reference=f"BUYER{buyer_id.hex}",
                        idempotency_key="buyer-key",
                        current_period_start=now,
                        current_period_end=now + timedelta(days=30),
                        verified_at=now,
                    ),
                    Subscription(
                        id=farmer_subscription_id,
                        user_id=farmer_id,
                        plan_id=farmer_plan_id,
                        status="active",
                        provider="test",
                        provider_subscription_ref="farmer-provider",
                        account_reference=f"FARMER{farmer_id.hex}",
                        idempotency_key="farmer-key",
                        current_period_start=now,
                        current_period_end=now + timedelta(days=30),
                        verified_at=now,
                    ),
                ]
            )
            await session.commit()

        async with database.session() as session:
            service = PrebookingService(PremiumRepository(session))
            value = await service.create(
                buyer,
                PrebookingCreate(
                    farmer_id=farmer_id,
                    product_id=product_id,
                    listing_id=listing_id,
                    quantity=Decimal("5"),
                    quantity_unit="kg",
                    window_start=now + timedelta(days=5),
                    window_end=now + timedelta(days=6),
                ),
            )
            assert len(await service.list(buyer)) == 1
            accepted = await service.transition(
                farmer, value.id, PrebookingTransition(status="accepted", expected_version=1)
            )
            assert accepted.status == "accepted"

        async with database.session() as session:
            insights = await InsightsService(PremiumRepository(session)).farmer(farmer)
            assert insights.active_listings == 1
            assert insights.units_available == Decimal("20.000")
    finally:
        async with database.session() as session:
            await session.execute(delete(Prebooking).where(Prebooking.buyer_id == buyer_id))
            await session.execute(
                delete(Subscription).where(Subscription.user_id.in_((buyer_id, farmer_id)))
            )
            await session.execute(delete(Listing).where(Listing.id == listing_id))
            await session.execute(delete(Plan).where(Plan.id.in_((buyer_plan_id, farmer_plan_id))))
            await session.execute(delete(Product).where(Product.id == product_id))
            await session.execute(delete(ProduceCategory).where(ProduceCategory.id == category_id))
            await session.execute(delete(User).where(User.id.in_((buyer_id, farmer_id))))
            await session.commit()
        await database.dispose()
