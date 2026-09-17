from __future__ import annotations

import os
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from mavuno.auth.context import AuthenticatedUser
from mavuno.core.config import Settings
from mavuno.db import Database
from mavuno.db.models import (
    Fulfilment,
    FulfilmentStatusHistory,
    Listing,
    Order,
    OrderItem,
    OrderStatusHistory,
    ProduceCategory,
    Product,
    User,
)
from mavuno.fulfilment.repository import FulfilmentRepository
from mavuno.fulfilment.schemas import FulfilmentTransition, FulfilmentUpdate
from mavuno.fulfilment.service import FulfilmentService, _now

TEST_DATABASE_URL = os.getenv("MAVUNO_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="MAVUNO_TEST_DATABASE_URL is not set"),
]


async def seed(database: Database) -> tuple[Order, UUID, UUID, UUID, UUID]:
    buyer_id, farmer_id, category_id, product_id, listing_id = (uuid4() for _ in range(5))
    current_order = Order(
        id=uuid4(),
        buyer_id=buyer_id,
        status="paid",
        currency="KES",
        subtotal_amount=Decimal("250"),
        total_amount=Decimal("250"),
        idempotency_key=f"fulfilment-{uuid4()}",
        reservation_expires_at=_now(),
        version=1,
    )
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
            ]
        )
        await session.flush()
        session.add(ProduceCategory(id=category_id, name="Fruit", slug=f"fruit-{category_id}"))
        await session.flush()
        session.add(
            Product(
                id=product_id,
                category_id=category_id,
                name="Mango",
                slug=f"mango-{product_id}",
                default_unit="kg",
            )
        )
        await session.flush()
        session.add(
            Listing(
                id=listing_id,
                farmer_id=farmer_id,
                product_id=product_id,
                title="Mangoes",
                price_amount=Decimal("250"),
                currency="KES",
                available_quantity=Decimal("5"),
                quantity_unit="kg",
                status="active",
                version=1,
            )
        )
        await session.flush()
        session.add(current_order)
        await session.flush()
        session.add(
            OrderItem(
                id=uuid4(),
                order_id=current_order.id,
                listing_id=listing_id,
                farmer_id=farmer_id,
                product_name="Mango",
                listing_title="Mangoes",
                quantity=Decimal("1"),
                quantity_unit="kg",
                unit_price=Decimal("250"),
                line_total=Decimal("250"),
            )
        )
        await session.commit()
    return current_order, buyer_id, farmer_id, product_id, listing_id


async def cleanup(
    database: Database,
    current_order: Order,
    buyer_id: UUID,
    farmer_id: UUID,
    product_id: UUID,
    listing_id: UUID,
) -> None:
    async with database.session() as session:
        records = list(
            await session.scalars(
                select(Fulfilment.id).where(Fulfilment.order_id == current_order.id)
            )
        )
        if records:
            await session.execute(
                delete(FulfilmentStatusHistory).where(
                    FulfilmentStatusHistory.fulfilment_id.in_(records)
                )
            )
            await session.execute(delete(Fulfilment).where(Fulfilment.id.in_(records)))
        await session.execute(
            delete(OrderStatusHistory).where(OrderStatusHistory.order_id == current_order.id)
        )
        await session.execute(delete(OrderItem).where(OrderItem.order_id == current_order.id))
        await session.execute(delete(Order).where(Order.id == current_order.id))
        await session.execute(delete(Listing).where(Listing.id == listing_id))
        product = await session.get(Product, product_id)
        assert product is not None
        category_id = product.category_id
        await session.delete(product)
        await session.execute(delete(ProduceCategory).where(ProduceCategory.id == category_id))
        await session.execute(delete(User).where(User.id.in_((buyer_id, farmer_id))))
        await session.commit()


@pytest.mark.anyio
async def test_fulfilment_lifecycle_permissions_history_and_unique_order() -> None:
    assert TEST_DATABASE_URL is not None
    database = Database(Settings(environment="test", database_url=SecretStr(TEST_DATABASE_URL)))
    current_order, buyer_id, farmer_id, product_id, listing_id = await seed(database)
    buyer = AuthenticatedUser(buyer_id, None, None, frozenset({"buyer"}), 0)
    farmer = AuthenticatedUser(farmer_id, None, None, frozenset({"farmer"}), 0)
    try:
        async with database.session() as session:
            service = FulfilmentService(FulfilmentRepository(session))
            created = await service.update(
                buyer,
                current_order.id,
                FulfilmentUpdate(
                    method="delivery",
                    location_label="Buyer shop",
                    location_details="Kenyatta Avenue",
                    latitude=Decimal("-1.286389"),
                    longitude=Decimal("36.817223"),
                    window_start=_now() + timedelta(hours=2),
                    window_end=_now() + timedelta(hours=4),
                    coordination_notes="Call on arrival",
                ),
            )
            assert created.status == "pending"
            assert created.history[0].new_status == "pending"

        async with database.session() as session:
            service = FulfilmentService(FulfilmentRepository(session))
            scheduled = await service.transition(
                farmer,
                current_order.id,
                FulfilmentTransition(status="scheduled", expected_version=1),
            )
            assert scheduled.version == 2
            assert await service.get(farmer, current_order.id) == scheduled
            await service.transition(
                farmer,
                current_order.id,
                FulfilmentTransition(status="ready_for_handover", expected_version=2),
            )

        async with database.session() as session:
            service = FulfilmentService(FulfilmentRepository(session))
            await service.transition(
                farmer,
                current_order.id,
                FulfilmentTransition(status="in_transit", expected_version=3),
            )
            completed = await service.transition(
                buyer,
                current_order.id,
                FulfilmentTransition(status="completed", expected_version=4),
            )
            assert completed.status == "completed"
            assert len(completed.history) == 5
            stored_order = await session.get(Order, current_order.id)
            assert stored_order is not None and stored_order.status == "completed"

        async with database.session() as session:
            session.add(
                Fulfilment(
                    id=uuid4(),
                    order_id=current_order.id,
                    method="pickup",
                    status="pending",
                    location_label="Farm",
                    location_details="Gate",
                    window_start=_now() + timedelta(hours=1),
                    window_end=_now() + timedelta(hours=2),
                    version=1,
                )
            )
            with pytest.raises(IntegrityError):
                await session.commit()
            await session.rollback()
    finally:
        await cleanup(database, current_order, buyer_id, farmer_id, product_id, listing_id)
        await database.dispose()
