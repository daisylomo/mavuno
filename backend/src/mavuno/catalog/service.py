from __future__ import annotations

from decimal import Decimal
from typing import TypeVar
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from mavuno.api.errors import ApiError
from mavuno.auth.context import AuthenticatedUser
from mavuno.catalog.pagination import decode_cursor, encode_cursor
from mavuno.catalog.repository import CatalogRepository, Sort
from mavuno.catalog.schemas import (
    CategoryCreate,
    ImageCreate,
    ListingCreate,
    ListingPage,
    ListingResponse,
    ListingUpdate,
    ProductCreate,
)
from mavuno.db.models import InventoryMovement, Listing, ListingImage, ProduceCategory, Product

CatalogValue = TypeVar("CatalogValue", ProduceCategory, Product)


class CatalogService:
    def __init__(self, repository: CatalogRepository) -> None:
        self.repository = repository

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

    async def _response(self, listing: Listing) -> ListingResponse:
        product, category, images = await self.repository.listing_context(listing)
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
