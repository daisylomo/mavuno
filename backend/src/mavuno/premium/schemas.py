from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class PlanCreate(BaseModel):
    code: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=2, max_length=120)
    audience: Literal["buyer", "farmer"]
    price_amount: Decimal = Field(ge=0, max_digits=19, decimal_places=4)
    currency: Literal["KES"] = "KES"
    billing_interval: Literal["month", "year"]
    features: list[Literal["prebooking", "insights"]] = Field(min_length=1)


class PlanResponse(PlanCreate):
    id: UUID
    active: bool

    model_config = {"from_attributes": True}


class SubscriptionCreate(BaseModel):
    plan_id: UUID


class SubscriptionResponse(BaseModel):
    id: UUID
    plan_id: UUID
    status: str
    provider: str
    account_reference: str
    current_period_start: datetime | None
    current_period_end: datetime | None
    verified_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PrebookingCreate(BaseModel):
    farmer_id: UUID
    product_id: UUID
    listing_id: UUID | None = None
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    quantity_unit: Literal["kg", "g", "crate", "piece", "bunch", "bag"]
    target_price: Decimal | None = Field(default=None, ge=0, max_digits=19, decimal_places=4)
    window_start: datetime
    window_end: datetime
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_window(self) -> PrebookingCreate:
        if self.window_end <= self.window_start:
            raise ValueError("window_end must follow window_start")
        return self


class PrebookingTransition(BaseModel):
    status: Literal["accepted", "rejected", "cancelled", "fulfilled"]
    expected_version: int = Field(ge=1)


class PrebookingResponse(BaseModel):
    id: UUID
    buyer_id: UUID
    farmer_id: UUID
    product_id: UUID
    listing_id: UUID | None
    status: str
    quantity: Decimal
    quantity_unit: str
    target_price: Decimal | None
    currency: str
    window_start: datetime
    window_end: datetime
    notes: str | None
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FarmerInsightsResponse(BaseModel):
    active_listings: int
    units_available: Decimal
    completed_order_lines: int
    gross_sales: Decimal
