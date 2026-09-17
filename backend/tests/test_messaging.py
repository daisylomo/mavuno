from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import httpx2 as httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from mavuno.api.errors import ApiError
from mavuno.auth.context import AuthenticatedUser
from mavuno.db.models import Conversation, Message, Notification, NotificationPreference
from mavuno.messaging.provider import (
    HttpPushProvider,
    PushPayload,
    PushProviderError,
    UnconfiguredPushProvider,
)
from mavuno.messaging.schemas import ConversationCreate, NotificationPreferencesUpdate
from mavuno.messaging.service import (
    MessagingService,
    NotificationDeliveryService,
    NotificationService,
)
from mavuno.profiles.push_tokens import PushTokenProtector


def user(user_id: UUID | None = None) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=user_id or uuid4(),
        email=None,
        phone_e164=None,
        roles=frozenset({"buyer"}),
        token_version=0,
    )


def repository() -> MagicMock:
    value = MagicMock()
    value.add = MagicMock()
    value.flush = AsyncMock()
    value.commit = AsyncMock()
    value.rollback = AsyncMock()
    value.refresh = AsyncMock()
    value.now = AsyncMock(return_value=datetime.now(UTC).replace(tzinfo=None))
    return value


@pytest.mark.anyio
async def test_listing_conversation_creation_and_idempotency() -> None:
    actor, farmer = user(), uuid4()
    repo = repository()
    repo.listing = AsyncMock(return_value=SimpleNamespace(status="active", farmer_id=farmer))
    repo.existing_conversation = AsyncMock(return_value=None)
    service = MessagingService(repo)
    result = await service.create_conversation(
        actor, ConversationCreate(scope_type="listing", scope_id=uuid4())
    )
    assert result.buyer_id == actor.id and result.farmer_id == farmer
    repo.add.assert_called_once()
    repo.existing_conversation.return_value = result
    assert (
        await service.create_conversation(
            actor, ConversationCreate(scope_type="listing", scope_id=result.scope_id)
        )
        is result
    )


@pytest.mark.anyio
async def test_conversation_scope_authorization() -> None:
    actor = user()
    repo = repository()
    repo.listing = AsyncMock(return_value=None)
    with pytest.raises(ApiError) as missing:
        await MessagingService(repo).create_conversation(
            actor, ConversationCreate(scope_type="listing", scope_id=uuid4())
        )
    assert missing.value.code == "scope_not_found"
    repo.listing.return_value = SimpleNamespace(status="active", farmer_id=uuid4())
    farmer_only = AuthenticatedUser(
        id=uuid4(), email=None, phone_e164=None, roles=frozenset({"farmer"}), token_version=0
    )
    with pytest.raises(ApiError) as wrong_role:
        await MessagingService(repo).create_conversation(
            farmer_only, ConversationCreate(scope_type="listing", scope_id=uuid4())
        )
    assert wrong_role.value.code == "scope_not_found"
    order = SimpleNamespace(id=uuid4(), buyer_id=actor.id)
    repo.order = AsyncMock(return_value=order)
    repo.order_has_farmer = AsyncMock(return_value=False)
    with pytest.raises(ApiError) as invalid:
        await MessagingService(repo).create_conversation(
            actor, ConversationCreate(scope_type="order", scope_id=order.id, farmer_id=uuid4())
        )
    assert invalid.value.code == "invalid_farmer"


@pytest.mark.anyio
async def test_farmer_can_open_only_an_order_they_own_items_in() -> None:
    actor, buyer = user(), uuid4()
    repo = repository()
    order = SimpleNamespace(id=uuid4(), buyer_id=buyer)
    repo.order = AsyncMock(return_value=order)
    repo.order_has_farmer = AsyncMock(return_value=True)
    repo.existing_conversation = AsyncMock(return_value=None)
    result = await MessagingService(repo).create_conversation(
        actor, ConversationCreate(scope_type="order", scope_id=order.id)
    )
    assert (result.buyer_id, result.farmer_id) == (buyer, actor.id)
    repo.order_has_farmer.return_value = False
    with pytest.raises(ApiError):
        await MessagingService(repo).create_conversation(
            actor, ConversationCreate(scope_type="order", scope_id=order.id)
        )


@pytest.mark.anyio
async def test_send_is_idempotent_and_enqueues_notification_atomically() -> None:
    actor, recipient = user(), uuid4()
    repo = repository()
    conversation = Conversation(
        id=uuid4(), scope_type="listing", scope_id=uuid4(), buyer_id=actor.id, farmer_id=recipient
    )
    repo.conversation = AsyncMock(return_value=conversation)
    repo.existing_message = AsyncMock(return_value=None)
    message = await MessagingService(repo).send(actor, conversation.id, uuid4(), " hello ")
    assert message.body == "hello"
    assert repo.add.call_count == 3
    assert repo.commit.await_count == 1
    repo.existing_message.return_value = message
    assert (
        await MessagingService(repo).send(
            actor, conversation.id, message.client_message_id, "ignored"
        )
        is message
    )
    repo.existing_message.return_value = None
    with pytest.raises(ApiError) as empty:
        await MessagingService(repo).send(actor, conversation.id, uuid4(), "   ")
    assert empty.value.code == "empty_message"


