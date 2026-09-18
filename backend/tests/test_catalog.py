from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, create_autospec
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from mavuno.api.errors import ApiError
from mavuno.auth.context import AuthenticatedUser
from mavuno.catalog.pagination import ListingCursor, decode_cursor, encode_cursor
from mavuno.catalog.repository import CatalogRepository
from mavuno.catalog.schemas import (
    CategoryCreate,
    ImageCreate,
    InventoryChange,
    ListingCreate,
    ListingUpdate,
    ProductCreate,
)
from mavuno.catalog.service import CatalogService
from mavuno.db.models import Listing, ProduceCategory, Product


@pytest.fixture
def farmer() -> AuthenticatedUser:
    return AuthenticatedUser(
        id=uuid4(),
        email="farmer@example.test",
        phone_e164=None,
        roles=frozenset({"farmer"}),
        token_version=0,
    )


@pytest.fixture
def repository() -> Any:
    value = create_autospec(CatalogRepository, instance=True)
    value.add = MagicMock()
    value.commit = AsyncMock()
    value.rollback = AsyncMock()
    value.flush = AsyncMock()
    value.refresh = AsyncMock()
    return value


@pytest.fixture
def service(repository: Any) -> CatalogService:
    return CatalogService(cast(CatalogRepository, repository))


def listing(farmer: AuthenticatedUser, *, quantity: str = "10.000") -> Listing:
    now = datetime.now(UTC).replace(tzinfo=None)
    value = Listing(
        id=uuid4(),
        farmer_id=farmer.id,
        product_id=uuid4(),
        title="Fresh sukuma wiki",
        price_amount=Decimal("50.0000"),
        currency="KES",
        available_quantity=Decimal(quantity),
        quantity_unit="kg",
        status="draft",
        version=1,
    )
    value.created_at = now
    value.updated_at = now
    return value


def listing_payload() -> ListingCreate:
    return ListingCreate(
        product_id=uuid4(),
        title="Fresh sukuma wiki",
        price_amount="50",
        available_quantity="10",
        quantity_unit="kg",
    )


def add_context(repository: Any, item: Listing) -> None:
    repository.listing_context = AsyncMock(
        return_value=(
            Product(
                id=item.product_id,
                category_id=uuid4(),
                name="Sukuma wiki",
                slug="sukuma-wiki",
                default_unit="kg",
            ),
            ProduceCategory(id=uuid4(), name="Leafy greens", slug="leafy-greens"),
            [],
        )
    )


def test_cursor_and_payload_validation() -> None:
    item_id = uuid4()
    assert decode_cursor(encode_cursor(Decimal("10.50"), item_id)).listing_id == item_id
    with pytest.raises(ValueError):
        decode_cursor("not-a-cursor")
    with pytest.raises(ValidationError):
        ListingCreate(
            product_id=uuid4(),
            title="Valid title",
            price_amount=1,
            available_quantity=1,
            quantity_unit="kg",
            available_from="2026-02-02",
            available_until="2026-01-01",
        )
    with pytest.raises(ValidationError):
        ListingUpdate(expected_version=1)
    with pytest.raises(ValidationError):
        ImageCreate(object_key="https://example.test/a.jpg", sort_order=0)
    with pytest.raises(ValidationError):
        InventoryChange(quantity_delta=0, movement_type="adjustment", reason="Correction")


