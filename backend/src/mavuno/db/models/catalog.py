from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, UniqueConstraint, text
from sqlalchemy.dialects.mysql import DATETIME, INTEGER, TEXT
from sqlalchemy.orm import Mapped, mapped_column

from mavuno.db.base import Base, TimestampMixin, UUIDBinary


class ProduceCategory(TimestampMixin, Base):
    __tablename__ = "produce_categories"
    __table_args__ = (UniqueConstraint("slug", name="uq_produce_categories_slug"),)

    id: Mapped[UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid4)
    parent_id: Mapped[UUID | None] = mapped_column(
        UUIDBinary(), ForeignKey("produce_categories.id", ondelete="RESTRICT"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)


class Product(TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_products_slug"),
        CheckConstraint(
            "default_unit IN ('kg','g','crate','piece','bunch','bag')",
            name="default_unit_allowed",
        ),
        Index("ix_products_category_id", "category_id"),
    )

    id: Mapped[UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid4)
    category_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("produce_categories.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), nullable=False)
    default_unit: Mapped[str] = mapped_column(String(16), nullable=False)


class Listing(TimestampMixin, Base):
    __tablename__ = "listings"
    __table_args__ = (
        CheckConstraint("price_amount >= 0", name="price_nonnegative"),
        CheckConstraint("available_quantity >= 0", name="quantity_nonnegative"),
        CheckConstraint("currency = 'KES'", name="currency_kes"),
        CheckConstraint(
            "quantity_unit IN ('kg','g','crate','piece','bunch','bag')",
            name="quantity_unit_allowed",
        ),
        CheckConstraint(
            "status IN ('draft','active','paused','sold_out','archived')",
            name="status_allowed",
        ),
        CheckConstraint(
            "available_from IS NULL OR available_until IS NULL "
            "OR available_from <= available_until",
            name="availability_window_valid",
        ),
        Index("ix_listings_farmer_status", "farmer_id", "status"),
        Index("ix_listings_product_status", "product_id", "status"),
        Index("ix_listings_status_created", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid4)
    farmer_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    price_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="KES")
    available_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    quantity_unit: Mapped[str] = mapped_column(String(16), nullable=False)
    harvest_date: Mapped[date | None] = mapped_column(nullable=True)
    available_from: Mapped[date | None] = mapped_column(nullable=True)
    available_until: Mapped[date | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="draft")
    version: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False, server_default="1")


class ListingImage(TimestampMixin, Base):
    __tablename__ = "listing_images"
    __table_args__ = (
        UniqueConstraint("listing_id", "sort_order", name="uq_listing_images_sort_order"),
        UniqueConstraint("listing_id", "object_key", name="uq_listing_images_object_key"),
        CheckConstraint("sort_order >= 0", name="sort_order_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid4)
    listing_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("listings.id", ondelete="CASCADE"), nullable=False
    )
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    alt_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False)


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"
    __table_args__ = (
        CheckConstraint("quantity_delta <> 0", name="delta_nonzero"),
        CheckConstraint("resulting_quantity >= 0", name="result_nonnegative"),
        CheckConstraint(
            "movement_type IN ('initial','restock','adjustment','reservation','release','sale')",
            name="movement_type_allowed",
        ),
        Index("ix_inventory_movements_listing_created", "listing_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid4)
    listing_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("listings.id", ondelete="RESTRICT"), nullable=False
    )
    actor_user_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    movement_type: Mapped[str] = mapped_column(String(24), nullable=False)
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    resulting_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reference_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reference_id: Mapped[UUID | None] = mapped_column(UUIDBinary(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")
    )
