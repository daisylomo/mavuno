from __future__ import annotations

import base64
import binascii
import hashlib
from decimal import Decimal
from typing import TypeVar
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from mavuno.api.errors import ApiError
from mavuno.auth.context import AuthenticatedUser
from mavuno.catalog.pagination import decode_cursor, encode_cursor
from mavuno.catalog.repository import CatalogRepository, FarmerFacts, Sort
from mavuno.catalog.schemas import (
    UPLOADED_IMAGE_PREFIX,
    CategoryCreate,
    FarmerPublicProfile,
    FarmerSummary,
    ImageCreate,
    ListingCreate,
    ListingPage,
    ListingResponse,
    ListingUpdate,
    PhotoUpload,
    ProductCreate,
)
from mavuno.db.models import (
    InventoryMovement,
    Listing,
    ListingImage,
    ListingImageContent,
    ProduceCategory,
    Product,
)

CatalogValue = TypeVar("CatalogValue", ProduceCategory, Product)


IMAGE_SIGNATURES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
}


class CatalogService:
    def __init__(self, repository: CatalogRepository, max_image_bytes: int = 1_500_000) -> None:
        self.repository = repository
        self.max_image_bytes = max_image_bytes
        self._farmers: dict[UUID, FarmerFacts] = {}

    async def create_category(self, payload: CategoryCreate) -> ProduceCategory:
        if (
            payload.parent_id is not None
            and await self.repository.get_category(payload.parent_id) is None
        ):
            raise ApiError(
                status_code=422,
                code="category_parent_not_found",
                message="Parent category was not found",
            )
        category = ProduceCategory(id=uuid4(), **payload.model_dump())
        return await self._insert_unique(category, "category_slug_unavailable")

    async def create_product(self, payload: ProductCreate) -> Product:
        if await self.repository.get_category(payload.category_id) is None:
            raise ApiError(
                status_code=422, code="category_not_found", message="Category was not found"
            )
        product = Product(id=uuid4(), **payload.model_dump())
        return await self._insert_unique(product, "product_slug_unavailable")

    async def create_listing(
        self, user: AuthenticatedUser, payload: ListingCreate
    ) -> ListingResponse:
        self._farmer(user)
        product = await self.repository.get_product(payload.product_id)
        if product is None:
            raise ApiError(
                status_code=422, code="product_not_found", message="Product was not found"
            )
        listing = Listing(
            id=uuid4(),
            farmer_id=user.id,
            status="draft",
            version=1,
            currency="KES",
            **payload.model_dump(),
        )
        self.repository.add(listing)
        await self.repository.flush()
        if listing.available_quantity > 0:
            self.repository.add(
                InventoryMovement(
                    id=uuid4(),
                    listing_id=listing.id,
                    actor_user_id=user.id,
                    movement_type="initial",
                    quantity_delta=listing.available_quantity,
                    resulting_quantity=listing.available_quantity,
                    reason="Initial listing quantity",
                )
            )
        await self.repository.commit()
        await self.repository.refresh(listing)
        return await self._response(listing)

    async def get_listing(self, listing_id: UUID) -> ListingResponse:
        listing = await self.repository.get_listing(listing_id)
        if listing is None or listing.status == "archived":
            raise ApiError(
                status_code=404, code="listing_not_found", message="Listing was not found"
            )
        return await self._response(listing)

    async def list_owned_listings(self, user: AuthenticatedUser) -> list[ListingResponse]:
        self._farmer(user)
        listings = await self.repository.list_owned_listings(user.id)
        return [await self._response(listing) for listing in listings]

    async def list_listings(
        self,
        *,
        search: str | None,
        category_slug: str | None,
        farmer_id: UUID | None,
        unit: str | None,
        min_price: Decimal | None,
        max_price: Decimal | None,
        sort: Sort,
        cursor_raw: str | None,
        limit: int,
    ) -> ListingPage:
        if min_price is not None and max_price is not None and min_price > max_price:
            raise ApiError(
                status_code=422,
                code="invalid_price_range",
                message="Minimum price cannot exceed maximum price",
            )
        try:
            cursor = decode_cursor(cursor_raw) if cursor_raw else None
        except ValueError as exc:
            raise ApiError(
                status_code=422, code="invalid_cursor", message="Listing cursor is invalid"
            ) from exc
        rows = await self.repository.list_listings(
            search=search,
            category_slug=category_slug,
            farmer_id=farmer_id,
            unit=unit,
            min_price=min_price,
            max_price=max_price,
            sort=sort,
            cursor=cursor,
            limit=limit,
        )
        has_more = len(rows) > limit
        visible = rows[:limit]
        await self._load_farmers({listing.farmer_id for listing in visible})
        items = [await self._response(listing) for listing in visible]
        next_cursor = None
        if has_more and visible:
            last = visible[-1]
            value = last.created_at if sort == "newest" else last.price_amount
            next_cursor = encode_cursor(value, last.id)
        return ListingPage(items=items, next_cursor=next_cursor)

    async def update_listing(
        self, user: AuthenticatedUser, listing_id: UUID, payload: ListingUpdate
    ) -> ListingResponse:
        self._farmer(user)
        listing = await self._owned(user, listing_id)
        changes = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
        start = changes.get("available_from", listing.available_from)
        end = changes.get("available_until", listing.available_until)
        if start is not None and end is not None and start > end:
            raise ApiError(
                status_code=422,
                code="invalid_availability_window",
                message="Availability window is invalid",
            )
        if changes.get("status") == "active" and listing.available_quantity <= 0:
            raise ApiError(
                status_code=409,
                code="listing_has_no_stock",
                message="A listing with no stock cannot be active",
            )
        if not await self.repository.optimistic_update(
            listing.id, payload.expected_version, changes
        ):
            await self.repository.rollback()
            raise ApiError(
                status_code=409,
                code="listing_version_conflict",
                message="Listing was changed by another request",
            )
        await self.repository.commit()
        updated = await self.repository.get_listing(listing.id)
        if updated is None:
            raise RuntimeError("Updated listing disappeared")
        return await self._response(updated)

    async def archive_listing(
        self, user: AuthenticatedUser, listing_id: UUID, expected_version: int
    ) -> None:
        self._farmer(user)
        listing = await self._owned(user, listing_id)
        if not await self.repository.optimistic_update(
            listing.id, expected_version, {"status": "archived"}
        ):
            await self.repository.rollback()
            raise ApiError(
                status_code=409,
                code="listing_version_conflict",
                message="Listing was changed by another request",
            )
        await self.repository.commit()

    async def change_inventory(
        self,
        user: AuthenticatedUser,
        listing_id: UUID,
        delta: Decimal,
        movement_type: str,
        reason: str,
    ) -> ListingResponse:
        self._farmer(user)
        listing = await self.repository.get_listing(listing_id, lock=True)
        if listing is None or listing.farmer_id != user.id or listing.status == "archived":
            raise ApiError(
                status_code=404, code="listing_not_found", message="Listing was not found"
            )
        result = listing.available_quantity + delta
        if result < 0:
            raise ApiError(
                status_code=409,
                code="insufficient_inventory",
                message="Inventory cannot become negative",
            )
        listing.available_quantity = result
        listing.version += 1
        if result == 0:
            listing.status = "sold_out"
        self.repository.add(
            InventoryMovement(
                id=uuid4(),
                listing_id=listing.id,
                actor_user_id=user.id,
                movement_type=movement_type,
                quantity_delta=delta,
                resulting_quantity=result,
                reason=reason,
            )
        )
        await self.repository.commit()
        await self.repository.refresh(listing)
        return await self._response(listing)

    async def add_image(
        self, user: AuthenticatedUser, listing_id: UUID, payload: ImageCreate
    ) -> ListingImage:
        self._farmer(user)
        await self._owned(user, listing_id)
        if payload.object_key.startswith(UPLOADED_IMAGE_PREFIX):
            raise ApiError(
                status_code=422,
                code="uploaded_key_reserved",
                message="Upload photo bytes through the photos endpoint",
            )
        image = ListingImage(id=uuid4(), listing_id=listing_id, **payload.model_dump())
        try:
            self.repository.add(image)
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ApiError(
                status_code=409,
                code="listing_image_conflict",
                message="Image key or order is already used",
            ) from exc
        await self.repository.refresh(image)
        return image

    async def add_photo(
        self, user: AuthenticatedUser, listing_id: UUID, payload: PhotoUpload
    ) -> ListingImage:
        """Store a farmer's own photograph of the produce, as uploaded from the app."""
        self._farmer(user)
        await self._owned(user, listing_id)
        try:
            content = base64.b64decode(payload.content_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ApiError(
                status_code=422, code="invalid_photo", message="Photo data is not valid base64"
            ) from exc
        if not content or len(content) > self.max_image_bytes:
            raise ApiError(
                status_code=413,
                code="photo_too_large",
                message=f"Photos must be smaller than {self.max_image_bytes // 1000} KB",
            )
        if not content.startswith(IMAGE_SIGNATURES[payload.content_type]) or (
            payload.content_type == "image/webp" and content[8:12] != b"WEBP"
        ):
            raise ApiError(
                status_code=422,
                code="invalid_photo",
                message="Photo content does not match its type",
            )
        image_id = uuid4()
        image = ListingImage(
            id=image_id,
            listing_id=listing_id,
            object_key=f"{UPLOADED_IMAGE_PREFIX}{image_id}",
            alt_text=payload.alt_text,
            sort_order=await self.repository.next_image_order(listing_id),
        )
        self.repository.add(image)
        await self.repository.flush()
        self.repository.add(
            ListingImageContent(
                image_id=image_id,
                content_type=payload.content_type,
                byte_size=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                content=content,
            )
        )
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ApiError(
                status_code=409,
                code="listing_image_conflict",
                message="Another photo was added at the same time; try again",
            ) from exc
        await self.repository.refresh(image)
        return image

    async def photo(self, image_id: UUID) -> ListingImageContent:
        content = await self.repository.image_content(image_id)
        if content is None:
            raise ApiError(status_code=404, code="photo_not_found", message="Photo was not found")
        return content

    async def farmer_profile(self, farmer_id: UUID) -> FarmerPublicProfile:
        await self._load_farmers({farmer_id})
        facts = self._farmers.get(farmer_id)
        if facts is None or facts.user.status != "active" or facts.farmer is None:
            raise ApiError(status_code=404, code="farmer_not_found", message="Farmer was not found")
        summary = self._summary(facts)
        farmer = facts.farmer
        return FarmerPublicProfile(
            **summary.model_dump(),
            bio=facts.profile.bio if facts.profile else None,
            farm_size_acres=farmer.farm_size_acres,
            farming_since_year=farmer.farming_since_year,
            delivery_radius_km=farmer.delivery_radius_km,
            categories=await self.repository.farmer_categories(farmer_id),
            cancelled_handovers=await self.repository.farmer_cancellations(farmer_id),
        )

    async def delete_image(self, user: AuthenticatedUser, listing_id: UUID, image_id: UUID) -> None:
        self._farmer(user)
        await self._owned(user, listing_id)
        image = await self.repository.get_image(image_id)
        if image is None or image.listing_id != listing_id:
            raise ApiError(
                status_code=404,
                code="listing_image_not_found",
                message="Listing image was not found",
            )
        await self.repository.delete_image(image)
        await self.repository.commit()

    async def _owned(self, user: AuthenticatedUser, listing_id: UUID) -> Listing:
        listing = await self.repository.get_listing(listing_id)
        if listing is None or listing.farmer_id != user.id or listing.status == "archived":
            raise ApiError(
                status_code=404, code="listing_not_found", message="Listing was not found"
            )
        return listing

    async def _load_farmers(self, farmer_ids: set[UUID]) -> None:
        missing = farmer_ids - set(self._farmers)
        if missing:
            self._farmers.update(await self.repository.farmer_facts(missing))

    @staticmethod
    def _summary(facts: FarmerFacts) -> FarmerSummary:
        profile, farmer = facts.profile, facts.farmer
        return FarmerSummary(
            id=facts.user.id,
            display_name=profile.display_name if profile else "Mavuno farmer",
            farm_name=farmer.farm_name if farmer else None,
            county=farmer.county if farmer else None,
            locality=farmer.locality if farmer else None,
            verification_status=farmer.verification_status if farmer else "unverified",
            member_since=facts.user.created_at,
            active_listings=facts.active_listings,
            completed_orders=facts.completed_orders,
            offers_pickup=farmer.offers_pickup if farmer else True,
            offers_delivery=farmer.offers_delivery if farmer else False,
            farming_practices=farmer.farming_practices if farmer else None,
        )

    async def _response(self, listing: Listing) -> ListingResponse:
        product, category, images = await self.repository.listing_context(listing)
        await self._load_farmers({listing.farmer_id})
        facts = self._farmers.get(listing.farmer_id)
        return ListingResponse(
            id=listing.id,
            farmer_id=listing.farmer_id,
            product_id=listing.product_id,
            product_name=product.name,
            category_slug=category.slug,
            title=listing.title,
            description=listing.description,
            price_amount=listing.price_amount,
            currency=listing.currency,
            available_quantity=listing.available_quantity,
            quantity_unit=listing.quantity_unit,
            harvest_date=listing.harvest_date,
            available_from=listing.available_from,
            available_until=listing.available_until,
            status=listing.status,
            version=listing.version,
            images=images,
            created_at=listing.created_at,
            updated_at=listing.updated_at,
            farmer=self._summary(facts) if facts is not None else None,
        )

    async def _insert_unique(self, value: CatalogValue, code: str) -> CatalogValue:
        try:
            self.repository.add(value)
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ApiError(
                status_code=409, code=code, message="The slug is already in use"
            ) from exc
        await self.repository.refresh(value)
        return value

    @staticmethod
    def _farmer(user: AuthenticatedUser) -> None:
        if "farmer" not in user.roles:
            raise ApiError(
                status_code=403, code="farmer_role_required", message="The farmer role is required"
            )
