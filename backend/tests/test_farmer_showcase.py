"""Farmer details on listings, stored photos, whole-shilling prices and the new routes."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, create_autospec
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from mavuno.api.errors import ApiError
from mavuno.api.v1 import catalog as catalog_routes
from mavuno.api.v1 import commerce as commerce_routes
from mavuno.api.v1 import profiles as profile_routes
from mavuno.auth.context import AuthenticatedUser
from mavuno.catalog.repository import CatalogRepository, FarmerFacts
from mavuno.catalog.schemas import (
    ImageCreate,
    ImageResponse,
    ListingCreate,
    ListingUpdate,
    PhotoUpload,
)
from mavuno.catalog.service import CatalogService
from mavuno.commerce.schemas import OrderCancelRequest, RefundCompletion
from mavuno.core.config import Settings
from mavuno.db.models import (
    FarmerProfile,
    Listing,
    ListingImage,
    ListingImageContent,
    ProduceCategory,
    Product,
    Profile,
    User,
)
from mavuno.profiles.schemas import FarmerProfileUpdate

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"0" * 64


def now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def farmer() -> AuthenticatedUser:
    return AuthenticatedUser(uuid4(), "farmer@example.test", None, frozenset({"farmer"}), 0)


def facts(user_id: Any, *, with_profiles: bool = True) -> FarmerFacts:
    user = User(id=user_id, email="f@example.test", password_hash="x", status="active")
    user.created_at = now()
    return FarmerFacts(
        user=user,
        profile=Profile(user_id=user_id, display_name="Wanjiru Kamau", bio="Third generation")
        if with_profiles
        else None,
        farmer=FarmerProfile(
            user_id=user_id,
            farm_name="Kamau Greens",
            county="Kiambu",
            locality="Limuru",
            verification_status="verified",
            offers_pickup=True,
            offers_delivery=True,
            farming_practices="No synthetic pesticides (farmer's description)",
            farm_size_acres=Decimal("2.5"),
            farming_since_year=2012,
            delivery_radius_km=15,
        )
        if with_profiles
        else None,
        active_listings=4,
        completed_orders=31,
    )


def owned_listing(owner: AuthenticatedUser) -> Listing:
    value = Listing(
        id=uuid4(),
        farmer_id=owner.id,
        product_id=uuid4(),
        title="Sukuma wiki",
        price_amount=Decimal("50"),
        currency="KES",
        available_quantity=Decimal("10"),
        quantity_unit="bunch",
        status="active",
        version=1,
    )
    value.created_at = now()
    value.updated_at = now()
    return value


@pytest.fixture
def repository() -> Any:
    value = create_autospec(CatalogRepository, instance=True)
    value.add = MagicMock()
    value.commit = AsyncMock()
    value.rollback = AsyncMock()
    value.flush = AsyncMock()
    value.refresh = AsyncMock()
    value.next_image_order = AsyncMock(return_value=1)
    return value


def test_prices_must_be_whole_shillings() -> None:
    with pytest.raises(ValidationError, match="whole shillings"):
        ListingCreate(
            product_id=uuid4(),
            title="Tomatoes",
            price_amount=Decimal("99.50"),
            available_quantity=Decimal("5"),
            quantity_unit="kg",
        )
    with pytest.raises(ValidationError, match="whole shillings"):
        ListingUpdate(expected_version=1, price_amount=Decimal("10.25"))
    assert ListingUpdate(expected_version=1, price_amount=Decimal("10.00")).price_amount == 10


def test_uploaded_images_get_a_served_url_and_presets_do_not() -> None:
    image_id = uuid4()
    uploaded = ImageResponse(id=image_id, object_key=f"uploads/{image_id}", sort_order=0)
    assert uploaded.url == f"/api/v1/listing-images/{image_id}"
    preset = ImageResponse(id=uuid4(), object_key="preset/tomatoes", sort_order=0)
    assert preset.url is None


@pytest.mark.anyio
async def test_listing_response_names_the_farmer(repository: Any) -> None:
    owner = farmer()
    listing = owned_listing(owner)
    repository.get_listing = AsyncMock(return_value=listing)
    repository.listing_context = AsyncMock(
        return_value=(
            Product(id=listing.product_id, category_id=uuid4(), name="Kale", slug="kale"),
            ProduceCategory(id=uuid4(), name="Vegetables", slug="vegetables"),
            [],
        )
    )
    repository.farmer_facts = AsyncMock(return_value={owner.id: facts(owner.id)})
    service = CatalogService(cast(CatalogRepository, repository))
    response = await service.get_listing(listing.id)
    assert response.farmer is not None
    assert response.farmer.display_name == "Wanjiru Kamau"
    assert response.farmer.locality == "Limuru"
    assert response.farmer.completed_orders == 31
    await service.get_listing(listing.id)
    repository.farmer_facts.assert_awaited_once()

    bare = CatalogService(cast(CatalogRepository, repository))
    repository.farmer_facts = AsyncMock(
        return_value={owner.id: facts(owner.id, with_profiles=False)}
    )
    summary = (await bare.get_listing(listing.id)).farmer
    assert summary is not None and summary.display_name == "Mavuno farmer"
    assert summary.verification_status == "unverified"


@pytest.mark.anyio
async def test_public_farmer_profile(repository: Any) -> None:
    owner_id = uuid4()
    repository.farmer_facts = AsyncMock(return_value={owner_id: facts(owner_id)})
    repository.farmer_categories = AsyncMock(return_value=["Fruits", "Vegetables"])
    repository.farmer_cancellations = AsyncMock(return_value=1)
    profile = await CatalogService(cast(CatalogRepository, repository)).farmer_profile(owner_id)
    assert profile.farm_name == "Kamau Greens"
    assert profile.categories == ["Fruits", "Vegetables"]
    assert profile.farming_since_year == 2012
    assert profile.cancelled_handovers == 1

    repository.farmer_facts = AsyncMock(return_value={})
    with pytest.raises(ApiError) as missing:
        await CatalogService(cast(CatalogRepository, repository)).farmer_profile(uuid4())
    assert missing.value.code == "farmer_not_found"


@pytest.mark.anyio
async def test_photo_upload_is_validated_and_stored(repository: Any) -> None:
    owner = farmer()
    listing = owned_listing(owner)
    repository.get_listing = AsyncMock(return_value=listing)
    service = CatalogService(cast(CatalogRepository, repository), max_image_bytes=100)
    for content, kind in ((JPEG, "image/jpeg"), (PNG, "image/png"), (WEBP, "image/webp")):
        repository.add.reset_mock()
        image = await service.add_photo(
            owner,
            listing.id,
            PhotoUpload(
                content_type=kind,
                content_base64=base64.b64encode(content).decode(),
                alt_text="Harvest",
            ),
        )
        assert image.object_key == f"uploads/{image.id}"
        assert image.sort_order == 1
        stored = repository.add.call_args_list[1].args[0]
        assert isinstance(stored, ListingImageContent)
        assert stored.content == content and stored.byte_size == len(content)

    bad = [
        (PhotoUpload(content_type="image/png", content_base64="not base64!!!!!!"), "invalid_photo"),
        (
            PhotoUpload(content_type="image/png", content_base64=base64.b64encode(JPEG).decode()),
            "invalid_photo",
        ),
        (
            PhotoUpload(
                content_type="image/jpeg", content_base64=base64.b64encode(JPEG * 3).decode()
            ),
            "photo_too_large",
        ),
    ]
    for payload, code in bad:
        with pytest.raises(ApiError) as rejected:
            await service.add_photo(owner, listing.id, payload)
        assert rejected.value.code == code

    repository.commit = AsyncMock(side_effect=IntegrityError("insert", {}, Exception()))
    with pytest.raises(ApiError) as conflict:
        await service.add_photo(
            owner,
            listing.id,
            PhotoUpload(content_type="image/jpeg", content_base64=base64.b64encode(JPEG).decode()),
        )
    assert conflict.value.code == "listing_image_conflict"

    with pytest.raises(ApiError) as reserved:
        await service.add_image(
            owner, listing.id, ImageCreate(object_key="uploads/forged", sort_order=2)
        )
    assert reserved.value.code == "uploaded_key_reserved"


@pytest.mark.anyio
async def test_photo_is_served_with_caching(repository: Any) -> None:
    image_id = uuid4()
    content = ListingImageContent(
        image_id=image_id, content_type="image/jpeg", byte_size=4, sha256="abc", content=JPEG
    )
    repository.image_content = AsyncMock(return_value=content)
    service = CatalogService(cast(CatalogRepository, repository))
    assert (await service.photo(image_id)).content == JPEG
    repository.image_content = AsyncMock(return_value=None)
    with pytest.raises(ApiError):
        await service.photo(image_id)


@pytest.mark.anyio
async def test_catalog_routes_for_photos_and_farmers(monkeypatch: pytest.MonkeyPatch) -> None:
    service = MagicMock()
    content = ListingImageContent(
        image_id=uuid4(), content_type="image/png", byte_size=4, sha256="abc", content=PNG
    )
    image = ListingImage(id=uuid4(), listing_id=uuid4(), object_key="uploads/x", sort_order=0)
    service.photo = AsyncMock(return_value=content)
    service.add_photo = AsyncMock(return_value=image)
    service.farmer_profile = AsyncMock(return_value="profile")
    monkeypatch.setattr(catalog_routes, "CatalogService", lambda *_args: service)
    request = MagicMock()
    request.headers = {}
    request.app.state.catalog_cache.invalidate_listing = AsyncMock()
    request.app.state.settings = Settings(environment="test")
    session = MagicMock()

    served = await catalog_routes.listing_photo(uuid4(), request, session)
    assert served.body == PNG and served.headers["etag"] == '"abc"'
    request.headers = {"if-none-match": '"abc"'}
    assert (await catalog_routes.listing_photo(uuid4(), request, session)).status_code == 304

    uploaded = await catalog_routes.upload_photo(
        uuid4(),
        PhotoUpload(content_type="image/png", content_base64=base64.b64encode(PNG).decode()),
        farmer(),
        session,
        request,
    )
    assert uploaded is image
    response = MagicMock(headers={})
    profile: Any = await catalog_routes.farmer_profile(uuid4(), session, response)
    assert profile == "profile"


@pytest.mark.anyio
async def test_commerce_routes_for_cancel_refresh_and_refunds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkout = MagicMock()
    checkout.cancel = AsyncMock(return_value="order")
    checkout.response = AsyncMock(return_value="order-response")
    payments = MagicMock()
    payments.refresh = AsyncMock(return_value="payment")
    payments.accept_reversal_result = AsyncMock()
    refunds = MagicMock()
    refunds.complete_manually = AsyncMock(return_value="refund")
    repository = MagicMock()
    repository.refunds_by_state = AsyncMock(return_value=["open"])
    monkeypatch.setattr(commerce_routes, "CheckoutService", lambda *_args: checkout)
    monkeypatch.setattr(commerce_routes, "PaymentService", lambda *_args, **_kwargs: payments)
    monkeypatch.setattr(commerce_routes, "RefundService", lambda *_args: refunds)
    monkeypatch.setattr(commerce_routes, "CommerceRepository", lambda _session: repository)
    request = MagicMock()
    session = MagicMock()
    buyer = AuthenticatedUser(uuid4(), "b@example.test", None, frozenset({"buyer"}), 0)
    admin = AuthenticatedUser(uuid4(), "a@example.test", None, frozenset({"administrator"}), 0)

    cancelled: Any = await commerce_routes.cancel_order(
        uuid4(), OrderCancelRequest(), buyer, session, request
    )
    assert cancelled == "order-response"
    assert await commerce_routes.refresh_payment(uuid4(), buyer, session, request) == "payment"
    assert await commerce_routes.daraja_reversal_result("t", {}, session, request) == {
        "accepted": True
    }
    assert await commerce_routes.open_refunds(admin, session) == ["open"]
    assert (
        await commerce_routes.complete_refund(
            uuid4(), RefundCompletion(reference="QWE123"), admin, session, request
        )
        == "refund"
    )
    with pytest.raises(ApiError) as forbidden:
        await commerce_routes.open_refunds(buyer, session)
    assert forbidden.value.code == "administrator_role_required"


@pytest.mark.anyio
async def test_farmer_orders_hide_contact_until_paid(monkeypatch: pytest.MonkeyPatch) -> None:
    owner = farmer()
    order = MagicMock(id=uuid4(), status="pending_payment", created_at=now())
    order.reservation_expires_at = now()
    item = MagicMock(
        listing_id=uuid4(),
        farmer_id=owner.id,
        product_name="Kale",
        listing_title="Kale",
        quantity=Decimal("1"),
        quantity_unit="bunch",
        unit_price=Decimal("50"),
        line_total=Decimal("50"),
    )
    buyer = MagicMock(phone_e164="+254700000000", email=None)
    address = MagicMock(line_1="1 Road", locality="Town", county="County")
    repository = MagicMock()
    repository.farmer_order_rows = AsyncMock(return_value=[(order, item, buyer, None, address)])
    repository.order_fulfilments = AsyncMock(return_value=[])
    other = MagicMock(farmer_id=uuid4())
    repository.order_items = AsyncMock(return_value=[item, other])
    monkeypatch.setattr(commerce_routes, "CommerceRepository", lambda _session: repository)
    [pending] = await commerce_routes.farmer_orders(owner, MagicMock())
    assert pending.customer_phone is None and pending.delivery_location is None
    assert pending.reservation_expires_at is not None
    assert pending.other_farmers == 1

    order.status = "paid"
    part = MagicMock(farmer_id=owner.id, status="scheduled", version=2)
    repository.order_fulfilments = AsyncMock(return_value=[part])
    [paid] = await commerce_routes.farmer_orders(owner, MagicMock())
    assert paid.customer_phone == "+254700000000"
    assert paid.delivery_location == "1 Road, Town, County"
    assert (paid.fulfilment_status, paid.fulfilment_version) == ("scheduled", 2)


def test_farmer_profile_update_validation() -> None:
    update = FarmerProfileUpdate(locality="Limuru", offers_delivery=True, delivery_radius_km=10)
    assert update.offers_delivery is True
    with pytest.raises(ValidationError):
        FarmerProfileUpdate(offers_pickup=None)
    with pytest.raises(ValidationError):
        FarmerProfileUpdate(farm_size_acres=Decimal("0"))


@pytest.mark.anyio
async def test_get_farmer_profile_route(monkeypatch: pytest.MonkeyPatch) -> None:
    service = MagicMock()
    service.get_farmer = AsyncMock(return_value="farmer")
    monkeypatch.setattr(profile_routes, "_service", lambda *_args: service)
    assert await profile_routes.get_farmer_profile(farmer(), MagicMock(), MagicMock()) == "farmer"
