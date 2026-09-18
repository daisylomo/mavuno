from __future__ import annotations

import os
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import delete, select

from mavuno.auth.context import AuthenticatedUser
from mavuno.commerce.repository import CommerceRepository
from mavuno.commerce.service import CartService, CheckoutService, _now
from mavuno.core.config import Settings
from mavuno.db import Database
from mavuno.db.models import (
    Cart,
    CartItem,
    InventoryMovement,
    Listing,
    Order,
    OrderItem,
    OrderStatusHistory,
    OutboxJob,
    ProduceCategory,
    Product,
    User,
)

TEST_DATABASE_URL = os.getenv("MAVUNO_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="MAVUNO_TEST_DATABASE_URL is not set"),
]


async def seed(database: Database) -> tuple[AuthenticatedUser, UUID, UUID, UUID, UUID]:
    buyer_id, farmer_id, category_id, product_id, listing_id = (uuid4() for _ in range(5))
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
        session.add(ProduceCategory(id=category_id, name="Grains", slug=f"grains-{category_id}"))
        await session.flush()
        session.add(
            Product(
                id=product_id,
                category_id=category_id,
                name="Maize",
                slug=f"maize-{product_id}",
                default_unit="kg",
            )
        )
        await session.flush()
        session.add(
            Listing(
                id=listing_id,
                farmer_id=farmer_id,
                product_id=product_id,
                title="Dry maize",
                price_amount=Decimal("100"),
                currency="KES",
                available_quantity=Decimal("10"),
                quantity_unit="kg",
                status="active",
                version=1,
            )
        )
        await session.commit()
    return (
        AuthenticatedUser(buyer_id, "buyer@example.test", None, frozenset({"buyer"}), 0),
        farmer_id,
        category_id,
        product_id,
        listing_id,
    )


async def cleanup(
    database: Database,
    buyer_id: UUID,
    farmer_id: UUID,
    category_id: UUID,
    product_id: UUID,
    listing_id: UUID,
) -> None:
    async with database.session() as session:
        order_ids = list(await session.scalars(select(Order.id).where(Order.buyer_id == buyer_id)))
        if order_ids:
            await session.execute(delete(OutboxJob))
            await session.execute(
                delete(OrderStatusHistory).where(OrderStatusHistory.order_id.in_(order_ids))
            )
            await session.execute(delete(OrderItem).where(OrderItem.order_id.in_(order_ids)))
        await session.execute(
            delete(InventoryMovement).where(InventoryMovement.listing_id == listing_id)
        )
        if order_ids:
            await session.execute(delete(Order).where(Order.id.in_(order_ids)))
        cart_ids = list(await session.scalars(select(Cart.id).where(Cart.buyer_id == buyer_id)))
        if cart_ids:
            await session.execute(delete(CartItem).where(CartItem.cart_id.in_(cart_ids)))
            await session.execute(delete(Cart).where(Cart.id.in_(cart_ids)))
        await session.execute(delete(Listing).where(Listing.id == listing_id))
        await session.execute(delete(Product).where(Product.id == product_id))
        await session.execute(delete(ProduceCategory).where(ProduceCategory.id == category_id))
        await session.execute(delete(User).where(User.id.in_((buyer_id, farmer_id))))
        await session.commit()


@pytest.mark.anyio
async def test_checkout_is_idempotent_and_expiration_releases_inventory() -> None:
    assert TEST_DATABASE_URL is not None
    settings = Settings(environment="test", database_url=SecretStr(TEST_DATABASE_URL))
    database = Database(settings)
    buyer, farmer_id, category_id, product_id, listing_id = await seed(database)
    try:
        async with database.session() as session:
            cart = await CartService(CommerceRepository(session)).upsert(
                buyer, listing_id, Decimal("4")
            )
            assert cart.subtotal_amount == Decimal("400")

        async with database.session() as session:
            checkout = CheckoutService(CommerceRepository(session), settings)
            order = await checkout.checkout(buyer, "checkout-idempotency-key", None)
            same = await checkout.checkout(buyer, "checkout-idempotency-key", None)
            assert same.id == order.id
            assert order.items[0].product_name == "Maize"

        async with database.session() as session:
            listing = await session.get(Listing, listing_id)
            assert listing is not None and listing.available_quantity == Decimal("6.000")
            stored_order = await session.get(Order, order.id)
            assert stored_order is not None
            stored_order.reservation_expires_at = _now() - timedelta(seconds=1)
            await session.commit()

        async with database.session() as session:
            await CheckoutService(CommerceRepository(session), settings).expire(order.id)

        async with database.session() as session:
            listing = await session.get(Listing, listing_id)
            expired = await session.get(Order, order.id)
            assert listing is not None and listing.available_quantity == Decimal("10.000")
            assert expired is not None and expired.status == "expired"
    finally:
        await cleanup(database, buyer.id, farmer_id, category_id, product_id, listing_id)
        await database.dispose()
