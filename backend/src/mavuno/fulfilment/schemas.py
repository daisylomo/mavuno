from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

FulfilmentMethod = Literal["pickup", "delivery"]
FulfilmentStatus = Literal[
    "pending", "scheduled", "ready_for_handover", "in_transit", "completed", "cancelled"
]


class FulfilmentUpdate(BaseModel):
    method: FulfilmentMethod | None = None
    location_label: str | None = Field(default=None, min_length=1, max_length=120)
    location_details: str | None = Field(default=None, min_length=1, max_length=500)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90, decimal_places=7)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180, decimal_places=7)
    window_start: datetime | None = None
    window_end: datetime | None = None
    coordination_notes: str | None = Field(default=None, max_length=2000)
    expected_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def paired_coordinates(self) -> FulfilmentUpdate:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be supplied together")
        return self


class FulfilmentTransition(BaseModel):
    status: FulfilmentStatus
    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=255)


class FulfilmentHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    actor_user_id: UUID
    previous_status: str | None
    new_status: str
    reason: str | None
    created_at: datetime


class FulfilmentResponse(BaseModel):
    id: UUID
    order_id: UUID
    method: str
    status: str
    location_label: str
    location_details: str
    latitude: Decimal | None
    longitude: Decimal | None
    window_start: datetime
    window_end: datetime
    coordination_notes: str | None
    version: int
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    history: list[FulfilmentHistoryResponse]
