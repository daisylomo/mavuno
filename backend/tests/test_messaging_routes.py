from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from mavuno.api.v1 import messaging
from mavuno.auth.context import AuthenticatedUser
from mavuno.messaging.schemas import (
    ConversationCreate,
    MarkReadRequest,
    MessageCreate,
    NotificationPreferencesUpdate,
)


@pytest.mark.anyio
async def test_messaging_routes_delegate(monkeypatch: pytest.MonkeyPatch) -> None:
    actor = AuthenticatedUser(uuid4(), None, None, frozenset({"buyer"}), 0)
    conversation_id, message_id, notification_id = uuid4(), uuid4(), uuid4()
    service = MagicMock()
    service.create_conversation = AsyncMock(return_value="conversation")
    service.list_conversations = AsyncMock(return_value=[])
    service.send = AsyncMock(return_value="message")
    service.messages = AsyncMock(return_value="page")
    service.mark_read = AsyncMock()
    notifications = MagicMock()
    notifications.preferences = AsyncMock(return_value="preferences")
    notifications.update_preferences = AsyncMock(return_value="updated")
    notifications.list = AsyncMock(return_value=[])
    notifications.mark_read = AsyncMock(return_value="notification")
    monkeypatch.setattr(messaging, "MessagingService", lambda *_args: service)
    monkeypatch.setattr(messaging, "NotificationService", lambda *_args: notifications)
    session = MagicMock()
    payload = ConversationCreate(scope_type="listing", scope_id=uuid4())
    assert await messaging.create_conversation(payload, actor, session) == "conversation"
    assert await messaging.list_conversations(actor, session) == []
    message = MessageCreate(client_message_id=uuid4(), body="hello")
    assert await messaging.send_message(conversation_id, message, actor, session) == "message"
    assert await messaging.list_messages(conversation_id, actor, session, None, 20) == "page"
    response = await messaging.mark_conversation_read(
        conversation_id, MarkReadRequest(last_read_message_id=message_id), actor, session
    )
    assert response.status_code == 204
    assert await messaging.get_notification_preferences(actor, session) == "preferences"
    preference = NotificationPreferencesUpdate(messages_push=False, orders_push=True)
    assert await messaging.update_notification_preferences(preference, actor, session) == "updated"
    assert await messaging.list_notifications(actor, session) == []
    assert await messaging.mark_notification_read(notification_id, actor, session) == "notification"
