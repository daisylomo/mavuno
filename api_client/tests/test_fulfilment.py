from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from api_client.client import MavunoClient
from api_client.models.catalog import ListingCreateRequest, ListingUpdateRequest
from api_client.models.commerce import CartItemUpsert, CheckoutRequest
from api_client.models.fulfilment import FulfilmentTransition, FulfilmentUpdate
from api_client.models.profiles import AddressCreate
from api_client.tests.conftest import mark_order_paid, register_and_login


@pytest.fixture
def logistics_environment(client: MavunoClient, test_product: str):
    farmer, _ = register_and_login(client, "farmer")
    buyer, _ = register_and_login(client, "buyer")

    listing_res = farmer.catalog.create_listing(
        ListingCreateRequest(
            product_id=test_product,
            title="Potatoes",
            price_amount=Decimal("60.00"),
            available_quantity=Decimal("100.000"),
            quantity_unit="kg",
        )
    )
    assert listing_res.success is True, f"Create listing failed: {listing_res.error}"
    listing = listing_res.data
    activate_res = farmer.catalog.update_listing(
        listing.id, ListingUpdateRequest(expected_version=listing.version, status="active")
    )
    assert activate_res.success is True

    address_res = buyer.profiles.create_address(
        AddressCreate(label="Hub", line_1="Mombasa Rd", locality="Industrial Area", county="Nairobi")
    )
    assert address_res.success is True

    cart_res = buyer.commerce.upsert_cart_item(listing.id, CartItemUpsert(quantity=Decimal("20.000")))
    assert cart_res.success is True

    checkout_res = buyer.commerce.checkout(CheckoutRequest(delivery_address_id=address_res.data.id))
    assert checkout_res.success is True, f"Checkout failed: {checkout_res.error}"
    order_id = checkout_res.data.id

    # No payment provider is configured in this environment; flip the order to "paid" directly
    # so the fulfilment coordination endpoints (which require order.status in {paid, fulfilment}) work.
    mark_order_paid(order_id)

    return farmer, buyer, order_id


def test_fulfilment_tracking_and_transitions(logistics_environment):
    farmer, buyer, order_id = logistics_environment
    now = datetime.now(timezone.utc)

    # 1. Buyer opens the fulfilment coordination record (creates it in "pending" status)
    create_res = buyer.fulfilment.update_fulfilment(
        order_id,
        FulfilmentUpdate(
            method="delivery",
            location_label="Buyer shop",
            location_details="Kenyatta Avenue",
            window_start=(now + timedelta(hours=2)).isoformat(),
            window_end=(now + timedelta(hours=4)).isoformat(),
            coordination_notes="Call on arrival",
        ),
    )
    assert create_res.success is True, f"Create fulfilment failed: {create_res.error}"
    assert create_res.data.status == "pending"

    # 2. Fetch the record back
    fulfilment_res = farmer.fulfilment.get_fulfilment(order_id)
    assert fulfilment_res.success is True, f"Get fulfilment failed: {fulfilment_res.error}"
    assert fulfilment_res.data is not None

    # 3. Farmer schedules pickup/delivery
    scheduled_res = farmer.fulfilment.transition_fulfilment(
        order_id,
        FulfilmentTransition(status="scheduled", expected_version=create_res.data.version),
    )
    assert scheduled_res.success is True, f"Schedule transition failed: {scheduled_res.error}"
    assert scheduled_res.data.status == "scheduled"

    # 4. Farmer marks ready for handover
    ready_res = farmer.fulfilment.transition_fulfilment(
        order_id,
        FulfilmentTransition(status="ready_for_handover", expected_version=scheduled_res.data.version),
    )
    assert ready_res.success is True
    assert ready_res.data.status == "ready_for_handover"

    # 5. Farmer marks in-transit (only valid for "delivery" method)
    transit_res = farmer.fulfilment.transition_fulfilment(
        order_id,
        FulfilmentTransition(status="in_transit", expected_version=ready_res.data.version),
    )
    assert transit_res.success is True, f"In-transit transition failed: {transit_res.error}"
    assert transit_res.data.status == "in_transit"

    # 6. Buyer confirms completion
    completed_res = buyer.fulfilment.transition_fulfilment(
        order_id,
        FulfilmentTransition(status="completed", expected_version=transit_res.data.version),
    )
    assert completed_res.success is True
    assert completed_res.data.status == "completed"