@pytest.mark.anyio
async def test_create_listing_adds_initial_inventory(
    service: CatalogService, repository: Any, farmer: AuthenticatedUser
) -> None:
    payload = listing_payload()
    repository.get_product = AsyncMock(
        return_value=Product(
            id=payload.product_id,
            category_id=uuid4(),
            name="Sukuma",
            slug="sukuma",
            default_unit="kg",
        )
    )
    repository.listing_context = AsyncMock(
        return_value=(
            repository.get_product.return_value,
            ProduceCategory(id=uuid4(), name="Greens", slug="greens"),
            [],
        )
    )
    now = datetime.now(UTC).replace(tzinfo=None)

    async def set_database_values(item: Listing) -> None:
        item.created_at = now
        item.updated_at = now

    repository.refresh = AsyncMock(side_effect=set_database_values)

    result = await service.create_listing(farmer, payload)

    assert result.available_quantity == Decimal("10")
    assert repository.add.call_count == 2
    repository.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_listing_requires_farmer_and_known_product(
    service: CatalogService, repository: Any, farmer: AuthenticatedUser
) -> None:
    buyer = AuthenticatedUser(farmer.id, farmer.email, None, frozenset({"buyer"}), 0)
    with pytest.raises(ApiError) as role_error:
        await service.create_listing(buyer, listing_payload())
    assert role_error.value.code == "farmer_role_required"

    repository.get_product = AsyncMock(return_value=None)
    with pytest.raises(ApiError) as product_error:
        await service.create_listing(farmer, listing_payload())
    assert product_error.value.code == "product_not_found"


@pytest.mark.anyio
async def test_optimistic_update_and_conflict(
    service: CatalogService, repository: Any, farmer: AuthenticatedUser
) -> None:
    item = listing(farmer)
    repository.get_listing = AsyncMock(side_effect=[item, item])
    repository.optimistic_update = AsyncMock(return_value=True)
    add_context(repository, item)
    result = await service.update_listing(
        farmer, item.id, ListingUpdate(expected_version=1, title="Updated produce")
    )
    assert result.id == item.id

    repository.get_listing = AsyncMock(return_value=item)
    repository.optimistic_update = AsyncMock(return_value=False)
    with pytest.raises(ApiError) as conflict:
        await service.update_listing(
            farmer, item.id, ListingUpdate(expected_version=1, title="Another title")
        )
    assert conflict.value.code == "listing_version_conflict"
    repository.rollback.assert_awaited()


@pytest.mark.anyio
async def test_inventory_is_locked_and_never_negative(
    service: CatalogService, repository: Any, farmer: AuthenticatedUser
) -> None:
    item = listing(farmer, quantity="2.000")
    repository.get_listing = AsyncMock(return_value=item)
    add_context(repository, item)
    result = await service.change_inventory(
        farmer, item.id, Decimal("-2.000"), "adjustment", "Spoilage"
    )
    assert result.available_quantity == 0
    assert result.status == "sold_out"
    repository.get_listing.assert_awaited_with(item.id, lock=True)

    item.available_quantity = Decimal("1")
    with pytest.raises(ApiError) as error:
        await service.change_inventory(farmer, item.id, Decimal("-2"), "adjustment", "Invalid")
    assert error.value.code == "insufficient_inventory"


@pytest.mark.anyio
async def test_foreign_listing_is_hidden(
    service: CatalogService, repository: Any, farmer: AuthenticatedUser
) -> None:
    item = listing(farmer)
    item.farmer_id = uuid4()
    repository.get_listing = AsyncMock(return_value=item)
    with pytest.raises(ApiError) as error:
        await service.archive_listing(farmer, item.id, 1)
    assert error.value.code == "listing_not_found"


@pytest.mark.anyio
async def test_pagination_and_bad_range(
    service: CatalogService, repository: Any, farmer: AuthenticatedUser
) -> None:
    first = listing(farmer)
    second = listing(farmer)
    repository.list_listings = AsyncMock(return_value=[first, second])
    add_context(repository, first)
    page = await service.list_listings(
        search=None,
        category_slug=None,
        farmer_id=None,
        unit=None,
        min_price=None,
        max_price=None,
        sort="newest",
        cursor_raw=None,
        limit=1,
    )
    assert len(page.items) == 1
    assert page.next_cursor is not None

    with pytest.raises(ApiError) as error:
        await service.list_listings(
            search=None,
            category_slug=None,
            farmer_id=None,
            unit=None,
            min_price=Decimal("20"),
            max_price=Decimal("10"),
            sort="newest",
            cursor_raw=None,
            limit=20,
        )
    assert error.value.code == "invalid_price_range"

    with pytest.raises(ApiError) as cursor_error:
        await service.list_listings(
            search=None,
            category_slug=None,
            farmer_id=None,
            unit=None,
            min_price=None,
            max_price=None,
            sort="newest",
            cursor_raw="invalid",
            limit=20,
        )
    assert cursor_error.value.code == "invalid_cursor"


