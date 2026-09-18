"""Add produce catalog, listings, images, and inventory ledger.

Revision ID: 0003_catalog_listings
Revises: 0002_profile_audit_events
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0003_catalog_listings"
down_revision: str | None = "0002_profile_audit_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = mysql.BINARY(16)
    created = sa.Column(
        "created_at",
        mysql.DATETIME(fsp=6),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP(6)"),
    )
    updated = sa.Column(
        "updated_at",
        mysql.DATETIME(fsp=6),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)"),
    )
    op.create_table(
        "produce_categories",
        sa.Column("id", uuid, nullable=False),
        sa.Column("parent_id", uuid, nullable=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False),
        created,
        updated,
        sa.ForeignKeyConstraint(["parent_id"], ["produce_categories.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_produce_categories_slug"),
    )
    op.create_table(
        "products",
        sa.Column("id", uuid, nullable=False),
        sa.Column("category_id", uuid, nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("slug", sa.String(160), nullable=False),
        sa.Column("default_unit", sa.String(16), nullable=False),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)"),
        ),
        sa.CheckConstraint(
            "default_unit IN ('kg','g','crate','piece','bunch','bag')",
            name="ck_products_default_unit_allowed",
        ),
        sa.ForeignKeyConstraint(["category_id"], ["produce_categories.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_products_slug"),
    )
    op.create_index("ix_products_category_id", "products", ["category_id"])
    op.create_table(
        "listings",
        sa.Column("id", uuid, nullable=False),
        sa.Column("farmer_id", uuid, nullable=False),
        sa.Column("product_id", uuid, nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("description", mysql.TEXT(), nullable=True),
        sa.Column("price_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="KES"),
        sa.Column("available_quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("quantity_unit", sa.String(16), nullable=False),
        sa.Column("harvest_date", sa.Date(), nullable=True),
        sa.Column("available_from", sa.Date(), nullable=True),
        sa.Column("available_until", sa.Date(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("version", mysql.INTEGER(unsigned=True), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)"),
        ),
        sa.CheckConstraint("price_amount >= 0", name="ck_listings_price_nonnegative"),
        sa.CheckConstraint("available_quantity >= 0", name="ck_listings_quantity_nonnegative"),
        sa.CheckConstraint("currency = 'KES'", name="ck_listings_currency_kes"),
        sa.CheckConstraint(
            "quantity_unit IN ('kg','g','crate','piece','bunch','bag')",
            name="ck_listings_quantity_unit_allowed",
        ),
        sa.CheckConstraint(
            "status IN ('draft','active','paused','sold_out','archived')",
            name="ck_listings_status_allowed",
        ),
        sa.CheckConstraint(
            "available_from IS NULL OR available_until IS NULL "
            "OR available_from <= available_until",
            name="ck_listings_availability_window_valid",
        ),
        sa.ForeignKeyConstraint(["farmer_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_listings_farmer_status", "listings", ["farmer_id", "status"])
    op.create_index("ix_listings_product_status", "listings", ["product_id", "status"])
    op.create_index("ix_listings_status_created", "listings", ["status", "created_at"])
    op.create_table(
        "listing_images",
        sa.Column("id", uuid, nullable=False),
        sa.Column("listing_id", uuid, nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("alt_text", sa.String(255), nullable=True),
        sa.Column("sort_order", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)"),
        ),
        sa.CheckConstraint("sort_order >= 0", name="ck_listing_images_sort_order_nonnegative"),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("listing_id", "sort_order", name="uq_listing_images_sort_order"),
        sa.UniqueConstraint("listing_id", "object_key", name="uq_listing_images_object_key"),
    )
    op.create_table(
        "inventory_movements",
        sa.Column("id", uuid, nullable=False),
        sa.Column("listing_id", uuid, nullable=False),
        sa.Column("actor_user_id", uuid, nullable=False),
        sa.Column("movement_type", sa.String(24), nullable=False),
        sa.Column("quantity_delta", sa.Numeric(14, 3), nullable=False),
        sa.Column("resulting_quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("reference_type", sa.String(32), nullable=True),
        sa.Column("reference_id", uuid, nullable=True),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.CheckConstraint("quantity_delta <> 0", name="ck_inventory_movements_delta_nonzero"),
        sa.CheckConstraint(
            "resulting_quantity >= 0", name="ck_inventory_movements_result_nonnegative"
        ),
        sa.CheckConstraint(
            "movement_type IN ('initial','restock','adjustment','reservation','release','sale')",
            name="ck_inventory_movements_movement_type_allowed",
        ),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_inventory_movements_listing_created",
        "inventory_movements",
        ["listing_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("inventory_movements")
    op.drop_table("listing_images")
    op.drop_table("listings")
    op.drop_table("products")
    op.drop_table("produce_categories")
