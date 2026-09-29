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


class RefundResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    payment_id: UUID
    order_id: UUID
    farmer_id: UUID | None
    amount: Decimal
    currency: str
    reason: str
    state: str
    provider_ref: str | None
    operator_note: str | None
    created_at: datetime
    completed_at: datetime | None


class OrderResponse(BaseModel):
    id: UUID
    buyer_id: UUID
    status: str
    currency: str
    subtotal_amount: Decimal
    # What M-PESA charges: the subtotal rounded down to whole shillings.
    total_amount: Decimal
    reservation_expires_at: datetime
    paid_at: datetime | None
    items: list[OrderItemResponse]
    created_at: datetime
    refunds: list[RefundResponse] = Field(default_factory=list)


class OrderCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=255)


class RefundCompletion(BaseModel):
    reference: str = Field(min_length=3, max_length=128)
    note: str | None = Field(default=None, max_length=255)


class FarmerOrderResponse(BaseModel):
    id: UUID
    order_number: str
    customer_name: str
    # Contact details are only shared once the order is paid.
    customer_phone: str | None
    delivery_location: str | None
    items: list[OrderItemResponse]
    # Only this farmer's share of the order.
    total_amount: Decimal
    status: str
    created_at: datetime
    reservation_expires_at: datetime | None = None
    fulfilment_status: str | None = None
    fulfilment_version: int | None = None
    other_farmers: int = 0


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
    provider_transaction_ref: str | None = None
    failure_code: str | None
    failure_message: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
