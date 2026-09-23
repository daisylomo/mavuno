from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Literal, Optional

BuyerType = Literal["individual", "business", "institution"]
PlatformType = Literal["android", "ios", "web"]


# --- Request Models ---

@dataclass
class ProfileUpdate:
    display_name: Optional[str] = None
    avatar_object_key: Optional[str] = None
    locale: Optional[str] = None
    bio: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class FarmerProfileUpdate:
    farm_name: Optional[str] = None
    county: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class BuyerProfileUpdate:
    organization_name: Optional[str] = None
    buyer_type: Optional[BuyerType] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class AddressCreate:
    label: str
    line_1: str
    locality: str
    county: str
    line_2: Optional[str] = None
    postal_code: Optional[str] = None
    country_code: str = "KE"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    delivery_notes: Optional[str] = None
    is_default: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class AddressUpdate:
    label: Optional[str] = None
    line_1: Optional[str] = None
    line_2: Optional[str] = None
    locality: Optional[str] = None
    county: Optional[str] = None
    postal_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    delivery_notes: Optional[str] = None
    is_default: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class InstallationUpsert:
    platform: PlatformType
    push_token: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


# --- Response Models ---

@dataclass
class ProfileResponse:
    user_id: str
    display_name: str
    locale: str = "en-KE"
    avatar_object_key: Optional[str] = None
    bio: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProfileResponse":
        return cls(
            user_id=str(data.get("user_id", "")),
            display_name=data.get("display_name", ""),
            locale=data.get("locale", "en-KE"),
            avatar_object_key=data.get("avatar_object_key"),
            bio=data.get("bio"),
        )


@dataclass
class FarmerProfileResponse:
    user_id: str
    farm_name: Optional[str] = None
    county: Optional[str] = None
    verification_status: str = "unverified"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FarmerProfileResponse":
        return cls(
            user_id=str(data.get("user_id", "")),
            farm_name=data.get("farm_name"),
            county=data.get("county"),
            verification_status=data.get("verification_status", "unverified"),
        )


@dataclass
class BuyerProfileResponse:
    user_id: str
    organization_name: Optional[str] = None
    buyer_type: str = "individual"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BuyerProfileResponse":
        return cls(
            user_id=str(data.get("user_id", "")),
            organization_name=data.get("organization_name"),
            buyer_type=data.get("buyer_type", "individual"),
        )


@dataclass
class AddressResponse:
    id: str
    user_id: str
    label: str
    line_1: str
    locality: str
    county: str
    country_code: str = "KE"
    line_2: Optional[str] = None
    postal_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    delivery_notes: Optional[str] = None
    is_default: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AddressResponse":
        return cls(
            id=str(data.get("id", "")),
            user_id=str(data.get("user_id", "")),
            label=data.get("label", ""),
            line_1=data.get("line_1", ""),
            locality=data.get("locality", ""),
            county=data.get("county", ""),
            country_code=data.get("country_code", "KE"),
            line_2=data.get("line_2"),
            postal_code=data.get("postal_code"),
            latitude=float(data["latitude"]) if data.get("latitude") is not None else None,
            longitude=float(data["longitude"]) if data.get("longitude") is not None else None,
            delivery_notes=data.get("delivery_notes"),
            is_default=data.get("is_default", False),
        )


@dataclass
class InstallationResponse:
    id: str
    user_id: str
    installation_id: str
    platform: str
    has_push_token: bool
    last_seen_at: Optional[str] = None
    revoked_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InstallationResponse":
        return cls(
            id=str(data.get("id", "")),
            user_id=str(data.get("user_id", "")),
            installation_id=str(data.get("installation_id", "")),
            platform=data.get("platform", ""),
            has_push_token=data.get("has_push_token", False),
            last_seen_at=data.get("last_seen_at"),
            revoked_at=data.get("revoked_at"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )