import uuid
from decimal import Decimal

from api_client.client import MavunoClient
from api_client.models.catalog import ListingCreateRequest, ListingUpdateRequest
from api_client.models.messaging import (
    ConversationCreate,
    MarkReadRequest,
    MessageCreate,
    NotificationPreferencesUpdate,
)
from api_client.tests.conftest import register_and_login


def test_messaging_lifecycle(client: MavunoClient, test_product: str):
    farmer_client, _ = register_and_login(client, "farmer")
    buyer_client, _ = register_and_login(client, "buyer")

    listing_res = farmer_client.catalog.create_listing(
        ListingCreateRequest(
            product_id=test_product,
            title="Kale",
            price_amount=Decimal("30.00"),
            available_quantity=Decimal("100.000"),
            quantity_unit="kg",
        )
    )
    assert listing_res.success is True
    listing = listing_res.data
    activate_res = farmer_client.catalog.update_listing(
        listing.id, ListingUpdateRequest(expected_version=listing.version, status="active")
    )
    assert activate_res.success is True

    # Buyer starts a conversation scoped to the listing
    conv_res = buyer_client.messaging.create_conversation(
        ConversationCreate(scope_type="listing", scope_id=listing.id)
    )
    assert conv_res.success is True, f"Create conversation failed: {conv_res.error}"
    conversation_id = conv_res.data.id

    # Send message
    msg_res = buyer_client.messaging.send_message(
        conversation_id,
        MessageCreate(body="Is the harvest ready?", client_message_id=str(uuid.uuid4())),
    )
    assert msg_res.success is True
    msg_id = msg_res.data.id

    # Read messages
    msgs_res = farmer_client.messaging.list_messages(conversation_id)
    assert msgs_res.success is True
    assert any(m.id == msg_id for m in msgs_res.data.items)

    # Mark as read
    read_res = farmer_client.messaging.mark_conversation_read(
        conversation_id, MarkReadRequest(last_read_message_id=msg_id)
    )
    assert read_res.success is True

    # Update notification preferences
    pref_res = farmer_client.messaging.update_notification_preferences(
        NotificationPreferencesUpdate(messages_push=True, orders_push=False)
    )
    assert pref_res.success is True
    assert pref_res.data.orders_push is False
