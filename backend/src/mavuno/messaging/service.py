from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import IntegrityError

from mavuno.api.errors import ApiError
from mavuno.auth.context import AuthenticatedUser
from mavuno.db.models import (
    Conversation,
    ConversationReadState,
    Message,
    Notification,
    NotificationDelivery,
    NotificationPreference,
    OutboxJob,
)
from mavuno.messaging.provider import PushPayload, PushProvider
from mavuno.messaging.repository import MessagingRepository
from mavuno.messaging.schemas import (
    ConversationCreate,
    MessagePage,
    NotificationPreferencesResponse,
    NotificationPreferencesUpdate,
)
from mavuno.profiles.push_tokens import PushTokenProtector


def not_found() -> ApiError:
    return ApiError(
        status_code=404, code="conversation_not_found", message="Conversation was not found"
    )


class MessagingService:
    def __init__(self, repository: MessagingRepository) -> None:
        self.repository = repository

    async def create_conversation(
        self, user: AuthenticatedUser, payload: ConversationCreate
    ) -> Conversation:
        if payload.scope_type == "listing":
            listing = await self.repository.listing(payload.scope_id)
            if (
                listing is None
                or not user.has_role("buyer")
                or listing.status not in {"active", "paused"}
                or listing.farmer_id == user.id
            ):
                raise ApiError(
                    status_code=404,
                    code="scope_not_found",
                    message="Conversation scope was not found",
                )
            buyer_id, farmer_id = user.id, listing.farmer_id
        else:
            order = await self.repository.order(payload.scope_id)
            if order is None:
                raise ApiError(
                    status_code=404,
                    code="scope_not_found",
                    message="Conversation scope was not found",
                )
            if order.buyer_id == user.id:
                if payload.farmer_id is None or not await self.repository.order_has_farmer(
                    order.id, payload.farmer_id
                ):
                    raise ApiError(
                        status_code=422,
                        code="invalid_farmer",
                        message="Select a farmer from this order",
                    )
                buyer_id, farmer_id = user.id, payload.farmer_id
            elif await self.repository.order_has_farmer(order.id, user.id):
                buyer_id, farmer_id = order.buyer_id, user.id
            else:
                raise ApiError(
                    status_code=404,
                    code="scope_not_found",
                    message="Conversation scope was not found",
                )
        existing = await self.repository.existing_conversation(
            payload.scope_type, payload.scope_id, buyer_id, farmer_id
        )
        if existing is not None:
            return existing
        value = Conversation(
            scope_type=payload.scope_type,
            scope_id=payload.scope_id,
            buyer_id=buyer_id,
            farmer_id=farmer_id,
        )
        self.repository.add(value)
        try:
            await self.repository.commit()
        except IntegrityError:
            await self.repository.rollback()
            winner = await self.repository.existing_conversation(
                payload.scope_type, payload.scope_id, buyer_id, farmer_id
            )
            if winner is None:
                raise
            return winner
        await self.repository.refresh(value)
        return value

    async def list_conversations(self, user: AuthenticatedUser) -> list[Conversation]:
        return await self.repository.conversations(user.id)

    async def send(
        self, user: AuthenticatedUser, conversation_id: UUID, client_id: UUID, body: str
    ) -> Message:
        conversation = await self.repository.conversation(conversation_id, user.id)
        if conversation is None:
            raise not_found()
        existing = await self.repository.existing_message(conversation_id, user.id, client_id)
        if existing is not None:
            return existing
        normalized_body = body.strip()
        if not normalized_body:
            raise ApiError(
                status_code=422, code="empty_message", message="Message body cannot be empty"
            )
        now = await self.repository.now()
        message = Message(
            conversation_id=conversation_id,
            sender_id=user.id,
            client_message_id=client_id,
            body=normalized_body,
            created_at=now,
        )
        self.repository.add(message)
        try:
            await self.repository.flush()
        except IntegrityError:
            await self.repository.rollback()
            winner = await self.repository.existing_message(conversation_id, user.id, client_id)
            if winner is None:
                raise
            return winner
        conversation.last_message_at = now
        recipient_id = (
            conversation.farmer_id if user.id == conversation.buyer_id else conversation.buyer_id
        )
        notification = Notification(
            user_id=recipient_id,
            kind="message_received",
            title="New message",
            body=normalized_body[:160],
            data={"conversation_id": str(conversation.id), "message_id": str(message.id)},
            dedupe_key=f"message:{message.id}",
            created_at=now,
        )
        self.repository.add(notification)
        await self.repository.flush()
        self.repository.add(
            OutboxJob(
                job_type="notification_push",
                dedupe_key=f"notification:{notification.id}",
                payload={"notification_id": str(notification.id)},
                status="pending",
                attempts=0,
                max_attempts=8,
                available_at=now,
            )
        )
        try:
            await self.repository.commit()
        except IntegrityError:
            await self.repository.rollback()
            winner = await self.repository.existing_message(conversation_id, user.id, client_id)
            if winner is None:
                raise
            return winner
        return message

    async def messages(
        self, user: AuthenticatedUser, conversation_id: UUID, cursor: UUID | None, limit: int
    ) -> MessagePage:
        if await self.repository.conversation(conversation_id, user.id) is None:
            raise not_found()
        values = await self.repository.messages(conversation_id, cursor, limit)
        more = len(values) > limit
        items = values[:limit]
        return MessagePage(items=items, next_cursor=items[-1].id if more and items else None)

    async def mark_read(
        self, user: AuthenticatedUser, conversation_id: UUID, message_id: UUID
    ) -> ConversationReadState:
        if await self.repository.conversation(conversation_id, user.id) is None:
            raise not_found()
        message = await self.repository.message(message_id, conversation_id)
        if message is None:
            raise ApiError(
                status_code=422,
                code="invalid_read_marker",
                message="Read marker must belong to the conversation",
            )
        state = await self.repository.read_state(conversation_id, user.id)
        if state is None:
            state = ConversationReadState(
                conversation_id=conversation_id,
                user_id=user.id,
                last_read_message_id=message.id,
                read_at=message.created_at,
            )
            self.repository.add(state)
        elif message.created_at >= state.read_at:
            state.last_read_message_id = message.id
            state.read_at = message.created_at
        await self.repository.commit()
        return state


