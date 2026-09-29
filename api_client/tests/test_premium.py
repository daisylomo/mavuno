from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from api_client.client import MavunoClient
from api_client.models.premium import PrebookingCreate, PrebookingTransition
from api_client.tests.conftest import grant_premium_entitlement, register_and_login


@pytest.fixture
def farmer_client(client: MavunoClient):
    c, user_id = register_and_login(client, "farmer")
    return c, user_id


@pytest.fixture
def buyer_client(client: MavunoClient):
    c, user_id = register_and_login(client, "buyer")
    return c, user_id


def test_premium_plans_and_subscriptions(client: MavunoClient, farmer_client):
    farmer, _ = farmer_client

    # 1. Public list of available subscription tiers
    plans_res = client.premium.list_plans()
    assert plans_res.success is True, f"List plans failed: {plans_res.error}"
    assert plans_res.data is not None

    # 2. Farmer queries active subscriptions (should be empty initially or populated)
    subs_res = farmer.premium.list_subscriptions()
    assert subs_res.success is True, f"List subscriptions failed: {subs_res.error}"

    # 3. Farmer market insights require an active, verified "insights" entitlement
    insights_res = farmer.premium.get_farmer_insights()
    assert insights_res.status_code == 403


def test_premium_farmer_insights_with_entitlement(farmer_client):
    farmer, farmer_id = farmer_client
    grant_premium_entitlement(farmer_id, "farmer", ["insights"])

    insights_res = farmer.premium.get_farmer_insights()
    assert insights_res.success is True, f"Get insights failed: {insights_res.error}"
    assert insights_res.data is not None


def test_premium_prebooking_lifecycle(farmer_client, buyer_client, test_product: str):
    farmer, farmer_id = farmer_client
    buyer, buyer_id = buyer_client

    # Prebooking creation requires the buyer to hold an active, verified "prebooking" entitlement
    grant_premium_entitlement(buyer_id, "buyer", ["prebooking"])

    now = datetime.now(timezone.utc)

    # 1. Buyer creates a pre-booking contract for an upcoming harvest
    prebooking_req = PrebookingCreate(
        farmer_id=farmer_id,
        product_id=test_product,
        quantity=Decimal("500.000"),
        quantity_unit="kg",
        target_price=Decimal("120.00"),
        window_start=(now + timedelta(days=7)).isoformat(),
        window_end=(now + timedelta(days=14)).isoformat(),
    )
    create_res = buyer.premium.create_prebooking(prebooking_req)
    assert create_res.success is True, f"Create prebooking failed: {create_res.error}"
    prebooking_id = create_res.data.id

    # 2. Buyer inspects their active pre-bookings
    buyer_bookings = buyer.premium.list_prebookings()
    assert buyer_bookings.success is True
    assert any(b.id == prebooking_id for b in buyer_bookings.data)

    # 3. Farmer accepts the pre-booking
    status_req = PrebookingTransition(status="accepted", expected_version=create_res.data.version)
    status_res = farmer.premium.transition_prebooking(prebooking_id, status_req)
    assert status_res.success is True, f"Transition failed: {status_res.error}"
    assert status_res.data.status == "accepted"
