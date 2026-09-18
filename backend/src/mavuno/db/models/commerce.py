from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.mysql import DATETIME, INTEGER, JSON
from sqlalchemy.orm import Mapped, mapped_column

from mavuno.db.base import Base, TimestampMixin, UUIDBinary


class Cart(TimestampMixin, Base):
    __tablename__ = "carts"
    __table_args__ = (
        CheckConstraint("status IN ('active','converted','abandoned')", name="status_allowed"),
        Index("ix_carts_buyer_status", "buyer_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid4)
    buyer_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")


class CartItem(TimestampMixin, Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("cart_id", "listing_id", name="uq_cart_items_listing"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )
    id: Mapped[UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid4)
    cart_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("carts.id", ondelete="CASCADE"), nullable=False
    )
    listing_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("listings.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)


class Order(TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("buyer_id", "idempotency_key", name="uq_orders_buyer_idempotency"),
        CheckConstraint(
            "status IN ('pending_payment','paid','cancelled','expired',"
            "'fulfilment','completed','refunded')",
            name="status_allowed",
        ),
        CheckConstraint("subtotal_amount >= 0 AND total_amount >= 0", name="totals_nonnegative"),
        CheckConstraint("currency = 'KES'", name="currency_kes"),
        Index("ix_orders_buyer_created", "buyer_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid4)
    buyer_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="KES")
    subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    delivery_address_id: Mapped[UUID | None] = mapped_column(
        UUIDBinary(), ForeignKey("addresses.id", ondelete="RESTRICT"), nullable=True
    )
    reservation_expires_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    version: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False, server_default="1")


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0 AND line_total >= 0", name="amounts_nonnegative"),
        Index("ix_order_items_order_id", "order_id"),
    )
    id: Mapped[UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
    )
    listing_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("listings.id", ondelete="RESTRICT"), nullable=False
    )
    farmer_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    product_name: Mapped[str] = mapped_column(String(160), nullable=False)
    listing_title: Mapped[str] = mapped_column(String(180), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    quantity_unit: Mapped[str] = mapped_column(String(16), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"
    id: Mapped[UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(
        UUIDBinary(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    previous_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    new_status: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")
    )


class Payment(TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("order_id", "idempotency_key", name="uq_payments_order_idempotency"),
        UniqueConstraint("provider", "provider_request_ref", name="uq_payments_provider_request"),
        UniqueConstraint(
            "provider", "provider_transaction_ref", name="uq_payments_provider_transaction"
        ),
        CheckConstraint("rail IN ('mpesa','bank')", name="rail_allowed"),
        CheckConstraint(
            "state IN ('created','pending_customer','processing','succeeded',"
            "'failed','cancelled','expired','reversed')",
            name="state_allowed",
        ),
        CheckConstraint("amount > 0 AND currency = 'KES'", name="amount_currency_valid"),
        Index("ix_payments_order_id", "order_id"),
        Index("ix_payments_state_updated", "state", "updated_at"),
    )
    id: Mapped[UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
    )
    rail: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_request_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_transaction_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payer_phone_e164: Mapped[str | None] = mapped_column(String(16), nullable=True)
    account_reference: Mapped[str] = mapped_column(String(64), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(255), nullable=True)


class PaymentEvent(Base):
    __tablename__ = "payment_events"
    __table_args__ = (
        UniqueConstraint("provider", "provider_event_ref", name="uq_payment_events_provider_ref"),
        Index("ix_payment_events_payment_created", "payment_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid4)
    payment_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("payments.id", ondelete="RESTRICT"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_event_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    direction: Mapped[str] = mapped_column(String(24), nullable=False)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    payload_redacted: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    processing_state: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")
    )


class PaymentReconciliation(Base):
    __tablename__ = "payment_reconciliations"
    id: Mapped[UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid4)
    payment_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("payments.id", ondelete="RESTRICT"), nullable=False
    )
    expected_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    reported_amount: Mapped[Decimal | None] = mapped_column(Numeric(19, 4), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    provider_settlement_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    discrepancy_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    checked_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")
    )


class OutboxJob(TimestampMixin, Base):
    __tablename__ = "outbox_jobs"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_outbox_jobs_dedupe_key"),
        Index("ix_outbox_jobs_status_available", "status", "available_at"),
    )
    id: Mapped[UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid4)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(160), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="pending")
    attempts: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), nullable=False, server_default="0"
    )
    max_attempts: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), nullable=False, server_default="8"
    )
    available_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    leased_until: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
