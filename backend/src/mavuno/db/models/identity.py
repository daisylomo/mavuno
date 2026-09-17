from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.mysql import BINARY, DATETIME, INTEGER, TEXT, VARBINARY
from sqlalchemy.orm import Mapped, mapped_column

from mavuno.db.base import Base, TimestampMixin, UUIDBinary


class Role(Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email IS NOT NULL OR phone_e164 IS NOT NULL", name="identifier_required"),
        CheckConstraint(
            "status IN ('pending', 'active', 'suspended', 'disabled')", name="status_allowed"
        ),
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint("phone_e164", name="uq_users_phone_e164"),
        Index("ix_users_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid4)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone_e164: Mapped[str | None] = mapped_column(String(16), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    token_version: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), nullable=False, server_default="0"
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    phone_verified_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_name: Mapped[str] = mapped_column(
        String(32), ForeignKey("roles.name", ondelete="RESTRICT"), primary_key=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")
    )


class Profile(TimestampMixin, Base):
    __tablename__ = "profiles"

    user_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    avatar_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    locale: Mapped[str] = mapped_column(String(16), nullable=False, server_default="en-KE")
    bio: Mapped[str | None] = mapped_column(TEXT, nullable=True)


class FarmerProfile(TimestampMixin, Base):
    __tablename__ = "farmer_profiles"

    user_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    farm_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    county: Mapped[str | None] = mapped_column(String(80), nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="unverified"
    )
    __table_args__ = (
        CheckConstraint(
            "verification_status IN ('unverified', 'pending', 'verified', 'rejected')",
            name="verification_status_allowed",
        ),
    )


class BuyerProfile(TimestampMixin, Base):
    __tablename__ = "buyer_profiles"

    user_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    organization_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    buyer_type: Mapped[str] = mapped_column(String(16), nullable=False, server_default="individual")
    __table_args__ = (
        CheckConstraint(
            "buyer_type IN ('individual', 'business', 'institution')", name="buyer_type_allowed"
        ),
    )


class Address(TimestampMixin, Base):
    __tablename__ = "addresses"
    __table_args__ = (
        CheckConstraint("latitude BETWEEN -90 AND 90", name="latitude_range"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="longitude_range"),
        Index("ix_addresses_user_id", "user_id"),
    )

    id: Mapped[UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    line_1: Mapped[str] = mapped_column(String(255), nullable=False)
    line_2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    locality: Mapped[str] = mapped_column(String(120), nullable=False)
    county: Mapped[str] = mapped_column(String(80), nullable=False)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, server_default="KE")
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    delivery_notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")


class DeviceInstallation(TimestampMixin, Base):
    __tablename__ = "device_installations"
    __table_args__ = (
        CheckConstraint("platform IN ('android', 'ios', 'web')", name="platform_allowed"),
        UniqueConstraint("installation_id", name="uq_device_installations_installation_id"),
        UniqueConstraint("push_token_hash", name="uq_device_installations_push_token_hash"),
        Index("ix_device_installations_user_id", "user_id"),
    )

    id: Mapped[UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    installation_id: Mapped[UUID] = mapped_column(UUIDBinary(), nullable=False)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    push_token_ciphertext: Mapped[bytes | None] = mapped_column(VARBINARY(1024), nullable=True)
    push_token_hash: Mapped[bytes | None] = mapped_column(BINARY(32), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
        Index("ix_refresh_tokens_user_id", "user_id"),
        Index("ix_refresh_tokens_family_id", "family_id"),
        Index("ix_refresh_tokens_expires_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    device_installation_id: Mapped[UUID | None] = mapped_column(
        UUIDBinary(), ForeignKey("device_installations.id", ondelete="SET NULL"), nullable=True
    )
    family_id: Mapped[UUID] = mapped_column(UUIDBinary(), nullable=False, default=uuid4)
    token_hash: Mapped[bytes] = mapped_column(BINARY(32), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")
    )
    rotated_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    replaced_by_id: Mapped[UUID | None] = mapped_column(
        UUIDBinary(), ForeignKey("refresh_tokens.id", ondelete="SET NULL"), nullable=True
    )
