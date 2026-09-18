from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, UniqueConstraint, text
from sqlalchemy.dialects.mysql import DATETIME, JSON
from sqlalchemy.orm import Mapped, mapped_column

from mavuno.db.base import Base, TimestampMixin, UUIDBinary


class Plan(TimestampMixin, Base):
    __tablename__ = "plans"
    __table_args__ = (
        UniqueConstraint("code", name="uq_plans_code"),
        CheckConstraint("audience IN ('buyer','farmer')", name="audience_allowed"),
        CheckConstraint("billing_interval IN ('month','year')", name="interval_allowed"),
        CheckConstraint("price_amount >= 0", name="price_nonnegative"),
    )
    id: Mapped[UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    audience: Mapped[str] = mapped_column(String(16), nullable=False)
    price_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="KES")
    billing_interval: Mapped[str] = mapped_column(String(16), nullable=False)
    features: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    active: Mapped[bool] = mapped_column(nullable=False, server_default="1")


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_subscriptions_user_idempotency"),
        UniqueConstraint(
            "provider", "provider_subscription_ref", name="uq_subscriptions_provider_ref"
        ),
        UniqueConstraint("account_reference", name="uq_subscriptions_account_reference"),
        CheckConstraint(
            "status IN ('pending','active','past_due','cancelled','expired')",
            name="status_allowed",
        ),
        Index("ix_subscriptions_user_status", "user_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    plan_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    provider: Mapped[str] = mapped_column(String(48), nullable=False)
    provider_subscription_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    account_reference: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    current_period_start: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)


class SubscriptionEvent(Base):
    __tablename__ = "subscription_events"
    __table_args__ = (
        UniqueConstraint("provider", "provider_event_ref", name="uq_subscription_events_ref"),
        Index("ix_subscription_events_subscription_created", "subscription_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid4)
    subscription_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("subscriptions.id", ondelete="RESTRICT"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(48), nullable=False)
    provider_event_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    payload_redacted: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")
    )


class Prebooking(TimestampMixin, Base):
    __tablename__ = "prebookings"
    __table_args__ = (
        CheckConstraint(
            "status IN ('requested','accepted','rejected','cancelled','fulfilled')",
            name="status_allowed",
        ),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("window_end > window_start", name="window_valid"),
        Index("ix_prebookings_buyer_created", "buyer_id", "created_at"),
        Index("ix_prebookings_farmer_status", "farmer_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid4)
    buyer_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    farmer_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    listing_id: Mapped[UUID | None] = mapped_column(
        UUIDBinary(), ForeignKey("listings.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="requested")
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    quantity_unit: Mapped[str] = mapped_column(String(24), nullable=False)
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(19, 4), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="KES")
    window_start: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(nullable=False, server_default="1")
