"""End-to-end checks against MySQL for the release blockers found in emulator testing.

* An approved M-PESA payment completes the order even though Daraja's status query returns
  neither the amount nor the receipt number.
* A payment that arrives after the reservation lapsed never oversells stock.
* In a mixed order each farmer hands over only their own items.
"""

from __future__ import annotations

import base64
import os
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import delete, select

from mavuno.api.errors import ApiError
from mavuno.auth.context import AuthenticatedUser
from mavuno.catalog.repository import CatalogRepository
from mavuno.catalog.schemas import PhotoUpload
from mavuno.catalog.service import CatalogService
from mavuno.commerce.repository import CommerceRepository
from mavuno.commerce.schemas import PaymentInitiateRequest
from mavuno.commerce.service import CartService, CheckoutService, PaymentService, _now
from mavuno.core.config import Settings
from mavuno.db import Database
from mavuno.db.models import (
    Cart,
    CartItem,
    FarmerProfile,
    Fulfilment,
    FulfilmentStatusHistory,
    InventoryMovement,
    Listing,
    ListingImage,
    Order,
    OrderItem,
    OrderStatusHistory,
    OutboxJob,
    Payment,
    PaymentEvent,
    PaymentReconciliation,
    PaymentRefund,
    ProduceCategory,
    Product,
    Profile,
    User,
)
from mavuno.fulfilment.repository import FulfilmentRepository
from mavuno.fulfilment.schemas import FulfilmentTransition, FulfilmentUpdate
from mavuno.fulfilment.service import FulfilmentService
from mavuno.payments.provider import (
    CallbackEvent,
    InitiationRequest,
    InitiationResult,
    ProviderStatus,
    ReversalResult,
)

TEST_DATABASE_URL = os.getenv("MAVUNO_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="MAVUNO_TEST_DATABASE_URL is not set"),
]
TOKEN = "t" * 32


class SandboxLikeProvider:
    """Behaves like Daraja: the query confirms success but omits amount and receipt."""

    name = "daraja"

    def __init__(self) -> None:
        self.request_ref = f"ws_CO_{uuid4().hex[:12]}"

    async def initiate(self, request: InitiationRequest) -> InitiationResult:
        return InitiationResult(self.request_ref, "merchant", "pending", "0")

    def parse_callback(self, payload: dict[str, object]) -> CallbackEvent:
        receipt = str(payload["receipt"])
        return CallbackEvent(
            f"{self.request_ref}:0",
            self.request_ref,
            "succeeded",
            False,
            {"ResultCode": "0", "Amount": str(payload["amount"]), "MpesaReceiptNumber": receipt},
            Decimal(str(payload["amount"])),
            receipt,
            None,
        )

    async def query_status(self, provider_request_ref: str) -> ProviderStatus:
        return ProviderStatus(
            provider_request_ref, "succeeded", None, "KES", None, None, None, "0", "Processed"
        )

    async def reverse(self, transaction_ref: str, amount: Decimal, reason: str) -> ReversalResult:
        return ReversalResult("AG_TEST", True)


def settings() -> Settings:
    assert TEST_DATABASE_URL is not None
    return Settings(
        environment="test",
        database_url=SecretStr(TEST_DATABASE_URL),
        payments_enabled=True,
        daraja_consumer_key=SecretStr("key"),
        daraja_consumer_secret=SecretStr("secret"),
        daraja_shortcode="174379",
        daraja_passkey=SecretStr("passkey"),
        daraja_callback_base_url="https://api.example.test",
        daraja_callback_token=SecretStr(TOKEN),
    )


class World:
    def __init__(self) -> None:
        self.buyer = AuthenticatedUser(uuid4(), None, None, frozenset({"buyer"}), 0)
        self.farmers = [
            AuthenticatedUser(uuid4(), None, None, frozenset({"farmer"}), 0) for _ in range(2)
        ]
        self.category_id = uuid4()
        self.product_id = uuid4()
        self.listings = [uuid4(), uuid4()]


