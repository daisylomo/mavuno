from decimal import Decimal

import pytest
from api_client.client import MavunoClient
from api_client.models.catalog import (
    InventoryChangeRequest,
    ListingCreateRequest,
    ListingFilterRequest,
    ListingUpdateRequest,
)
from api_client.tests.conftest import register_and_login


@pytest.fixture
def farmer_client(client: MavunoClient) -> MavunoClient:
    c, _ = register_and_login(client, "farmer")
    return c


def test_catalog_lifecycle(farmer_client: MavunoClient, client: MavunoClient, test_product: str):
    # 1. Create Listing
    create_req = ListingCreateRequest(
        product_id=test_product,
        title="Grade 1 Spinach",
        price_amount=Decimal("45.00"),
        available_quantity=Decimal("200.000"),
        quantity_unit="kg",
    )
    create_res = farmer_client.catalog.create_listing(create_req)
    assert create_res.success is True, f"Create listing failed: {create_res.error}"
    listing_id = create_res.data.id

    # 2. Get Listing
    get_res = farmer_client.catalog.get_listing(listing_id)
    assert get_res.success is True
    assert get_res.data.id == listing_id

    # 3. Activate Listing (new listings start as "draft" and are invisible to public search)
    activate_res = farmer_client.catalog.update_listing(
        listing_id,
        ListingUpdateRequest(expected_version=create_res.data.version, status="active"),
    )
    assert activate_res.success is True
    assert activate_res.data.status == "active"

    # 4. Update Price
    update_res = farmer_client.catalog.update_listing(
        listing_id,
        ListingUpdateRequest(expected_version=activate_res.data.version, price_amount=Decimal("50.00")),
    )
    assert update_res.success is True
    assert update_res.data.price_amount == Decimal("50.00")

    # 5. Change Inventory
    inv_res = farmer_client.catalog.change_inventory(
        listing_id,
        InventoryChangeRequest(
            quantity_delta=Decimal("-50.000"), movement_type="adjustment", reason="Wholesale sale"
        ),
    )
    assert inv_res.success is True
    assert inv_res.data.available_quantity == Decimal("150.000")

    # 6. Public Search Discovery
    search_res = client.catalog.list_listings(ListingFilterRequest(limit=20, sort="newest"))
    assert search_res.success is True
    assert listing_id in [item.id for item in search_res.data.items]

    # 7. Archive Listing
    archive_res = farmer_client.catalog.archive_listing(
        listing_id, expected_version=inv_res.data.version
    )
    assert archive_res.success is True
