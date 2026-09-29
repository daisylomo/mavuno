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


class ImageResponse(ImageCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


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


class ListingPage(BaseModel):
    items: list[ListingResponse]
    next_cursor: str | None
