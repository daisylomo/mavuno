from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mavuno.db.models import (
    Listing,
    Order,
    OrderItem,
    Plan,
    Prebooking,
    Product,
    Subscription,
    UserRole,
)


class PremiumRepository:
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

    async def plans(self) -> list[Plan]:
        return list(await self.session.scalars(select(Plan).where(Plan.active.is_(True))))

    async def plan(self, plan_id: UUID) -> Plan | None:
        return await self.session.get(Plan, plan_id)

    async def subscription(
        self, subscription_id: UUID, *, lock: bool = False
    ) -> Subscription | None:
        query = select(Subscription).where(Subscription.id == subscription_id)
        if lock:
            query = query.with_for_update()
        return cast(Subscription | None, await self.session.scalar(query))

    async def subscription_by_idempotency(
        self, user_id: UUID, idempotency_key: str
    ) -> Subscription | None:
        return cast(
            Subscription | None,
            await self.session.scalar(
                select(Subscription).where(
                    Subscription.user_id == user_id,
                    Subscription.idempotency_key == idempotency_key,
                )
            ),
        )

    async def subscription_by_reference(self, account_reference: str) -> Subscription | None:
        return cast(
            Subscription | None,
            await self.session.scalar(
                select(Subscription).where(Subscription.account_reference == account_reference)
            ),
        )

    async def subscriptions(self, user_id: UUID) -> list[Subscription]:
        return list(
            await self.session.scalars(
                select(Subscription)
                .where(Subscription.user_id == user_id)
                .order_by(Subscription.created_at.desc())
            )
        )

    async def entitlement(self, user_id: UUID, feature: str, now: datetime) -> bool:
        values = await self.session.execute(
            select(Subscription, Plan)
            .join(Plan, Plan.id == Subscription.plan_id)
            .where(
                Subscription.user_id == user_id,
                Subscription.status == "active",
                Subscription.verified_at.is_not(None),
                Subscription.current_period_end > now,
                Plan.active.is_(True),
            )
        )
        return any(feature in plan.features for _, plan in values)

    async def listing(self, listing_id: UUID) -> Listing | None:
        return await self.session.get(Listing, listing_id)

    async def product(self, product_id: UUID) -> Product | None:
        return await self.session.get(Product, product_id)

    async def user_has_role(self, user_id: UUID, role_name: str) -> bool:
        return (
            await self.session.scalar(
                select(UserRole.user_id)
                .where(UserRole.user_id == user_id, UserRole.role_name == role_name)
                .limit(1)
            )
            is not None
        )

    async def prebooking(self, prebooking_id: UUID, *, lock: bool = False) -> Prebooking | None:
        query = select(Prebooking).where(Prebooking.id == prebooking_id)
        if lock:
            query = query.with_for_update()
        return cast(Prebooking | None, await self.session.scalar(query))

    async def prebookings(self, user_id: UUID) -> list[Prebooking]:
        return list(
            await self.session.scalars(
                select(Prebooking)
                .where(or_(Prebooking.buyer_id == user_id, Prebooking.farmer_id == user_id))
                .order_by(Prebooking.created_at.desc())
            )
        )

    async def farmer_insights(self, farmer_id: UUID) -> tuple[int, Decimal, int, Decimal]:
        listing_row = (
            await self.session.execute(
                select(
                    func.count(Listing.id), func.coalesce(func.sum(Listing.available_quantity), 0)
                ).where(Listing.farmer_id == farmer_id, Listing.status.in_(("active", "sold_out")))
            )
        ).one()
        sales_row = (
            await self.session.execute(
                select(func.count(OrderItem.id), func.coalesce(func.sum(OrderItem.line_total), 0))
                .join(Order, Order.id == OrderItem.order_id)
                .where(OrderItem.farmer_id == farmer_id, Order.status == "completed")
            )
        ).one()
        return (
            int(listing_row[0]),
            Decimal(listing_row[1]),
            int(sales_row[0]),
            Decimal(sales_row[1]),
        )
