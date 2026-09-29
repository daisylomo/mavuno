from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from mavuno.api.dependencies import CurrentUser, DatabaseSession
from mavuno.messaging.repository import MessagingRepository
from mavuno.messaging.schemas import (
    ConversationCreate,
    ConversationResponse,
    MarkReadRequest,
    MessageCreate,
    MessagePage,
    MessageResponse,
    NotificationPreferencesResponse,
    NotificationPreferencesUpdate,
    NotificationResponse,
)
from mavuno.messaging.service import MessagingService, NotificationService

router = APIRouter(tags=["messaging"])


@router.post("/conversations", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    payload: ConversationCreate, current_user: CurrentUser, session: DatabaseSession
) -> object:
    return await MessagingService(MessagingRepository(session)).create_conversation(
        current_user, payload
    )


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(current_user: CurrentUser, session: DatabaseSession) -> object:
    return await MessagingService(MessagingRepository(session)).list_conversations(current_user)


@router.post(
    "/conversations/{conversation_id}/messages", response_model=MessageResponse, status_code=201
)
async def send_message(
    conversation_id: UUID,
    payload: MessageCreate,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> object:
    return await MessagingService(MessagingRepository(session)).send(
        current_user, conversation_id, payload.client_message_id, payload.body
    )


@router.get("/conversations/{conversation_id}/messages", response_model=MessagePage)
async def list_messages(
    conversation_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> object:
    return await MessagingService(MessagingRepository(session)).messages(
        current_user, conversation_id, cursor, limit
    )


@router.put("/conversations/{conversation_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_conversation_read(
    conversation_id: UUID,
    payload: MarkReadRequest,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> Response:
    await MessagingService(MessagingRepository(session)).mark_read(
        current_user, conversation_id, payload.last_read_message_id
    )
    return Response(status_code=204)


@router.get("/notification-preferences", response_model=NotificationPreferencesResponse)
async def get_notification_preferences(
    current_user: CurrentUser, session: DatabaseSession
) -> object:
    return await NotificationService(MessagingRepository(session)).preferences(current_user)


@router.put("/notification-preferences", response_model=NotificationPreferencesResponse)
async def update_notification_preferences(
    payload: NotificationPreferencesUpdate, current_user: CurrentUser, session: DatabaseSession
) -> object:
    return await NotificationService(MessagingRepository(session)).update_preferences(
        current_user, payload
    )


@router.get("/notifications", response_model=list[NotificationResponse])
async def list_notifications(current_user: CurrentUser, session: DatabaseSession) -> object:
    return await NotificationService(MessagingRepository(session)).list(current_user)


@router.put("/notifications/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: UUID, current_user: CurrentUser, session: DatabaseSession
) -> object:
    return await NotificationService(MessagingRepository(session)).mark_read(
        current_user, notification_id
    )
