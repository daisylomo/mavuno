"""Per-farmer fulfilment, payment refunds, stored listing photos, richer farmer profiles.

Revision ID: 0009_release_blockers
Revises: 0008_catalog_seed

* ``fulfilments`` gains ``farmer_id``. Each farmer in a mixed order now coordinates and hands
  over only their own items. Existing shared records are split, one per participating farmer,
  keeping the original details and status.
* ``payment_refunds`` records money owed back to a buyer (cancellation, late or duplicate
  payment) and whether it was reversed automatically or needs an operator.
* ``listing_image_contents`` holds photo bytes uploaded from the app, so a stateless host with
  no object storage can still serve farmers' own photographs.
* ``farmer_profiles`` gains the public details buyers see about the farmer behind a listing.
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0009_release_blockers"
down_revision: str | None = "0008_catalog_seed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FULFILMENT_COPY_COLUMNS = (
    "order_id, method, status, location_label, location_details, latitude, longitude, "
    "window_start, window_end, coordination_notes, version, completed_at, created_at"
)


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
    ]


def _split_fulfilments() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT f.id, f.order_id, o.buyer_id FROM fulfilments f "
            "JOIN orders o ON o.id = f.order_id"
        )
    ).all()
    for fulfilment_id, order_id, buyer_id in rows:
        farmers = [
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT DISTINCT farmer_id FROM order_items WHERE order_id = :order_id "
                    "ORDER BY farmer_id"
                ),
                {"order_id": order_id},
            ).all()
        ]
        if not farmers:
            continue
        connection.execute(
            sa.text("UPDATE fulfilments SET farmer_id = :farmer_id WHERE id = :id"),
            {"farmer_id": farmers[0], "id": fulfilment_id},
        )
        for farmer_id in farmers[1:]:
            new_id = uuid4().bytes
            connection.execute(
                sa.text(
                    f"INSERT INTO fulfilments (id, farmer_id, {_FULFILMENT_COPY_COLUMNS}) "
                    f"SELECT :new_id, :farmer_id, {_FULFILMENT_COPY_COLUMNS} "
                    "FROM fulfilments WHERE id = :id"
                ),
                {"new_id": new_id, "farmer_id": farmer_id, "id": fulfilment_id},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO fulfilment_status_history "
                    "(id, fulfilment_id, actor_user_id, previous_status, new_status, reason) "
                    "SELECT :history_id, :new_id, :actor, NULL, status, "
                    "'Split from shared order coordination' FROM fulfilments WHERE id = :new_id"
                ),
                {"history_id": uuid4().bytes, "new_id": new_id, "actor": buyer_id},
            )


def upgrade() -> None:
    op.add_column("fulfilments", sa.Column("farmer_id", mysql.BINARY(16), nullable=True))
    _split_fulfilments()
    op.alter_column("fulfilments", "farmer_id", existing_type=mysql.BINARY(16), nullable=False)
    op.create_foreign_key(
        op.f("fk_fulfilments_farmer_id_users"),
        "fulfilments",
        "users",
        ["farmer_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    # The composite key starts with order_id, so it also serves the order foreign key and the
    # old single-column key can be dropped afterwards.
    op.create_unique_constraint(
        "uq_fulfilments_order_farmer", "fulfilments", ["order_id", "farmer_id"]
    )
    op.drop_constraint("uq_fulfilments_order_id", "fulfilments", type_="unique")
    op.create_index("ix_fulfilments_farmer_status", "fulfilments", ["farmer_id", "status"])

    op.create_table(
        "payment_refunds",
        sa.Column("id", mysql.BINARY(16), nullable=False),
        sa.Column("payment_id", mysql.BINARY(16), nullable=False),
        sa.Column("order_id", mysql.BINARY(16), nullable=False),
        sa.Column("farmer_id", mysql.BINARY(16), nullable=True),
        sa.Column("amount", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="KES", nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=24), server_default="pending", nullable=False),
        sa.Column("dedupe_key", sa.String(length=160), nullable=False),
        sa.Column("provider_ref", sa.String(length=128), nullable=True),
        sa.Column("operator_note", sa.String(length=255), nullable=True),
        sa.Column("completed_at", mysql.DATETIME(fsp=6), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "amount > 0 AND currency = 'KES'",
            name=op.f("ck_payment_refunds_amount_currency_valid"),
        ),
        sa.CheckConstraint(
            "state IN ('pending','submitted','completed','failed','manual_required')",
            name=op.f("ck_payment_refunds_state_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["payments.id"],
            name=op.f("fk_payment_refunds_payment_id_payments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_payment_refunds_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["farmer_id"],
            ["users.id"],
            name=op.f("fk_payment_refunds_farmer_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_refunds")),
        sa.UniqueConstraint("dedupe_key", name="uq_payment_refunds_dedupe_key"),
    )
    op.create_index("ix_payment_refunds_payment", "payment_refunds", ["payment_id"])
    op.create_index("ix_payment_refunds_state_updated", "payment_refunds", ["state", "updated_at"])

    op.create_table(
        "listing_image_contents",
        sa.Column("image_id", mysql.BINARY(16), nullable=False),
        sa.Column("content_type", sa.String(length=32), nullable=False),
        sa.Column("byte_size", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("content", mysql.MEDIUMBLOB(), nullable=False),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "byte_size > 0", name=op.f("ck_listing_image_contents_byte_size_positive")
        ),
        sa.CheckConstraint(
            "content_type IN ('image/jpeg','image/png','image/webp')",
            name=op.f("ck_listing_image_contents_content_type_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["image_id"],
            ["listing_images.id"],
            name=op.f("fk_listing_image_contents_image_id_listing_images"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("image_id", name=op.f("pk_listing_image_contents")),
    )

    op.add_column("farmer_profiles", sa.Column("locality", sa.String(length=120), nullable=True))
    op.add_column(
        "farmer_profiles", sa.Column("farming_practices", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "farmer_profiles",
        sa.Column("farm_size_acres", sa.Numeric(precision=8, scale=2), nullable=True),
    )
    op.add_column(
        "farmer_profiles",
        sa.Column("farming_since_year", mysql.SMALLINT(unsigned=True), nullable=True),
    )
    op.add_column(
        "farmer_profiles",
        sa.Column("offers_pickup", sa.Boolean(), server_default="1", nullable=False),
    )
    op.add_column(
        "farmer_profiles",
        sa.Column("offers_delivery", sa.Boolean(), server_default="0", nullable=False),
    )
    op.add_column(
        "farmer_profiles",
        sa.Column("delivery_radius_km", mysql.SMALLINT(unsigned=True), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_farmer_profiles_farm_size_positive"),
        "farmer_profiles",
        "farm_size_acres IS NULL OR farm_size_acres > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_farmer_profiles_farm_size_positive"), "farmer_profiles", type_="check"
    )
    for column in (
        "delivery_radius_km",
        "offers_delivery",
        "offers_pickup",
        "farming_since_year",
        "farm_size_acres",
        "farming_practices",
        "locality",
    ):
        op.drop_column("farmer_profiles", column)
    op.drop_table("listing_image_contents")
    op.drop_table("payment_refunds")
    # Collapse split coordination back to one record per order before restoring the old key.
    op.execute(
        "DELETE h FROM fulfilment_status_history h JOIN fulfilments f ON f.id = h.fulfilment_id "
        "WHERE f.farmer_id <> (SELECT MIN(i.farmer_id) FROM order_items i "
        "WHERE i.order_id = f.order_id)"
    )
    op.execute(
        "DELETE f FROM fulfilments f WHERE f.farmer_id <> (SELECT MIN(i.farmer_id) "
        "FROM order_items i WHERE i.order_id = f.order_id)"
    )
    op.drop_index("ix_fulfilments_farmer_status", table_name="fulfilments")
    op.create_unique_constraint("uq_fulfilments_order_id", "fulfilments", ["order_id"])
    op.drop_constraint("uq_fulfilments_order_farmer", "fulfilments", type_="unique")
    op.drop_constraint(op.f("fk_fulfilments_farmer_id_users"), "fulfilments", type_="foreignkey")
    op.drop_column("fulfilments", "farmer_id")
