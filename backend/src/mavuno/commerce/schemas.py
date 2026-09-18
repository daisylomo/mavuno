from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CartItemUpsert(BaseModel):
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)


class CartItemResponse(BaseModel):
    listing_id: UUID
    title: str
    quantity: Decimal
    quantity_unit: str
    unit_price: Decimal
    line_total: Decimal
    available_quantity: Decimal


class CartResponse(BaseModel):
    id: UUID
    items: list[CartItemResponse]
    subtotal_amount: Decimal
    currency: Literal["KES"] = "KES"


class CheckoutRequest(BaseModel):
    delivery_address_id: UUID | None = None


class OrderItemResponse(BaseModel):
    listing_id: UUID
    farmer_id: UUID
    product_name: str
    listing_title: str
    quantity: Decimal
    quantity_unit: str
    unit_price: Decimal
    line_total: Decimal


class OrderResponse(BaseModel):
    id: UUID
    buyer_id: UUID
    status: str
    currency: str
    subtotal_amount: Decimal
    total_amount: Decimal
    reservation_expires_at: datetime
    paid_at: datetime | None
    items: list[OrderItemResponse]
    created_at: datetime


class PaymentInitiateRequest(BaseModel):
    order_id: UUID
    rail: Literal["mpesa", "bank"]
    phone_e164: str | None = Field(default=None, min_length=10, max_length=16)


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    rail: str
    provider: str
    amount: Decimal
    currency: str
    state: str
    provider_request_ref: str | None
    failure_code: str | None
    created_at: datetime
