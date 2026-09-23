import asyncio
import os
import uuid
from typing import Tuple

import pytest
from pydantic import SecretStr

from api_client.client import MavunoClient
from api_client.models.auth import RegisterRequest

BASE_URL = os.getenv("MAVUNO_API_BASE_URL", "http://127.0.0.1:8000/api/v1")
DATABASE_URL = os.getenv(
    "MAVUNO_TEST_DATABASE_URL",
    os.getenv(
        "MAVUNO_DATABASE_URL",
        "mysql+aiomysql://mavuno:change-me@127.0.0.1:3306/mavuno?charset=utf8mb4",
    ),
)


@pytest.fixture(scope="session")
def client() -> MavunoClient:
    return MavunoClient(base_url=BASE_URL)


def unique_phone() -> str:
    return f"+2547{str(uuid.uuid4().int)[:8]}"


def register_and_login(client: MavunoClient, role: str) -> Tuple[MavunoClient, str]:
    """Registers a fresh user with the given role and returns (authenticated client, user_id)."""
    session_client = MavunoClient(base_url=client.base_url)
    res = session_client.auth.register(
        RegisterRequest(phone=unique_phone(), password="Password123!", role=role)
    )
    assert res.success is True, f"Registration failed: {res.error}"
    session_client.set_auth_token(res.data.access_token)
    return session_client, res.data.user.id


async def _seed_catalog_product() -> Tuple[str, str]:
    """Directly inserts a produce category + product, bypassing the admin-only HTTP endpoints."""
    from mavuno.core.config import Settings
    from mavuno.db import Database
    from mavuno.db.models import ProduceCategory, Product

    unique = uuid.uuid4().hex[:10]
    category_id = uuid.uuid4()
    product_id = uuid.uuid4()

    database = Database(Settings(environment="test", database_url=SecretStr(DATABASE_URL)))
    try:
        async with database.session() as session:
            session.add(
                ProduceCategory(id=category_id, name=f"Test Category {unique}", slug=f"cat-{unique}")
            )
            await session.flush()
            session.add(
                Product(
                    id=product_id,
                    category_id=category_id,
                    name=f"Test Product {unique}",
                    slug=f"product-{unique}",
                    default_unit="kg",
                )
            )
            await session.commit()
    finally:
        await database.dispose()
    return str(category_id), str(product_id)


@pytest.fixture(scope="session")
def test_product() -> str:
    """Session-scoped product_id backing catalog/commerce/premium listing tests."""
    _, product_id = asyncio.run(_seed_catalog_product())
    return product_id


async def _mark_order_paid(order_id: str) -> None:
    """Directly flips an order to "paid", bypassing the unconfigured M-Pesa/bank payment rails."""
    from datetime import UTC, datetime

    from mavuno.core.config import Settings
    from mavuno.db import Database
    from mavuno.db.models import Order

    database = Database(Settings(environment="test", database_url=SecretStr(DATABASE_URL)))
    try:
        async with database.session() as session:
            order = await session.get(Order, uuid.UUID(order_id))
            assert order is not None
            order.status = "paid"
            order.paid_at = datetime.now(UTC).replace(tzinfo=None)
            order.version += 1
            await session.commit()
    finally:
        await database.dispose()


def mark_order_paid(order_id: str) -> None:
    asyncio.run(_mark_order_paid(order_id))


async def _grant_premium_entitlement(user_id: str, audience: str, features: list) -> None:
    """Seeds an active, verified subscription directly, bypassing the payment-provider webhook."""
    from datetime import UTC, datetime, timedelta

    from mavuno.core.config import Settings
    from mavuno.db import Database
    from mavuno.db.models import Plan, Subscription

    unique = uuid.uuid4().hex[:10]
    plan_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)

    database = Database(Settings(environment="test", database_url=SecretStr(DATABASE_URL)))
    try:
        async with database.session() as session:
            session.add(
                Plan(
                    id=plan_id,
                    code=f"test-plan-{unique}",
                    name=f"Test Plan {unique}",
                    audience=audience,
                    price_amount="500.0000",
                    currency="KES",
                    billing_interval="month",
                    features=features,
                    active=True,
                )
            )
            await session.flush()
            session.add(
                Subscription(
                    id=uuid.uuid4(),
                    user_id=uuid.UUID(user_id),
                    plan_id=plan_id,
                    status="active",
                    provider="test",
                    account_reference=f"test-{unique}",
                    idempotency_key=f"test-{unique}",
                    current_period_start=now,
                    current_period_end=now + timedelta(days=30),
                    verified_at=now,
                )
            )
            await session.commit()
    finally:
        await database.dispose()


def grant_premium_entitlement(user_id: str, audience: str, features: list) -> None:
    asyncio.run(_grant_premium_entitlement(user_id, audience, features))