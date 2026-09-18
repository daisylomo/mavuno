from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator


class RegisterRequest(BaseModel):
    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=7, max_length=32)
    password: str = Field(min_length=10, max_length=128)
    role: Literal["buyer", "farmer"] = "buyer"

    @model_validator(mode="after")
    def require_identifier(self) -> RegisterRequest:
        if self.email is None and self.phone is None:
            raise ValueError("An email address or phone number is required")
        return self


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=40, max_length=256)


class LogoutRequest(RefreshRequest):
    pass


class UserResponse(BaseModel):
    id: UUID
    email: str | None
    phone_e164: str | None
    roles: list[str]


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserResponse


class LogoutResponse(BaseModel):
    revoked: bool = True
