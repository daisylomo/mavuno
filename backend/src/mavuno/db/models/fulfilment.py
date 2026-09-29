from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, UniqueConstraint, text
from sqlalchemy.dialects.mysql import DATETIME, INTEGER, TEXT
from sqlalchemy.orm import Mapped, mapped_column

from mavuno.db.base import Base, TimestampMixin, UUIDBinary


class Fulfilment(TimestampMixin, Base):
    __tablename__ = "fulfilments"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_fulfilments_order_id"),
        CheckConstraint("method IN ('pickup','delivery')", name="method_allowed"),
        CheckConstraint(
            "status IN ('pending','scheduled','ready_for_handover','in_transit',"
            "'completed','cancelled')",
            name="status_allowed",
        ),
        CheckConstraint("window_end > window_start", name="window_valid"),
        CheckConstraint("latitude IS NULL OR latitude BETWEEN -90 AND 90", name="latitude_range"),
        CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180", name="longitude_range"
        ),
        Index("ix_fulfilments_status_window", "status", "window_start"),
    )

    id: Mapped[UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
    )
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="pending")
    location_label: Mapped[str] = mapped_column(String(120), nullable=False)
    location_details: Mapped[str] = mapped_column(String(500), nullable=False)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    window_start: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    coordination_notes: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    version: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False, server_default="1")
    completed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)


class FulfilmentStatusHistory(Base):
    __tablename__ = "fulfilment_status_history"
    __table_args__ = (Index("ix_fulfilment_history_created", "fulfilment_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid4)
    fulfilment_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("fulfilments.id", ondelete="RESTRICT"), nullable=False
    )
    actor_user_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    previous_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    new_status: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")
    )
