from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mavuno.db.models import (
    Address,
    Cart,
    CartItem,
    Listing,
    Order,
    OrderItem,
    OutboxJob,
    Payment,
    Product,
    User,
)


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
