from __future__ import annotations

import os
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import delete, select

from mavuno.auth.context import AuthenticatedUser
from mavuno.core.config import Settings
from mavuno.db import Database
from mavuno.db.models import (
    Conversation,
    ConversationReadState,
    Listing,
    Message,
    Notification,
    NotificationDelivery,
    NotificationPreference,
    OutboxJob,
    ProduceCategory,
    Product,
    User,
)
from mavuno.messaging.repository import MessagingRepository
from mavuno.messaging.schemas import ConversationCreate
from mavuno.messaging.service import MessagingService, NotificationService

TEST_DATABASE_URL = os.getenv("MAVUNO_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="MAVUNO_TEST_DATABASE_URL is not set"),
]


@pytest.mark.anyio
async def test_listing_conversation_message_read_and_notification_round_trip() -> None:
    assert TEST_DATABASE_URL is not None
    database = Database(Settings(environment="test", database_url=SecretStr(TEST_DATABASE_URL)))
    buyer_id, farmer_id = uuid4(), uuid4()
    category = ProduceCategory(id=uuid4(), name="Messaging crop", slug=f"messaging-{uuid4()}")
    product = Product(
        id=uuid4(),
        category_id=category.id,
        name="Messaging product",
        slug=f"product-{uuid4()}",
        default_unit="kg",
    )
    listing = Listing(
        id=uuid4(),
        farmer_id=farmer_id,
        product_id=product.id,
        title="Conversation listing",
        price_amount=Decimal("10"),
        available_quantity=Decimal("5"),
        quantity_unit="kg",
        status="active",
    )
    buyer = AuthenticatedUser(buyer_id, "buyer@example.test", None, frozenset({"buyer"}), 0)
    try:
        async with database.session() as session:
            session.add_all(
                [
                    User(
                        id=buyer_id,
                        email=f"{buyer_id}@test.local",
                        password_hash="x",
                        status="active",
                    ),
                    User(
                        id=farmer_id,
                        email=f"{farmer_id}@test.local",
                        password_hash="x",
                        status="active",
                    ),
                    category,
                ]
            )
            await session.flush()
            session.add(product)
            await session.flush()
            session.add(listing)
            await session.commit()

        async with database.session() as session:
            repository = MessagingRepository(session)
            service = MessagingService(repository)
            conversation = await service.create_conversation(
                buyer, ConversationCreate(scope_type="listing", scope_id=listing.id)
            )
            same = await service.create_conversation(
                buyer, ConversationCreate(scope_type="listing", scope_id=listing.id)
            )
            assert same.id == conversation.id
            message = await service.send(buyer, conversation.id, uuid4(), "Is this available?")
            duplicate = await service.send(
                buyer, conversation.id, message.client_message_id, "ignored"
            )
            assert duplicate.id == message.id
            assert (await service.list_conversations(buyer))[0].id == conversation.id
            page = await service.messages(buyer, conversation.id, None, 50)
            assert page.items[0].body == "Is this available?"
            await service.mark_read(buyer, conversation.id, message.id)
            notifications = await repository.notifications(farmer_id)
            assert len(notifications) == 1
            farmer = AuthenticatedUser(farmer_id, None, None, frozenset({"farmer"}), 0)
            await NotificationService(repository).mark_read(farmer, notifications[0].id)
    finally:
        async with database.session() as session:
            await session.execute(delete(NotificationDelivery))
            await session.execute(
                delete(OutboxJob).where(OutboxJob.dedupe_key.like("notification:%"))
            )
            await session.execute(delete(ConversationReadState))
            await session.execute(
                delete(Notification).where(Notification.user_id.in_([buyer_id, farmer_id]))
            )
            await session.execute(
                delete(NotificationPreference).where(
                    NotificationPreference.user_id.in_([buyer_id, farmer_id])
                )
            )
            conversation_ids = select(Conversation.id).where(Conversation.scope_id == listing.id)
            await session.execute(
                delete(Message).where(Message.conversation_id.in_(conversation_ids))
            )
            await session.execute(delete(Conversation).where(Conversation.scope_id == listing.id))
            await session.execute(delete(Listing).where(Listing.id == listing.id))
            await session.execute(delete(Product).where(Product.id == product.id))
            await session.execute(delete(ProduceCategory).where(ProduceCategory.id == category.id))
            await session.execute(delete(User).where(User.id.in_([buyer_id, farmer_id])))
            await session.commit()
        await database.dispose()