class NotificationService:
    def __init__(self, repository: MessagingRepository) -> None:
        self.repository = repository

    async def preferences(self, user: AuthenticatedUser) -> NotificationPreferencesResponse:
        value = await self.repository.preferences(user.id)
        return NotificationPreferencesResponse(
            messages_push=True if value is None else value.messages_push,
            orders_push=True if value is None else value.orders_push,
        )

    async def update_preferences(
        self, user: AuthenticatedUser, payload: NotificationPreferencesUpdate
    ) -> NotificationPreferencesResponse:
        value = await self.repository.preferences(user.id)
        if value is None:
            value = NotificationPreference(
                user_id=user.id,
                messages_push=payload.messages_push,
                orders_push=payload.orders_push,
            )
            self.repository.add(value)
        else:
            value.messages_push, value.orders_push = payload.messages_push, payload.orders_push
        await self.repository.commit()
        return NotificationPreferencesResponse(
            messages_push=value.messages_push, orders_push=value.orders_push
        )

    async def list(self, user: AuthenticatedUser) -> list[Notification]:
        return await self.repository.notifications(user.id)

    async def mark_read(self, user: AuthenticatedUser, notification_id: UUID) -> Notification:
        value = await self.repository.notification(notification_id, user.id)
        if value is None:
            raise ApiError(
                status_code=404, code="notification_not_found", message="Notification was not found"
            )
        value.read_at = await self.repository.now()
        await self.repository.commit()
        return value


class NotificationDeliveryService:
    def __init__(
        self, repository: MessagingRepository, provider: PushProvider, protector: PushTokenProtector
    ) -> None:
        self.repository, self.provider, self.protector = repository, provider, protector

    async def deliver(self, notification_id: UUID) -> None:
        notification = await self.repository.session.get(Notification, notification_id)
        if notification is None:
            return
        preference = await self.repository.preferences(notification.user_id)
        if (
            preference is not None
            and notification.kind == "message_received"
            and not preference.messages_push
        ):
            return
        devices = await self.repository.active_devices(notification.user_id)
        for device in devices:
            delivery = await self.repository.delivery(notification.id, device.id)
            if delivery is not None and delivery.status == "delivered":
                continue
            if delivery is None:
                delivery = NotificationDelivery(
                    notification_id=notification.id,
                    device_installation_id=device.id,
                    status="pending",
                    attempts=0,
                )
                self.repository.add(delivery)
                await self.repository.flush()
            if device.push_token_ciphertext is None:
                continue
            delivery.attempts += 1
            provider_id = await self.provider.send(
                self.protector.decrypt(device.push_token_ciphertext),
                PushPayload(notification.title, notification.body, notification.data),
                f"{notification.id}:{device.id}",
            )
            delivery.provider_message_id, delivery.status = provider_id, "delivered"
            delivery.delivered_at = await self.repository.now()
        await self.repository.commit()
