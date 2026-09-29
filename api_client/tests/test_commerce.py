from decimal import Decimal

import pytest
from api_client.client import MavunoClient
from api_client.models.catalog import ListingCreateRequest, ListingUpdateRequest
from api_client.models.commerce import CartItemUpsert, CheckoutRequest, PaymentInitiateRequest
from api_client.models.profiles import AddressCreate
from api_client.tests.conftest import register_and_login


@pytest.fixture
def farmer_client(client: MavunoClient) -> MavunoClient:
    c, _ = register_and_login(client, "farmer")
    return c


@pytest.fixture
def buyer_client(client: MavunoClient) -> MavunoClient:
    c, _ = register_and_login(client, "buyer")
    return c


def test_commerce_cart_and_checkout_lifecycle(
    farmer_client: MavunoClient, buyer_client: MavunoClient, test_product: str
):
    # Farmer creates listing
    listing_res = farmer_client.catalog.create_listing(
        ListingCreateRequest(
            product_id=test_product,
            title="Red Onions",
            price_amount=Decimal("80.00"),
            available_quantity=Decimal("50.000"),
            quantity_unit="kg",
        )
    )
    assert listing_res.success is True
    listing_id = listing_res.data.id

    # Listings only become purchasable once "active" (new listings start as "draft")
    activate_res = farmer_client.catalog.update_listing(
        listing_id,
        ListingUpdateRequest(expected_version=listing_res.data.version, status="active"),
    )
    assert activate_res.success is True

    # Buyer creates address
    addr_res = buyer_client.profiles.create_address(
        AddressCreate(
            label="Home",
            line_1="Westlands Ring Rd",
            locality="Westlands",
            county="Nairobi",
        )
    )
    assert addr_res.success is True
    address_id = addr_res.data.id

    # Add to cart
    add_res = buyer_client.commerce.upsert_cart_item(listing_id, CartItemUpsert(quantity=Decimal("5.000")))
    assert add_res.success is True

    # Verify cart
    cart_res = buyer_client.commerce.get_cart()
    assert cart_res.success is True
    assert any(item.listing_id == listing_id for item in cart_res.data.items)

    # Checkout
    checkout_res = buyer_client.commerce.checkout(CheckoutRequest(delivery_address_id=address_id))
    assert checkout_res.success is True
    order_id = checkout_res.data.id

    # Initiate Payment (the dev environment has no M-Pesa/bank provider configured, so a
    # 503 "payments_disabled" response is expected there; only treat other failures as bugs)
    pay_res = buyer_client.commerce.initiate_payment(
        PaymentInitiateRequest(order_id=order_id, rail="mpesa", phone_e164="+254712345678")
    )
    assert pay_res.success is True or pay_res.status_code == 503
