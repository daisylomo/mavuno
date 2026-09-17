from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mavuno.db.models import Fulfilment, FulfilmentStatusHistory, Order, OrderItem


class FulfilmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, value: Any) -> None:
        self.session.add(value)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def refresh(self, value: Any) -> None:
        await self.session.refresh(value)

    async def order(self, order_id: UUID, *, lock: bool = False) -> Order | None:
        query = select(Order).where(Order.id == order_id)
        if lock:
            query = query.with_for_update()
        return cast(Order | None, await self.session.scalar(query))

    async def farmer_ids(self, order_id: UUID) -> set[UUID]:
        return set(
            await self.session.scalars(
                select(OrderItem.farmer_id).where(OrderItem.order_id == order_id).distinct()
            )
        )

    async def fulfilment(self, order_id: UUID, *, lock: bool = False) -> Fulfilment | None:
        query = select(Fulfilment).where(Fulfilment.order_id == order_id)
        if lock:
            query = query.with_for_update()
        return cast(Fulfilment | None, await self.session.scalar(query))

    async def history(self, fulfilment_id: UUID) -> list[FulfilmentStatusHistory]:
        return list(
            await self.session.scalars(
                select(FulfilmentStatusHistory)
                .where(FulfilmentStatusHistory.fulfilment_id == fulfilment_id)
                .order_by(FulfilmentStatusHistory.created_at, FulfilmentStatusHistory.id)
            )
        )
