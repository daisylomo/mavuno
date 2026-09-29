from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Trimmed = Annotated[str, StringConstraints(strip_whitespace=True)]
Unit = Literal["kg", "g", "crate", "piece", "bunch", "bag"]
ListingStatus = Literal["draft", "active", "paused", "sold_out", "archived"]


class CategoryCreate(BaseModel):
    name: Annotated[Trimmed, Field(min_length=2, max_length=120)]
    slug: Annotated[Trimmed, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)]
    parent_id: UUID | None = None


class CategoryResponse(CategoryCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class ProductCreate(BaseModel):
    category_id: UUID
    name: Annotated[Trimmed, Field(min_length=2, max_length=160)]
    slug: Annotated[Trimmed, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=160)]
    default_unit: Unit


class ProductResponse(ProductCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


def _whole_shillings(value: Decimal | None) -> Decimal | None:
    if value is not None and value != value.to_integral_value():
        raise ValueError("Prices must be whole shillings; M-PESA cannot charge cents")
    return value


class ListingCreate(BaseModel):
    product_id: UUID
    title: Annotated[Trimmed, Field(min_length=3, max_length=180)]
    description: Annotated[Trimmed, Field(max_length=5000)] | None = None
    price_amount: Decimal = Field(gt=0, max_digits=19, decimal_places=4)
    available_quantity: Decimal = Field(ge=0, max_digits=14, decimal_places=3)
    quantity_unit: Unit
    harvest_date: date | None = None
    available_from: date | None = None
    available_until: date | None = None

    @model_validator(mode="after")
    def valid_window(self) -> ListingCreate:
        _whole_shillings(self.price_amount)
        if (
            self.available_from is not None
            and self.available_until is not None
            and self.available_from > self.available_until
        ):
            raise ValueError("available_from must not be after available_until")
        return self


class ListingUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    title: Annotated[Trimmed, Field(min_length=3, max_length=180)] | None = None
    description: Annotated[Trimmed, Field(max_length=5000)] | None = None
    price_amount: Decimal | None = Field(default=None, gt=0, max_digits=19, decimal_places=4)
    harvest_date: date | None = None
    available_from: date | None = None
    available_until: date | None = None
    status: ListingStatus | None = None

    @model_validator(mode="after")
    def has_changes(self) -> ListingUpdate:
        if self.model_fields_set == {"expected_version"}:
            raise ValueError("At least one listing field is required")
        _whole_shillings(self.price_amount)
        for field in ("title", "price_amount", "status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        if (
            "available_from" in self.model_fields_set
            and "available_until" in self.model_fields_set
            and self.available_from is not None
            and self.available_until is not None
            and self.available_from > self.available_until
        ):
            raise ValueError("available_from must not be after available_until")
        return self


class ImageCreate(BaseModel):
    object_key: Annotated[Trimmed, Field(min_length=1, max_length=512)]
    alt_text: Annotated[Trimmed, Field(max_length=255)] | None = None
    sort_order: int = Field(ge=0, le=99)

    @model_validator(mode="after")
    def relative_key(self) -> ImageCreate:
        key = self.object_key
        if "://" in key or key.startswith(("/", "\\")) or "\\" in key or ".." in key.split("/"):
            raise ValueError("object_key must be a relative object-storage key")
        return self


UPLOADED_IMAGE_PREFIX = "uploads/"
PRESET_IMAGE_PREFIX = "preset/"


class ImageResponse(ImageCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    # Where a photo uploaded from the app is served, relative to the API root. Preset keys
    # ("preset/tomatoes") name an illustration bundled with the app and have no URL.
    url: str | None = None

    @model_validator(mode="after")
    def served_url(self) -> ImageResponse:
        if self.url is None and self.object_key.startswith(UPLOADED_IMAGE_PREFIX):
            self.url = f"/api/v1/listing-images/{self.id}"
        return self


class PhotoUpload(BaseModel):
    content_type: Literal["image/jpeg", "image/png", "image/webp"]
    # Base64 of the image bytes (no data: prefix). The app resizes photos before upload.
    content_base64: str = Field(min_length=16, max_length=11_000_000)
    alt_text: Annotated[Trimmed, Field(max_length=255)] | None = None


class FarmerSummary(BaseModel):
    """What a buyer sees about the farmer behind a listing."""

    id: UUID
    display_name: str
    farm_name: str | None
    county: str | None
    locality: str | None
    verification_status: str
    member_since: datetime
    active_listings: int
    completed_orders: int
    offers_pickup: bool
    offers_delivery: bool
    # As stated by the farmer; Mavuno does not certify farming practices.
    farming_practices: str | None


class FarmerPublicProfile(FarmerSummary):
    bio: str | None
    farm_size_acres: Decimal | None
    farming_since_year: int | None
    delivery_radius_km: int | None
    categories: list[str]
    # Hand-overs for this farmer's items that were called off, by anyone.
    cancelled_handovers: int


class InventoryChange(BaseModel):
    quantity_delta: Decimal = Field(max_digits=14, decimal_places=3)
    movement_type: Literal["restock", "adjustment"]
    reason: Annotated[Trimmed, Field(min_length=2, max_length=255)]

    @model_validator(mode="after")
    def nonzero(self) -> InventoryChange:
        if self.quantity_delta == 0:
            raise ValueError("quantity_delta cannot be zero")
        return self


class ListingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    farmer_id: UUID
    product_id: UUID
    product_name: str
    category_slug: str
    title: str
    description: str | None
    price_amount: Decimal
    currency: str
    available_quantity: Decimal
    quantity_unit: str
    harvest_date: date | None
    available_from: date | None
    available_until: date | None
    status: str
    version: int
    images: list[ImageResponse]
    created_at: datetime
    updated_at: datetime
    farmer: FarmerSummary | None = None


class ListingPage(BaseModel):
    items: list[ListingResponse]
    next_cursor: str | None
