from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional

PrebookingStatus = Literal["pending", "accepted", "rejected", "fulfilled", "cancelled"]
PlanFeature = Literal["prebooking", "insights"]
PlanAudience = Literal["buyer", "farmer"]
QuantityUnit = Literal["kg", "g", "crate", "piece", "bunch", "bag"]


# --- Request Models ---

@dataclass
class PlanCreate:
    code: str
    name: str
    audience: PlanAudience
    price_amount: Decimal
    billing_interval: Literal["month", "year"]
    features: List[PlanFeature]
    currency: str = "KES"

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["price_amount"] = str(self.price_amount)
        return data


@dataclass
class SubscriptionCreate:
    plan_id: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PrebookingCreate:
    farmer_id: str
    product_id: str
    quantity: Decimal
    quantity_unit: QuantityUnit
    window_start: str
    window_end: str
    listing_id: Optional[str] = None
    target_price: Optional[Decimal] = None
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["quantity"] = str(self.quantity)
        if self.target_price is not None:
            data["target_price"] = str(self.target_price)
        return {k: v for k, v in data.items() if v is not None}


@dataclass
class PrebookingTransition:
    status: Literal["accepted", "rejected", "cancelled", "fulfilled"]
    expected_version: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --- Response Models ---

@dataclass
class PlanResponse:
    id: str
    code: str
    name: str
    audience: str
    price_amount: Decimal
    currency: str
    billing_interval: str
    features: List[str]
    active: bool

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlanResponse":
        return cls(
            id=str(data.get("id", "")),
            code=data.get("code", ""),
            name=data.get("name", ""),
            audience=data.get("audience", ""),
            price_amount=Decimal(str(data.get("price_amount", "0"))),
            currency=data.get("currency", "KES"),
            billing_interval=data.get("billing_interval", "month"),
            features=data.get("features", []),
            active=data.get("active", True),
        )


@dataclass
class SubscriptionResponse:
    id: str
    plan_id: str
    status: str
    provider: str
    account_reference: str
    current_period_start: Optional[str] = None
    current_period_end: Optional[str] = None
    verified_at: Optional[str] = None
    created_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubscriptionResponse":
        return cls(
            id=str(data.get("id", "")),
            plan_id=str(data.get("plan_id", "")),
            status=data.get("status", "pending"),
            provider=data.get("provider", ""),
            account_reference=data.get("account_reference", ""),
            current_period_start=data.get("current_period_start"),
            current_period_end=data.get("current_period_end"),
            verified_at=data.get("verified_at"),
            created_at=data.get("created_at"),
        )


@dataclass
class PrebookingResponse:
    id: str
    buyer_id: str
    farmer_id: str
    product_id: str
    status: PrebookingStatus
    quantity: Decimal
    quantity_unit: str
    currency: str
    version: int
    listing_id: Optional[str] = None
    target_price: Optional[Decimal] = None
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PrebookingResponse":
        return cls(
            id=str(data.get("id", "")),
            buyer_id=str(data.get("buyer_id", "")),
            farmer_id=str(data.get("farmer_id", "")),
            product_id=str(data.get("product_id", "")),
            status=data.get("status", "pending"),
            quantity=Decimal(str(data.get("quantity", "0"))),
            quantity_unit=data.get("quantity_unit", "kg"),
            currency=data.get("currency", "KES"),
            version=int(data.get("version", 1)),
            listing_id=data.get("listing_id"),
            target_price=Decimal(str(data["target_price"])) if data.get("target_price") is not None else None,
            window_start=data.get("window_start"),
            window_end=data.get("window_end"),
            notes=data.get("notes"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class FarmerInsightsResponse:
    active_listings: int
    units_available: Decimal
    completed_order_lines: int
    gross_sales: Decimal

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FarmerInsightsResponse":
        return cls(
            active_listings=int(data.get("active_listings", 0)),
            units_available=Decimal(str(data.get("units_available", "0"))),
            completed_order_lines=int(data.get("completed_order_lines", 0)),
            gross_sales=Decimal(str(data.get("gross_sales", "0"))),
        )
