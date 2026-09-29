"""add fulfilment coordination

Revision ID: 0005_fulfilment
Revises: 0004_orders_payments
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0005_fulfilment"
down_revision: str | None = "0004_orders_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fulfilments",
        sa.Column("id", mysql.BINARY(16), nullable=False),
        sa.Column("order_id", mysql.BINARY(16), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="pending", nullable=False),
        sa.Column("location_label", sa.String(length=120), nullable=False),
        sa.Column("location_details", sa.String(length=500), nullable=False),
        sa.Column("latitude", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("longitude", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("window_start", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("window_end", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("coordination_notes", sa.Text(), nullable=True),
        sa.Column("version", mysql.INTEGER(unsigned=True), server_default="1", nullable=False),
        sa.Column("completed_at", mysql.DATETIME(fsp=6), nullable=True),
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
        sa.CheckConstraint(
            "method IN ('pickup','delivery')", name=op.f("ck_fulfilments_method_allowed")
        ),
        sa.CheckConstraint(
            "status IN ('pending','scheduled','ready_for_handover','in_transit',"
            "'completed','cancelled')",
            name=op.f("ck_fulfilments_status_allowed"),
        ),
        sa.CheckConstraint("window_end > window_start", name=op.f("ck_fulfilments_window_valid")),
        sa.CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90",
            name=op.f("ck_fulfilments_latitude_range"),
        ),
        sa.CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name=op.f("ck_fulfilments_longitude_range"),
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_fulfilments_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fulfilments")),
        sa.UniqueConstraint("order_id", name="uq_fulfilments_order_id"),
    )
    op.create_index(
        "ix_fulfilments_status_window", "fulfilments", ["status", "window_start"], unique=False
    )
    op.create_table(
        "fulfilment_status_history",
        sa.Column("id", mysql.BINARY(16), nullable=False),
        sa.Column("fulfilment_id", mysql.BINARY(16), nullable=False),
        sa.Column("actor_user_id", mysql.BINARY(16), nullable=False),
        sa.Column("previous_status", sa.String(length=24), nullable=True),
        sa.Column("new_status", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_fulfilment_status_history_actor_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["fulfilment_id"],
            ["fulfilments.id"],
            name=op.f("fk_fulfilment_status_history_fulfilment_id_fulfilments"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fulfilment_status_history")),
    )
    op.create_index(
        "ix_fulfilment_history_created",
        "fulfilment_status_history",
        ["fulfilment_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("fulfilment_status_history")
    op.drop_table("fulfilments")
