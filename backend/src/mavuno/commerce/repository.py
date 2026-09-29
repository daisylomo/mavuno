from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mavuno.db.models import (
    Address,
    Cart,
    CartItem,
    Fulfilment,
    Listing,
    Order,
    OrderItem,
    OutboxJob,
    Payment,
    PaymentEvent,
    PaymentRefund,
    Product,
    Profile,
    User,
)

IN_FLIGHT_PAYMENT_STATES = ("created", "pending_customer", "processing")


class CommerceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, value: Any) -> None:
        self.session.add(value)

    async def flush(self) -> None:
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def refresh(self, value: Any) -> None:
        await self.session.refresh(value)

    async def active_cart(self, buyer_id: UUID, *, lock: bool = False) -> Cart | None:
        query = select(Cart).where(Cart.buyer_id == buyer_id, Cart.status == "active")
        if lock:
            query = query.with_for_update()
        return cast(Cart | None, await self.session.scalar(query))

    async def lock_user(self, user_id: UUID) -> None:
        await self.session.execute(select(User.id).where(User.id == user_id).with_for_update())

    async def cart_items(self, cart_id: UUID) -> list[CartItem]:
        return list(await self.session.scalars(select(CartItem).where(CartItem.cart_id == cart_id)))

    async def cart_item(self, cart_id: UUID, listing_id: UUID) -> CartItem | None:
        return cast(
            CartItem | None,
            await self.session.scalar(
                select(CartItem).where(
                    CartItem.cart_id == cart_id, CartItem.listing_id == listing_id
                )
            ),
        )

    async def listing(self, listing_id: UUID, *, lock: bool = False) -> Listing | None:
        query = select(Listing).where(Listing.id == listing_id)
        if lock:
            query = query.with_for_update()
        return cast(Listing | None, await self.session.scalar(query))

    async def product(self, product_id: UUID) -> Product | None:
        return await self.session.get(Product, product_id)

    async def address(self, address_id: UUID, user_id: UUID) -> Address | None:
        return cast(
            Address | None,
            await self.session.scalar(
                select(Address).where(Address.id == address_id, Address.user_id == user_id)
            ),
        )

    async def delete_cart_item(self, value: CartItem) -> None:
        await self.session.delete(value)

    async def existing_order(self, buyer_id: UUID, idempotency_key: str) -> Order | None:
        return cast(
            Order | None,
            await self.session.scalar(
                select(Order).where(
                    Order.buyer_id == buyer_id, Order.idempotency_key == idempotency_key
                )
            ),
        )

    async def order(self, order_id: UUID, *, lock: bool = False) -> Order | None:
        query = select(Order).where(Order.id == order_id)
        if lock:
            query = query.with_for_update()
        return cast(Order | None, await self.session.scalar(query))

    async def buyer_orders(self, buyer_id: UUID) -> list[Order]:
        return list(
            await self.session.scalars(
                select(Order)
                .where(Order.buyer_id == buyer_id)
                .order_by(Order.created_at.desc(), Order.id.desc())
                .limit(50)
            )
        )

    async def farmer_order_rows(self, farmer_id: UUID) -> list[Any]:
        return list(
            (
                await self.session.execute(
                    select(Order, OrderItem, User, Profile, Address)
                    .join(OrderItem, OrderItem.order_id == Order.id)
                    .join(User, User.id == Order.buyer_id)
                    .outerjoin(Profile, Profile.user_id == User.id)
                    .outerjoin(Address, Address.id == Order.delivery_address_id)
                    .where(
                        OrderItem.farmer_id == farmer_id,
                        Order.status.in_(
                            ("pending_payment", "paid", "fulfilment", "completed", "cancelled")
                        ),
                    )
                    .order_by(Order.created_at.desc(), Order.id.desc())
                    .limit(100)
                )
            ).all()
        )

    async def order_payments(self, order_id: UUID) -> list[Payment]:
        return list(
            await self.session.scalars(
                select(Payment)
                .where(Payment.order_id == order_id)
                .order_by(Payment.created_at.desc(), Payment.id.desc())
            )
        )

    async def paid_order_phone(self, order_id: UUID) -> str | None:
        return cast(
            str | None,
            await self.session.scalar(
                select(Payment.payer_phone_e164)
                .where(Payment.order_id == order_id, Payment.state == "succeeded")
                .order_by(Payment.created_at.desc())
                .limit(1)
            ),
        )

    async def order_items(self, order_id: UUID) -> list[OrderItem]:
        return list(
            await self.session.scalars(select(OrderItem).where(OrderItem.order_id == order_id))
        )

    async def existing_payment(self, order_id: UUID, idempotency_key: str) -> Payment | None:
        return cast(
            Payment | None,
            await self.session.scalar(
                select(Payment).where(
                    Payment.order_id == order_id, Payment.idempotency_key == idempotency_key
                )
            ),
        )

    async def payment(self, payment_id: UUID, *, lock: bool = False) -> Payment | None:
        query = select(Payment).where(Payment.id == payment_id)
        if lock:
            query = query.with_for_update()
        return cast(Payment | None, await self.session.scalar(query))

    async def payment_by_request_ref(self, provider: str, request_ref: str) -> Payment | None:
        return cast(
            Payment | None,
            await self.session.scalar(
                select(Payment).where(
                    Payment.provider == provider, Payment.provider_request_ref == request_ref
                )
            ),
        )

    async def claim_jobs(
        self, now: datetime, lease_until: datetime, limit: int = 10
    ) -> list[OutboxJob]:
        jobs = list(
            await self.session.scalars(
                select(OutboxJob)
                .where(
                    OutboxJob.status.in_(("pending", "retry")),
                    OutboxJob.available_at <= now,
                    or_(OutboxJob.leased_until.is_(None), OutboxJob.leased_until < now),
                )
                .order_by(OutboxJob.available_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for job in jobs:
            job.status = "processing"
            job.leased_until = lease_until
            job.attempts += 1
        await self.session.commit()
        return jobs

    async def success_callback(self, payment_id: UUID) -> PaymentEvent | None:
        """The latest successful STK callback, which carries the receipt and amount."""
        return cast(
            PaymentEvent | None,
            await self.session.scalar(
                select(PaymentEvent)
                .where(
                    PaymentEvent.payment_id == payment_id,
                    PaymentEvent.direction == "callback",
                    PaymentEvent.event_type == "succeeded",
                )
                .order_by(PaymentEvent.created_at.desc())
                .limit(1)
            ),
        )

    async def in_flight_payment(
        self, order_id: UUID, *, since: datetime, exclude: UUID | None = None
    ) -> Payment | None:
        """A prompt sent after ``since`` that the buyer may still be answering."""
        query = select(Payment).where(
            Payment.order_id == order_id,
            Payment.state.in_(IN_FLIGHT_PAYMENT_STATES),
            Payment.created_at >= since,
        )
        if exclude is not None:
            query = query.where(Payment.id != exclude)
        return cast(
            Payment | None,
            await self.session.scalar(query.order_by(Payment.created_at.desc()).limit(1)),
        )

    async def succeeded_payment(self, order_id: UUID) -> Payment | None:
        return cast(
            Payment | None,
            await self.session.scalar(
                select(Payment)
                .where(Payment.order_id == order_id, Payment.state == "succeeded")
                .order_by(Payment.created_at)
                .limit(1)
            ),
        )

    async def order_refunds(self, order_id: UUID) -> list[PaymentRefund]:
        return list(
            await self.session.scalars(
                select(PaymentRefund)
                .where(PaymentRefund.order_id == order_id)
                .order_by(PaymentRefund.created_at, PaymentRefund.id)
            )
        )

    async def refunded_total(self, payment_id: UUID) -> Decimal:
        value = await self.session.scalar(
            select(func.coalesce(func.sum(PaymentRefund.amount), 0)).where(
                PaymentRefund.payment_id == payment_id,
                PaymentRefund.state != "failed",
            )
        )
        return Decimal(str(value or 0))

    async def refund(self, refund_id: UUID, *, lock: bool = False) -> PaymentRefund | None:
        query = select(PaymentRefund).where(PaymentRefund.id == refund_id)
        if lock:
            query = query.with_for_update()
        return cast(PaymentRefund | None, await self.session.scalar(query))

    async def refund_by_provider_ref(self, provider_ref: str) -> PaymentRefund | None:
        return cast(
            PaymentRefund | None,
            await self.session.scalar(
                select(PaymentRefund).where(PaymentRefund.provider_ref == provider_ref)
            ),
        )

    async def refunds_by_state(self, states: tuple[str, ...]) -> list[PaymentRefund]:
        return list(
            await self.session.scalars(
                select(PaymentRefund)
                .where(PaymentRefund.state.in_(states))
                .order_by(PaymentRefund.created_at)
                .limit(200)
            )
        )

    async def order_fulfilments(self, order_id: UUID, *, lock: bool = False) -> list[Fulfilment]:
        query = select(Fulfilment).where(Fulfilment.order_id == order_id)
        if lock:
            query = query.with_for_update()
        return list(await self.session.scalars(query.order_by(Fulfilment.farmer_id)))
