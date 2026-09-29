from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional

FulfilmentMethod = Literal["pickup", "delivery"]
FulfilmentStatus = Literal[
    "pending", "scheduled", "ready_for_handover", "in_transit", "completed", "cancelled"
]


# --- Request Models ---

@dataclass
class FulfilmentUpdate:
    method: Optional[FulfilmentMethod] = None
    location_label: Optional[str] = None
    location_details: Optional[str] = None
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    coordination_notes: Optional[str] = None
    expected_version: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        for key in ("latitude", "longitude"):
            if data.get(key) is not None:
                data[key] = str(data[key])
        return {k: v for k, v in data.items() if v is not None}


@dataclass
class FulfilmentTransition:
    status: FulfilmentStatus
    expected_version: int
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


# --- Response Models ---

@dataclass
class FulfilmentHistoryEntry:
    actor_user_id: str
    new_status: str
    previous_status: Optional[str] = None
    reason: Optional[str] = None
    created_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FulfilmentHistoryEntry":
        return cls(
            actor_user_id=str(data.get("actor_user_id", "")),
            new_status=data.get("new_status", ""),
            previous_status=data.get("previous_status"),
            reason=data.get("reason"),
            created_at=data.get("created_at"),
        )


@dataclass
class FulfilmentResponse:
    id: str
    order_id: str
    method: str
    status: FulfilmentStatus
    location_label: str
    location_details: str
    version: int
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    coordination_notes: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    history: Optional[List[FulfilmentHistoryEntry]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FulfilmentResponse":
        raw_history = data.get("history") or []
        return cls(
            id=str(data.get("id", "")),
            order_id=str(data.get("order_id", "")),
            method=data.get("method", "delivery"),
            status=data.get("status", "pending"),
            location_label=data.get("location_label", ""),
            location_details=data.get("location_details", ""),
            version=int(data.get("version", 1)),
            latitude=Decimal(str(data["latitude"])) if data.get("latitude") is not None else None,
            longitude=Decimal(str(data["longitude"])) if data.get("longitude") is not None else None,
            window_start=data.get("window_start"),
            window_end=data.get("window_end"),
            coordination_notes=data.get("coordination_notes"),
            completed_at=data.get("completed_at"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            history=[FulfilmentHistoryEntry.from_dict(h) for h in raw_history],
        )
