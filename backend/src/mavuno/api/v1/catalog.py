from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from mavuno.api.dependencies import CurrentUser, DatabaseSession, require_roles
from mavuno.auth.context import AuthenticatedUser
from mavuno.catalog.repository import CatalogRepository
from mavuno.catalog.schemas import (
    CategoryCreate,
    CategoryResponse,
    ImageCreate,
    ImageResponse,
    InventoryChange,
    ListingCreate,
    ListingPage,
    ListingResponse,
    ListingUpdate,
    ProductCreate,
    ProductResponse,
)
from mavuno.catalog.service import CatalogService

router = APIRouter(tags=["catalog"])
AdminUser = Annotated[AuthenticatedUser, Depends(require_roles("administrator"))]


def _service(session: DatabaseSession) -> CatalogService:
    return CatalogService(CatalogRepository(session))


@router.get("/catalog/categories", response_model=list[CategoryResponse])
async def categories(session: DatabaseSession, response: Response) -> object:
    response.headers["Cache-Control"] = "public, max-age=300"
    return await CatalogRepository(session).list_categories()


@router.post("/catalog/categories", response_model=CategoryResponse, status_code=201)
async def create_category(
    payload: CategoryCreate, _: AdminUser, session: DatabaseSession
) -> object:
    return await _service(session).create_category(payload)


@router.get("/catalog/products", response_model=list[ProductResponse])
async def products(
    session: DatabaseSession, response: Response, category_id: UUID | None = None
) -> object:
    response.headers["Cache-Control"] = "public, max-age=300"
    return await CatalogRepository(session).list_products(category_id)


@router.post("/catalog/products", response_model=ProductResponse, status_code=201)
async def create_product(payload: ProductCreate, _: AdminUser, session: DatabaseSession) -> object:
    return await _service(session).create_product(payload)


@router.get("/listings", response_model=ListingPage)
async def list_listings(
    session: DatabaseSession,
    response: Response,
    search: str | None = Query(default=None, min_length=2, max_length=120),
    category: str | None = Query(default=None, max_length=120),
    farmer_id: UUID | None = None,
    unit: Literal["kg", "g", "crate", "piece", "bunch", "bag"] | None = None,
    min_price: Annotated[Decimal | None, Query(ge=0)] = None,
    max_price: Annotated[Decimal | None, Query(ge=0)] = None,
    sort: Literal["newest", "price_asc", "price_desc"] = "newest",
    cursor: str | None = Query(default=None, max_length=512),
    limit: int = Query(default=20, ge=1, le=100),
) -> ListingPage:
    page = await _service(session).list_listings(
        search=search,
        category_slug=category,
        farmer_id=farmer_id,
        unit=unit,
        min_price=min_price,
        max_price=max_price,
        sort=sort,
        cursor_raw=cursor,
        limit=limit,
    )
    response.headers["Cache-Control"] = "public, max-age=30, stale-while-revalidate=60"
    digest = hashlib.sha256(
        "|".join(f"{item.id}:{item.version}" for item in page.items).encode()
    ).hexdigest()[:24]
    response.headers["ETag"] = f'"{digest}"'
    return page


@router.post("/listings", response_model=ListingResponse, status_code=status.HTTP_201_CREATED)
async def create_listing(
    payload: ListingCreate, current_user: CurrentUser, session: DatabaseSession
) -> ListingResponse:
    return await _service(session).create_listing(current_user, payload)


@router.get("/listings/{listing_id}", response_model=ListingResponse)
async def get_listing(
    listing_id: UUID, request: Request, response: Response, session: DatabaseSession
) -> ListingResponse | Response:
    listing = await _service(session).get_listing(listing_id)
    etag = f'"listing-{listing.id}-{listing.version}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    response.headers["Cache-Control"] = "public, max-age=30, stale-while-revalidate=60"
    response.headers["ETag"] = etag
    return listing


@router.patch("/listings/{listing_id}", response_model=ListingResponse)
async def update_listing(
    listing_id: UUID,
    payload: ListingUpdate,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> ListingResponse:
    return await _service(session).update_listing(current_user, listing_id, payload)


@router.delete("/listings/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_listing(
    listing_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
    expected_version: int = Query(ge=1),
) -> Response:
    await _service(session).archive_listing(current_user, listing_id, expected_version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/listings/{listing_id}/inventory", response_model=ListingResponse)
async def change_inventory(
    listing_id: UUID,
    payload: InventoryChange,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> ListingResponse:
    return await _service(session).change_inventory(
        current_user, listing_id, payload.quantity_delta, payload.movement_type, payload.reason
    )


@router.post(
    "/listings/{listing_id}/images",
    response_model=ImageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_image(
    listing_id: UUID,
    payload: ImageCreate,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> object:
    return await _service(session).add_image(current_user, listing_id, payload)


@router.delete("/listings/{listing_id}/images/{image_id}", status_code=204)
async def delete_image(
    listing_id: UUID,
    image_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> Response:
    await _service(session).delete_image(current_user, listing_id, image_id)
    return Response(status_code=204)