@pytest.mark.anyio
async def test_message_polling_and_read_marker_validation() -> None:
    actor = user()
    repo = repository()
    conversation = SimpleNamespace(id=uuid4())
    repo.conversation = AsyncMock(return_value=conversation)
    now = datetime.now(UTC).replace(tzinfo=None)
    values = [
        Message(
            id=uuid4(),
            conversation_id=conversation.id,
            sender_id=uuid4(),
            client_message_id=uuid4(),
            body="one",
            created_at=now,
        ),
        Message(
            id=uuid4(),
            conversation_id=conversation.id,
            sender_id=uuid4(),
            client_message_id=uuid4(),
            body="two",
            created_at=now,
        ),
    ]
    repo.messages = AsyncMock(return_value=values)
    page = await MessagingService(repo).messages(actor, conversation.id, None, 1)
    assert len(page.items) == 1 and page.next_cursor == values[0].id
    repo.message = AsyncMock(return_value=None)
    with pytest.raises(ApiError) as invalid:
        await MessagingService(repo).mark_read(actor, conversation.id, uuid4())
    assert invalid.value.code == "invalid_read_marker"
    message = Message(
        id=uuid4(),
        conversation_id=conversation.id,
        sender_id=uuid4(),
        client_message_id=uuid4(),
        body="x",
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )
    repo.message.return_value = message
    repo.read_state = AsyncMock(return_value=None)
    state = await MessagingService(repo).mark_read(actor, conversation.id, message.id)
    assert state.last_read_message_id == message.id


@pytest.mark.anyio
async def test_nonmember_gets_uniform_not_found() -> None:
    repo = repository()
    repo.conversation = AsyncMock(return_value=None)
    with pytest.raises(ApiError) as exc:
        await MessagingService(repo).messages(user(), uuid4(), None, 20)
    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_preferences_history_and_read() -> None:
    actor, repo = user(), repository()
    repo.preferences = AsyncMock(return_value=None)
    service = NotificationService(repo)
    defaults = await service.preferences(actor)
    assert defaults.messages_push and defaults.orders_push
    updated = await service.update_preferences(
        actor, NotificationPreferencesUpdate(messages_push=False, orders_push=True)
    )
    assert not updated.messages_push
    preference = NotificationPreference(user_id=actor.id, messages_push=True, orders_push=False)
    repo.preferences.return_value = preference
    await service.update_preferences(
        actor, NotificationPreferencesUpdate(messages_push=False, orders_push=True)
    )
    repo.notifications = AsyncMock(return_value=[])
    assert await service.list(actor) == []
    notification = Notification(
        id=uuid4(),
        user_id=actor.id,
        kind="message_received",
        title="t",
        body="b",
        data={},
        dedupe_key="d",
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )
    repo.notification = AsyncMock(return_value=notification)
    assert (await service.mark_read(actor, notification.id)).read_at is not None
    repo.notification.return_value = None
    with pytest.raises(ApiError):
        await service.mark_read(actor, uuid4())


@pytest.mark.anyio
async def test_delivery_decrypts_only_at_provider_boundary_and_is_idempotent() -> None:
    repo = repository()
    key = Fernet.generate_key().decode()
    protector = PushTokenProtector(encryption_key=SecretStr(key), hash_key=SecretStr("h" * 32))
    ciphertext, _ = protector.protect("secret-device-token")
    notification = Notification(
        id=uuid4(),
        user_id=uuid4(),
        kind="message_received",
        title="Hi",
        body="Body",
        data={},
        dedupe_key="d",
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )
    device = SimpleNamespace(id=uuid4(), push_token_ciphertext=ciphertext)
    repo.session.get = AsyncMock(return_value=notification)
    repo.preferences = AsyncMock(return_value=None)
    repo.active_devices = AsyncMock(return_value=[device])
    repo.delivery = AsyncMock(return_value=None)
    provider = MagicMock()
    provider.send = AsyncMock(return_value="provider-1")
    await NotificationDeliveryService(repo, provider, protector).deliver(notification.id)
    provider.send.assert_awaited_once()
    assert provider.send.await_args.args[0] == "secret-device-token"
    delivered = SimpleNamespace(status="delivered")
    repo.delivery.return_value = delivered
    await NotificationDeliveryService(repo, provider, protector).deliver(notification.id)
    assert provider.send.await_count == 1


@pytest.mark.anyio
async def test_delivery_respects_opt_out_and_missing_notification() -> None:
    repo = repository()
    repo.session.get = AsyncMock(return_value=None)
    provider = MagicMock(send=AsyncMock())
    protector = MagicMock()
    service = NotificationDeliveryService(repo, provider, protector)
    await service.deliver(uuid4())
    notification = SimpleNamespace(id=uuid4(), user_id=uuid4(), kind="message_received")
    repo.session.get.return_value = notification
    repo.preferences = AsyncMock(return_value=SimpleNamespace(messages_push=False))
    await service.deliver(notification.id)
    provider.send.assert_not_awaited()
    repo.preferences.return_value = None
    repo.active_devices = AsyncMock(return_value=[])
    await service.deliver(notification.id)
    provider.send.assert_not_awaited()


@pytest.mark.anyio
async def test_push_provider_success_failure_and_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Idempotency-Key"] == "dedupe"
        return httpx.Response(200, json={"message_id": "remote-1"})

    client_class = httpx.AsyncClient
    client = client_class(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: client)
    assert (
        await HttpPushProvider("https://push.test/send", "key").send(
            "token", PushPayload("t", "b", {}), "dedupe"
        )
        == "remote-1"
    )
    failing_client = client_class(
        transport=httpx.MockTransport(lambda _request: httpx.Response(503))
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: failing_client)
    with pytest.raises(PushProviderError, match="request failed"):
        await HttpPushProvider("https://push.test/send", "key").send(
            "token", PushPayload("t", "b", {}), "failed-dedupe"
        )
    with pytest.raises(PushProviderError):
        await UnconfiguredPushProvider().send("t", PushPayload("t", "b", {}), "k")
