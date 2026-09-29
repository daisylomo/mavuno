from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional

ListingUnit = Literal["kg", "g", "crate", "piece", "bunch", "bag"]
ListingSort = Literal["newest", "price_asc", "price_desc"]
ListingStatus = Literal["draft", "active", "paused", "sold_out", "archived"]


# --- Request Objects ---

@dataclass
class ListingFilterRequest:
    search: Optional[str] = None
    category: Optional[str] = None
    farmer_id: Optional[str] = None
    unit: Optional[ListingUnit] = None
    min_price: Optional[Decimal] = None
    max_price: Optional[Decimal] = None
    sort: ListingSort = "newest"
    cursor: Optional[str] = None
    limit: int = 20

    def to_params(self) -> Dict[str, Any]:
        params = {}
        for k, v in asdict(self).items():
            if v is not None:
                if isinstance(v, Decimal):
                    params[k] = str(v)
                else:
                    params[k] = v
        return params


@dataclass
class ListingCreateRequest:
    product_id: str
    title: str
    price_amount: Decimal
    available_quantity: Decimal
    quantity_unit: ListingUnit
    description: Optional[str] = None
    harvest_date: Optional[date] = None
    available_from: Optional[date] = None
    available_until: Optional[date] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["price_amount"] = str(self.price_amount)
        data["available_quantity"] = str(self.available_quantity)
        for key in ("harvest_date", "available_from", "available_until"):
            if data.get(key) is not None:
                data[key] = data[key].isoformat()
        return {k: v for k, v in data.items() if v is not None}


@dataclass
class ListingUpdateRequest:
    expected_version: int
    title: Optional[str] = None
    description: Optional[str] = None
    price_amount: Optional[Decimal] = None
    harvest_date: Optional[date] = None
    available_from: Optional[date] = None
    available_until: Optional[date] = None
    status: Optional[ListingStatus] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if self.price_amount is not None:
            data["price_amount"] = str(self.price_amount)
        for key in ("harvest_date", "available_from", "available_until"):
            if data.get(key) is not None:
                data[key] = data[key].isoformat()
        return {k: v for k, v in data.items() if v is not None}


@dataclass
class InventoryChangeRequest:
    quantity_delta: Decimal
    movement_type: Literal["restock", "adjustment"]
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quantity_delta": str(self.quantity_delta),
            "movement_type": self.movement_type,
            "reason": self.reason,
        }


# --- Response Objects ---

@dataclass
class ImageResponse:
    id: str
    object_key: str
    sort_order: int
    alt_text: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ImageResponse":
        return cls(
            id=str(data.get("id", "")),
            object_key=data.get("object_key", ""),
            sort_order=int(data.get("sort_order", 0)),
            alt_text=data.get("alt_text"),
        )


@dataclass
class ListingResponse:
    id: str
    farmer_id: str
    product_id: str
    product_name: str
    category_slug: str
    title: str
    price_amount: Decimal
    currency: str
    available_quantity: Decimal
    quantity_unit: str
    status: str
    version: int
    description: Optional[str] = None
    harvest_date: Optional[str] = None
    available_from: Optional[str] = None
    available_until: Optional[str] = None
    images: Optional[List[ImageResponse]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ListingResponse":
        raw_images = data.get("images") or []
        return cls(
            id=str(data.get("id", "")),
            farmer_id=str(data.get("farmer_id", "")),
            product_id=str(data.get("product_id", "")),
            product_name=data.get("product_name", ""),
            category_slug=data.get("category_slug", ""),
            title=data.get("title", ""),
            price_amount=Decimal(str(data.get("price_amount", "0"))),
            currency=data.get("currency", "KES"),
            available_quantity=Decimal(str(data.get("available_quantity", "0"))),
            quantity_unit=data.get("quantity_unit", "kg"),
            status=data.get("status", "draft"),
            version=int(data.get("version", 1)),
            description=data.get("description"),
            harvest_date=data.get("harvest_date"),
            available_from=data.get("available_from"),
            available_until=data.get("available_until"),
            images=[ImageResponse.from_dict(img) for img in raw_images],
        )


@dataclass
class ListingPage:
    items: List[ListingResponse]
    next_cursor: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ListingPage":
        raw_items = data.get("items") or []
        return cls(
            items=[ListingResponse.from_dict(item) for item in raw_items],
            next_cursor=data.get("next_cursor"),
        )
