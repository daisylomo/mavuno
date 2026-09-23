from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional


# --- Request Models ---

@dataclass
class CartItemUpsert:
    quantity: Decimal

    def to_dict(self) -> Dict[str, Any]:
        return {"quantity": str(self.quantity)}


@dataclass
class CheckoutRequest:
    delivery_address_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"delivery_address_id": self.delivery_address_id} if self.delivery_address_id else {}


@dataclass
class PaymentInitiateRequest:
    order_id: str
    rail: Literal["mpesa", "bank"]
    phone_e164: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"order_id": self.order_id, "rail": self.rail}
        if self.phone_e164 is not None:
            data["phone_e164"] = self.phone_e164
        return data


# --- Response Models ---

@dataclass
class CartItemResponse:
    listing_id: str
    title: str
    quantity: Decimal
    quantity_unit: str
    unit_price: Decimal
    line_total: Decimal
    available_quantity: Decimal

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CartItemResponse":
        return cls(
            listing_id=str(data.get("listing_id", "")),
            title=data.get("title", ""),
            quantity=Decimal(str(data.get("quantity", "0"))),
            quantity_unit=data.get("quantity_unit", "kg"),
            unit_price=Decimal(str(data.get("unit_price", "0"))),
            line_total=Decimal(str(data.get("line_total", "0"))),
            available_quantity=Decimal(str(data.get("available_quantity", "0"))),
        )


@dataclass
class CartResponse:
    id: str
    items: List[CartItemResponse]
    subtotal_amount: Decimal
    currency: str = "KES"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CartResponse":
        raw_items = data.get("items") or []
        return cls(
            id=str(data.get("id", "")),
            items=[CartItemResponse.from_dict(item) for item in raw_items],
            subtotal_amount=Decimal(str(data.get("subtotal_amount", "0"))),
            currency=data.get("currency", "KES"),
        )


@dataclass
class OrderItemResponse:
    listing_id: str
    farmer_id: str
    product_name: str
    listing_title: str
    quantity: Decimal
    quantity_unit: str
    unit_price: Decimal
    line_total: Decimal

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OrderItemResponse":
        return cls(
            listing_id=str(data.get("listing_id", "")),
            farmer_id=str(data.get("farmer_id", "")),
            product_name=data.get("product_name", ""),
            listing_title=data.get("listing_title", ""),
            quantity=Decimal(str(data.get("quantity", "0"))),
            quantity_unit=data.get("quantity_unit", "kg"),
            unit_price=Decimal(str(data.get("unit_price", "0"))),
            line_total=Decimal(str(data.get("line_total", "0"))),
        )


@dataclass
class OrderResponse:
    id: str
    buyer_id: str
    status: str
    currency: str
    subtotal_amount: Decimal
    total_amount: Decimal
    reservation_expires_at: Optional[str]
    paid_at: Optional[str]
    items: List[OrderItemResponse]
    created_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OrderResponse":
        raw_items = data.get("items") or []
        return cls(
            id=str(data.get("id", "")),
            buyer_id=str(data.get("buyer_id", "")),
            status=data.get("status", "pending_payment"),
            currency=data.get("currency", "KES"),
            subtotal_amount=Decimal(str(data.get("subtotal_amount", "0"))),
            total_amount=Decimal(str(data.get("total_amount", "0"))),
            reservation_expires_at=data.get("reservation_expires_at"),
            paid_at=data.get("paid_at"),
            items=[OrderItemResponse.from_dict(item) for item in raw_items],
            created_at=data.get("created_at"),
        )


@dataclass
class PaymentResponse:
    id: str
    order_id: str
    rail: str
    provider: str
    amount: Decimal
    currency: str
    state: str
    provider_request_ref: Optional[str] = None
    failure_code: Optional[str] = None
    created_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PaymentResponse":
        return cls(
            id=str(data.get("id", "")),
            order_id=str(data.get("order_id", "")),
            rail=data.get("rail", ""),
            provider=data.get("provider", ""),
            amount=Decimal(str(data.get("amount", "0"))),
            currency=data.get("currency", "KES"),
            state=data.get("state", "pending"),
            provider_request_ref=data.get("provider_request_ref"),
            failure_code=data.get("failure_code"),
            created_at=data.get("created_at"),
        )
