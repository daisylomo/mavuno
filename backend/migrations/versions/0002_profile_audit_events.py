"""Add immutable profile audit events.

Revision ID: 0002_profile_audit_events
Revises: 0001_identity_baseline
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0002_profile_audit_events"
down_revision: str | None = "0001_identity_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "device_installations",
        "push_token_ciphertext",
        existing_type=mysql.VARBINARY(1024),
        type_=mysql.VARBINARY(8192),
        existing_nullable=True,
    )
    op.create_table(
        "profile_audit_events",
        sa.Column("id", mysql.BINARY(16), nullable=False),
        sa.Column("user_id", mysql.BINARY(16), nullable=False),
        sa.Column("actor_user_id", mysql.BINARY(16), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", mysql.BINARY(16), nullable=True),
        sa.Column("changed_fields", mysql.JSON(), nullable=False),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_profile_audit_events_actor_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_profile_audit_events_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_profile_audit_events"),
    )
    op.create_index(
        "ix_profile_audit_events_user_created",
        "profile_audit_events",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("profile_audit_events")
    op.alter_column(
        "device_installations",
        "push_token_ciphertext",
        existing_type=mysql.VARBINARY(8192),
        type_=mysql.VARBINARY(1024),
        existing_nullable=True,
    )