async def seed(database: Database) -> World:
    world = World()
    async with database.session() as session:
        for user in (world.buyer, *world.farmers):
            session.add(
                User(
                    id=user.id, email=f"{user.id}@example.test", password_hash="x", status="active"
                )
            )
        await session.flush()
        session.add(
            Profile(user_id=world.farmers[0].id, display_name="Wanjiru Kamau", bio="Limuru farm")
        )
        session.add(
            FarmerProfile(
                user_id=world.farmers[0].id,
                farm_name="Kamau Greens",
                county="Kiambu",
                locality="Limuru",
                offers_delivery=True,
            )
        )
        session.add(ProduceCategory(id=world.category_id, name="Veg", slug=f"veg-{uuid4()}"))
        await session.flush()
        session.add(
            Product(
                id=world.product_id,
                category_id=world.category_id,
                name="Kale",
                slug=f"kale-{uuid4()}",
                default_unit="bunch",
            )
        )
        await session.flush()
        for listing_id, farmer in zip(world.listings, world.farmers, strict=True):
            session.add(
                Listing(
                    id=listing_id,
                    farmer_id=farmer.id,
                    product_id=world.product_id,
                    title="Kale",
                    price_amount=Decimal("50"),
                    currency="KES",
                    available_quantity=Decimal("3"),
                    quantity_unit="bunch",
                    status="active",
                    version=1,
                )
            )
        await session.commit()
    return world


async def cleanup(database: Database, world: World) -> None:
    async with database.session() as session:
        orders = list(
            await session.scalars(select(Order.id).where(Order.buyer_id == world.buyer.id))
        )
        payments = list(
            await session.scalars(select(Payment.id).where(Payment.order_id.in_(orders)))
        )
        parts = list(
            await session.scalars(select(Fulfilment.id).where(Fulfilment.order_id.in_(orders)))
        )
        await session.execute(delete(OutboxJob))
        await session.execute(delete(PaymentRefund).where(PaymentRefund.order_id.in_(orders)))
        for model in (PaymentEvent, PaymentReconciliation):
            await session.execute(delete(model).where(model.payment_id.in_(payments)))
        await session.execute(delete(Payment).where(Payment.id.in_(payments)))
        await session.execute(
            delete(FulfilmentStatusHistory).where(FulfilmentStatusHistory.fulfilment_id.in_(parts))
        )
        await session.execute(delete(Fulfilment).where(Fulfilment.id.in_(parts)))
        await session.execute(
            delete(OrderStatusHistory).where(OrderStatusHistory.order_id.in_(orders))
        )
        await session.execute(delete(OrderItem).where(OrderItem.order_id.in_(orders)))
        await session.execute(
            delete(InventoryMovement).where(InventoryMovement.listing_id.in_(world.listings))
        )
        await session.execute(delete(Order).where(Order.id.in_(orders)))
        carts = list(await session.scalars(select(Cart.id).where(Cart.buyer_id == world.buyer.id)))
        await session.execute(delete(CartItem).where(CartItem.cart_id.in_(carts)))
        await session.execute(delete(Cart).where(Cart.id.in_(carts)))
        await session.execute(
            delete(ListingImage).where(ListingImage.listing_id.in_(world.listings))
        )
        await session.execute(delete(Listing).where(Listing.id.in_(world.listings)))
        await session.execute(delete(Product).where(Product.id == world.product_id))
        await session.execute(
            delete(ProduceCategory).where(ProduceCategory.id == world.category_id)
        )
        ids = [world.buyer.id, *(farmer.id for farmer in world.farmers)]
        await session.execute(delete(FarmerProfile).where(FarmerProfile.user_id.in_(ids)))
        await session.execute(delete(Profile).where(Profile.user_id.in_(ids)))
        await session.execute(delete(User).where(User.id.in_(ids)))
        await session.commit()