@pytest.mark.anyio
async def test_taxonomy_validation_and_unique_conflicts(
    service: CatalogService, repository: Any
) -> None:
    parent_id = uuid4()
    repository.get_category = AsyncMock(return_value=None)
    with pytest.raises(ApiError) as parent_error:
        await service.create_category(
            CategoryCreate(name="Leafy greens", slug="leafy-greens", parent_id=parent_id)
        )
    assert parent_error.value.code == "category_parent_not_found"

    with pytest.raises(ApiError) as category_error:
        await service.create_product(
            ProductCreate(category_id=parent_id, name="Spinach", slug="spinach", default_unit="kg")
        )
    assert category_error.value.code == "category_not_found"

    repository.get_category = AsyncMock(
        return_value=ProduceCategory(id=parent_id, name="Leafy", slug="leafy")
    )
    repository.commit = AsyncMock(side_effect=IntegrityError("duplicate", {}, Exception()))
    with pytest.raises(ApiError) as duplicate:
        await service.create_product(
            ProductCreate(category_id=parent_id, name="Spinach", slug="spinach", default_unit="kg")
        )
    assert duplicate.value.code == "product_slug_unavailable"
    repository.rollback.assert_awaited()


@pytest.mark.anyio
async def test_add_and_delete_image_errors(
    service: CatalogService, repository: Any, farmer: AuthenticatedUser
) -> None:
    item = listing(farmer)
    repository.get_listing = AsyncMock(return_value=item)
    repository.commit = AsyncMock(side_effect=IntegrityError("duplicate", {}, Exception()))
    with pytest.raises(ApiError) as conflict:
        await service.add_image(
            farmer, item.id, ImageCreate(object_key="listing/a.jpg", sort_order=0)
        )
    assert conflict.value.code == "listing_image_conflict"

    repository.commit = AsyncMock()
    repository.get_image = AsyncMock(return_value=None)
    with pytest.raises(ApiError) as missing:
        await service.delete_image(farmer, item.id, uuid4())
    assert missing.value.code == "listing_image_not_found"


@pytest.mark.anyio
async def test_listing_state_guards(
    service: CatalogService, repository: Any, farmer: AuthenticatedUser
) -> None:
    item = listing(farmer, quantity="0")
    repository.get_listing = AsyncMock(return_value=item)
    with pytest.raises(ApiError) as no_stock:
        await service.update_listing(
            farmer, item.id, ListingUpdate(expected_version=1, status="active")
        )
    assert no_stock.value.code == "listing_has_no_stock"

    repository.optimistic_update = AsyncMock(return_value=False)
    with pytest.raises(ApiError) as archive_conflict:
        await service.archive_listing(farmer, item.id, 1)
    assert archive_conflict.value.code == "listing_version_conflict"

    repository.get_listing = AsyncMock(return_value=None)
    with pytest.raises(ApiError) as missing:
        await service.get_listing(item.id)
    assert missing.value.code == "listing_not_found"


def test_repository_cursor_sort_variants() -> None:
    base = select(Listing)
    listing_id = uuid4()
    newest = CatalogRepository._cursor_order(
        base,
        "newest",
        ListingCursor(datetime.now(UTC).replace(tzinfo=None).isoformat(), listing_id),
    )
    ascending = CatalogRepository._cursor_order(
        base, "price_asc", ListingCursor("10.0000", listing_id)
    )
    descending = CatalogRepository._cursor_order(
        base, "price_desc", ListingCursor("10.0000", listing_id)
    )
    assert "ORDER BY" in str(newest)
    assert "ORDER BY" in str(ascending)
    assert "ORDER BY" in str(descending)
