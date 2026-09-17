from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mavuno.db.models import (
    Conversation,
    ConversationReadState,
    DeviceInstallation,
    Listing,
    Message,
    Notification,
    NotificationDelivery,
    NotificationPreference,
    Order,
    OrderItem,
    OutboxJob,
)


class MessagingRepository:
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

    async def conversation(self, conversation_id: UUID, user_id: UUID) -> Conversation | None:
        return cast(
            Conversation | None,
            await self.session.scalar(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    or_(Conversation.buyer_id == user_id, Conversation.farmer_id == user_id),
                )
            ),
        )

    async def existing_conversation(
        self, scope_type: str, scope_id: UUID, buyer_id: UUID, farmer_id: UUID
    ) -> Conversation | None:
        return cast(
            Conversation | None,
            await self.session.scalar(
                select(Conversation).where(
                    Conversation.scope_type == scope_type,
                    Conversation.scope_id == scope_id,
                    Conversation.buyer_id == buyer_id,
                    Conversation.farmer_id == farmer_id,
                )
            ),
        )

    async def conversations(self, user_id: UUID, limit: int = 50) -> list[Conversation]:
        return list(
            await self.session.scalars(
                select(Conversation)
                .where(or_(Conversation.buyer_id == user_id, Conversation.farmer_id == user_id))
                .order_by(Conversation.updated_at.desc())
                .limit(limit)
            )
        )

    async def listing(self, listing_id: UUID) -> Listing | None:
        return await self.session.get(Listing, listing_id)

    async def order(self, order_id: UUID) -> Order | None:
        return await self.session.get(Order, order_id)

    async def order_has_farmer(self, order_id: UUID, farmer_id: UUID) -> bool:
        return (
            await self.session.scalar(
                select(OrderItem.id)
                .where(OrderItem.order_id == order_id, OrderItem.farmer_id == farmer_id)
                .limit(1)
            )
            is not None
        )

    async def existing_message(
        self, conversation_id: UUID, sender_id: UUID, client_id: UUID
    ) -> Message | None:
        return cast(
            Message | None,
            await self.session.scalar(
                select(Message).where(
                    Message.conversation_id == conversation_id,
                    Message.sender_id == sender_id,
                    Message.client_message_id == client_id,
                )
            ),
        )

    async def messages(
        self, conversation_id: UUID, cursor: UUID | None, limit: int
    ) -> list[Message]:
        query = select(Message).where(Message.conversation_id == conversation_id)
        if cursor is not None:
            anchor = await self.session.get(Message, cursor)
            if anchor is not None and anchor.conversation_id == conversation_id:
                query = query.where(
                    or_(
                        Message.created_at > anchor.created_at,
                        and_(Message.created_at == anchor.created_at, Message.id > anchor.id),
                    )
                )
        return list(
            await self.session.scalars(
                query.order_by(Message.created_at, Message.id).limit(limit + 1)
            )
        )

    async def message(self, message_id: UUID, conversation_id: UUID) -> Message | None:
        return cast(
            Message | None,
            await self.session.scalar(
                select(Message).where(
                    Message.id == message_id, Message.conversation_id == conversation_id
                )
            ),
        )

    async def read_state(
        self, conversation_id: UUID, user_id: UUID
    ) -> ConversationReadState | None:
        return await self.session.get(ConversationReadState, (conversation_id, user_id))

    async def preferences(self, user_id: UUID) -> NotificationPreference | None:
        return await self.session.get(NotificationPreference, user_id)

    async def notifications(self, user_id: UUID, limit: int = 50) -> list[Notification]:
        return list(
            await self.session.scalars(
                select(Notification)
                .where(Notification.user_id == user_id)
                .order_by(Notification.created_at.desc())
                .limit(limit)
            )
        )

    async def notification(self, notification_id: UUID, user_id: UUID) -> Notification | None:
        return cast(
            Notification | None,
            await self.session.scalar(
                select(Notification).where(
                    Notification.id == notification_id, Notification.user_id == user_id
                )
            ),
        )

    async def active_devices(self, user_id: UUID) -> list[DeviceInstallation]:
        return list(
            await self.session.scalars(
                select(DeviceInstallation).where(
                    DeviceInstallation.user_id == user_id,
                    DeviceInstallation.revoked_at.is_(None),
                    DeviceInstallation.push_token_ciphertext.is_not(None),
                )
            )
        )

    async def delivery(self, notification_id: UUID, device_id: UUID) -> NotificationDelivery | None:
        return cast(
            NotificationDelivery | None,
            await self.session.scalar(
                select(NotificationDelivery).where(
                    NotificationDelivery.notification_id == notification_id,
                    NotificationDelivery.device_installation_id == device_id,
                )
            ),
        )

    async def outbox(self, dedupe_key: str) -> OutboxJob | None:
        return cast(
            OutboxJob | None,
            await self.session.scalar(select(OutboxJob).where(OutboxJob.dedupe_key == dedupe_key)),
        )

    async def now(self) -> datetime:
        from mavuno.commerce.service import _now

        return _now()
