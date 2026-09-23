from dataclasses import asdict, dataclass
from typing import Literal, Optional

# Exactly matches the roles table
MavunoRole = Literal["farmer", "buyer", "administrator", "support"]

# Matches auth.schemas.RegisterRequest.role (only these two roles are self-registerable)
RegisterRole = Literal["buyer", "farmer"]

# Matches buyer_profiles.buyer_type
BuyerType = Literal["individual", "business", "institution"]


@dataclass
class LoginRequest:
    # Backend expects a single "identifier" (email or phone), not separate fields
    identifier: str
    password: str

    def to_dict(self) -> dict:
        return {"identifier": self.identifier, "password": self.password}


@dataclass
class RegisterRequest:
    password: str
    role: RegisterRole = "buyer"
    phone: Optional[str] = None
    email: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class RefreshRequest:
    refresh_token: str

    def to_dict(self) -> dict:
        return {"refresh_token": self.refresh_token}


@dataclass
class UserResponse:
    id: str
    roles: list[str]
    email: Optional[str] = None
    phone_e164: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "UserResponse":
        return cls(
            id=str(data.get("id", "")),
            roles=data.get("roles", []),
            email=data.get("email"),
            phone_e164=data.get("phone_e164"),
        )


@dataclass
class AuthTokensResponse:
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"
    user: Optional[UserResponse] = None

    @classmethod
    def from_dict(cls, data: dict) -> "AuthTokensResponse":
        user_data = data.get("user")
        return cls(
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token", ""),
            expires_in=data.get("expires_in", 0),
            token_type=data.get("token_type", "bearer"),
            user=UserResponse.from_dict(user_data) if user_data else None,
        )