async def checkout(database: Database, world: World, quantities: tuple[str, str]) -> UUID:
    async with database.session() as session:
        carts = CartService(CommerceRepository(session))
        for listing_id, quantity in zip(world.listings, quantities, strict=True):
            if Decimal(quantity) > 0:
                await carts.upsert(world.buyer, listing_id, Decimal(quantity))
    async with database.session() as session:
        order = await CheckoutService(CommerceRepository(session), settings()).checkout(
            world.buyer, f"checkout-{uuid4()}", None
        )
    return order.id


async def start_payment(
    database: Database, world: World, order_id: UUID, provider: SandboxLikeProvider
) -> UUID:
    async with database.session() as session:
        payment = await PaymentService(CommerceRepository(session), settings(), provider).initiate(
            world.buyer,
            PaymentInitiateRequest(order_id=order_id, rail="mpesa", phone_e164="0712345678"),
            f"pay-{uuid4()}",
        )
    return payment.id


async def approve(
    database: Database, payment_id: UUID, provider: SandboxLikeProvider, receipt: str
) -> None:
    """Safaricom calls back, then the worker's status query confirms the payment."""
    async with database.session() as session:
        payment = await session.get(Payment, payment_id)
        assert payment is not None
        amount = str(payment.amount)
    async with database.session() as session:
        await PaymentService(CommerceRepository(session), settings(), provider).accept_callback(
            TOKEN, {"receipt": receipt, "amount": amount}
        )
    async with database.session() as session:
        await PaymentService(CommerceRepository(session), settings(), provider).reconcile(
            payment_id
        )


async def lapse(database: Database, order_id: UUID, payment_id: UUID) -> None:
    """Let the reservation run out while the buyer's prompt is long abandoned."""
    async with database.session() as session:
        order = await session.get(Order, order_id)
        payment = await session.get(Payment, payment_id)
        assert order is not None and payment is not None
        order.reservation_expires_at = _now() - timedelta(seconds=1)
        payment.created_at = _now() - timedelta(minutes=20)
        await session.commit()
    async with database.session() as session:
        await CheckoutService(CommerceRepository(session), settings()).expire(order_id)


async def available(database: Database, listing_id: UUID) -> Decimal:
    async with database.session() as session:
        listing = await session.get(Listing, listing_id)
        assert listing is not None
        return listing.available_quantity


@pytest.mark.anyio
async def test_approved_payment_completes_a_mixed_order_farmer_by_farmer() -> None:
    database = Database(settings())
    world = await seed(database)
    try:
        order_id = await checkout(database, world, ("2", "1"))
        provider = SandboxLikeProvider()
        payment_id = await start_payment(database, world, order_id, provider)
        await approve(database, payment_id, provider, "NLJ7RT61SV")
        async with database.session() as session:
            order = await session.get(Order, order_id)
            payment = await session.get(Payment, payment_id)
            assert order is not None and order.status == "paid"
            assert payment is not None and payment.state == "succeeded"
            assert payment.provider_transaction_ref == "NLJ7RT61SV"

        first, second = world.farmers
        async with database.session() as session:
            service = FulfilmentService(
                FulfilmentRepository(session), CommerceRepository(session), settings()
            )
            await service.update(
                world.buyer,
                order_id,
                FulfilmentUpdate(
                    method="pickup",
                    location_label="Farm gate",
                    location_details="Limuru market road",
                    window_start=_now() + timedelta(hours=1),
                    window_end=_now() + timedelta(hours=3),
                ),
            )
            parts = await service.parts(world.buyer, order_id)
            assert {part.farmer_id for part in parts} == {first.id, second.id}
            assert [part.farmer_id for part in await service.parts(first, order_id)] == [first.id]

        async with database.session() as session:
            service = FulfilmentService(
                FulfilmentRepository(session), CommerceRepository(session), settings()
            )
            await service.transition(
                first, order_id, FulfilmentTransition(status="scheduled", expected_version=1)
            )
            with pytest.raises(ApiError) as foreign:
                await service.transition(
                    first,
                    order_id,
                    FulfilmentTransition(status="scheduled", expected_version=1),
                    second.id,
                )
            assert foreign.value.code == "fulfilment_forbidden"
            # The second farmer can no longer supply; their stock and share of money go back.
            await service.transition(
                second,
                order_id,
                FulfilmentTransition(status="cancelled", expected_version=1, reason="Hail"),
            )
        assert await available(database, world.listings[1]) == Decimal("3")

        async with database.session() as session:
            service = FulfilmentService(
                FulfilmentRepository(session), CommerceRepository(session), settings()
            )
            await service.transition(
                first,
                order_id,
                FulfilmentTransition(status="ready_for_handover", expected_version=2),
            )
            order = await session.get(Order, order_id)
            assert order is not None and order.status == "fulfilment"
            await service.transition(
                world.buyer,
                order_id,
                FulfilmentTransition(status="completed", expected_version=3),
                first.id,
            )
        async with database.session() as session:
            order = await session.get(Order, order_id)
            assert order is not None and order.status == "completed"
            refunds = list(
                await session.scalars(
                    select(PaymentRefund).where(PaymentRefund.order_id == order_id)
                )
            )
            assert [(refund.amount, refund.farmer_id) for refund in refunds] == [
                (Decimal("50.0000"), second.id)
            ]
            assert refunds[0].state == "manual_required"

        async with database.session() as session:
            catalog = CatalogService(CatalogRepository(session))
            page = await catalog.list_listings(
                search=None,
                category_slug=None,
                farmer_id=first.id,
                unit=None,
                min_price=None,
                max_price=None,
                sort="newest",
                cursor_raw=None,
                limit=10,
            )
            assert page.items[0].farmer is not None
            assert page.items[0].farmer.display_name == "Wanjiru Kamau"
            assert page.items[0].farmer.completed_orders == 1
            profile = await catalog.farmer_profile(first.id)
            assert profile.locality == "Limuru" and profile.offers_delivery is True
            photo = await catalog.add_photo(
                first,
                world.listings[0],
                PhotoUpload(
                    content_type="image/jpeg",
                    content_base64=base64.b64encode(b"\xff\xd8\xff" + b"1" * 32).decode(),
                ),
            )
            assert (await catalog.photo(photo.id)).byte_size == 35
    finally:
        await cleanup(database, world)
        await database.dispose()


@pytest.mark.anyio
async def test_late_payment_reserves_again_or_is_refunded() -> None:
    database = Database(settings())
    world = await seed(database)
    try:
        order_id = await checkout(database, world, ("3", "0"))
        provider = SandboxLikeProvider()
        payment_id = await start_payment(database, world, order_id, provider)
        await lapse(database, order_id, payment_id)
        assert await available(database, world.listings[0]) == Decimal("3")

        # The stock is still there, so the late payment takes it back.
        await approve(database, payment_id, provider, "LATE000001")
        assert await available(database, world.listings[0]) == Decimal("0")
        async with database.session() as session:
            order = await session.get(Order, order_id)
            assert order is not None and order.status == "paid"

        # A lapsed order whose stock was sold meanwhile is refunded instead of oversold.
        second_order = await checkout(database, world, ("0", "3"))
        provider = SandboxLikeProvider()
        second_payment = await start_payment(database, world, second_order, provider)
        await lapse(database, second_order, second_payment)
        async with database.session() as session:
            listing = await session.get(Listing, world.listings[1])
            assert listing is not None
            listing.available_quantity = Decimal("1")
            await session.commit()
        await approve(database, second_payment, provider, "LATE000002")
        assert await available(database, world.listings[1]) == Decimal("1")
        async with database.session() as session:
            order = await session.get(Order, second_order)
            assert order is not None and order.status == "expired"
            refund = await session.scalar(
                select(PaymentRefund).where(PaymentRefund.payment_id == second_payment)
            )
            assert refund is not None and refund.reason == "late_payment_stock_unavailable"
            assert refund.state == "pending"
    finally:
        await cleanup(database, world)
        await database.dispose()
