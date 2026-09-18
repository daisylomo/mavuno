from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

Trimmed = Annotated[str, StringConstraints(strip_whitespace=True)]


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    display_name: str
    avatar_object_key: str | None
    locale: str
    bio: str | None
    created_at: datetime
    updated_at: datetime


class ProfileUpdate(BaseModel):
    display_name: Annotated[Trimmed, Field(min_length=2, max_length=120)] | None = None
    avatar_object_key: Annotated[Trimmed, Field(min_length=1, max_length=512)] | None = None
    locale: Annotated[Trimmed, Field(pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$", max_length=16)] | None = (
        None
    )
    bio: Annotated[Trimmed, Field(max_length=2000)] | None = None

    @field_validator("avatar_object_key")
    @classmethod
    def avatar_is_an_object_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if "://" in value or value.startswith(("/", "\\")) or ".." in value.split("/"):
            raise ValueError("avatar_object_key must be a relative object-storage key")
        return value

    @model_validator(mode="after")
    def at_least_one_field(self) -> ProfileUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one profile field is required")
        for field in ("display_name", "locale"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class FarmerProfileUpdate(BaseModel):
    farm_name: Annotated[Trimmed, Field(max_length=160)] | None = None
    county: Annotated[Trimmed, Field(max_length=80)] | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> FarmerProfileUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one farmer profile field is required")
        return self


class FarmerProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    farm_name: str | None
    county: str | None
    verification_status: str
    created_at: datetime
    updated_at: datetime


class BuyerProfileUpdate(BaseModel):
    organization_name: Annotated[Trimmed, Field(max_length=160)] | None = None
    buyer_type: Literal["individual", "business", "institution"] | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> BuyerProfileUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one buyer profile field is required")
        if "buyer_type" in self.model_fields_set and self.buyer_type is None:
            raise ValueError("buyer_type cannot be null")
        return self


class BuyerProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    organization_name: str | None
    buyer_type: str
    created_at: datetime
    updated_at: datetime


class AddressCreate(BaseModel):
    label: Annotated[Trimmed, Field(min_length=1, max_length=80)]
    line_1: Annotated[Trimmed, Field(min_length=1, max_length=255)]
    line_2: Annotated[Trimmed, Field(max_length=255)] | None = None
    locality: Annotated[Trimmed, Field(min_length=1, max_length=120)]
    county: Annotated[Trimmed, Field(min_length=1, max_length=80)]
    postal_code: Annotated[Trimmed, Field(max_length=20)] | None = None
    country_code: Literal["KE"] = "KE"
    latitude: Decimal | None = Field(default=None, ge=-90, le=90, decimal_places=7)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180, decimal_places=7)
    delivery_notes: Annotated[Trimmed, Field(max_length=500)] | None = None
    is_default: bool = False

    @model_validator(mode="after")
    def coordinates_are_a_pair(self) -> AddressCreate:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be supplied together")
        return self


class AddressUpdate(BaseModel):
    label: Annotated[Trimmed, Field(min_length=1, max_length=80)] | None = None
    line_1: Annotated[Trimmed, Field(min_length=1, max_length=255)] | None = None
    line_2: Annotated[Trimmed, Field(max_length=255)] | None = None
    locality: Annotated[Trimmed, Field(min_length=1, max_length=120)] | None = None
    county: Annotated[Trimmed, Field(min_length=1, max_length=80)] | None = None
    postal_code: Annotated[Trimmed, Field(max_length=20)] | None = None
    latitude: Decimal | None = Field(default=None, ge=-90, le=90, decimal_places=7)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180, decimal_places=7)
    delivery_notes: Annotated[Trimmed, Field(max_length=500)] | None = None
    is_default: bool | None = None

    @model_validator(mode="after")
    def validate_update(self) -> AddressUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one address field is required")
        for field in ("label", "line_1", "locality", "county"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        coordinate_fields = {"latitude", "longitude"} & self.model_fields_set
        if coordinate_fields and coordinate_fields != {"latitude", "longitude"}:
            raise ValueError("latitude and longitude must be updated together")
        if self.is_default is False:
            raise ValueError("Use another address as default instead of clearing the default")
        return self


class AddressResponse(AddressCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime


class InstallationUpsert(BaseModel):
    platform: Literal["android", "ios", "web"]
    push_token: Annotated[str, Field(min_length=8, max_length=4096)] | None = None


class InstallationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    installation_id: UUID
    platform: str
    has_push_token: bool
    last_seen_at: datetime
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime
