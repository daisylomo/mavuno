"""Premium paid with M-PESA: prepaid monthly plans and payment outcomes on subscriptions.

Revision ID: 0011_mpesa_premium
Revises: 0010_store_premium_plans

Each M-PESA payment buys one prepaid period and is recorded as its own subscription row. STK
pushes cannot renew by themselves, so members renew by paying again; an early renewal starts
when the current period ends.

* ``subscriptions`` gains ``payer_phone_e164`` (the number that was prompted, checked against
  Safaricom's answer) and ``failure_reason``, and may now be ``failed``.
* Two monthly plans are seeded at a token KES 1 for sandbox testing. Raise the prices before
  taking real payments.
"""

import json
from collections.abc import Sequence
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op

revision: str = "0011_mpesa_premium"
down_revision: str | None = "0010_store_premium_plans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PLANS = (
    ("mpesa_buyer_monthly", "Mavuno Premium (monthly)", "buyer", ["prebooking"]),
    ("mpesa_farmer_monthly", "Mavuno Premium (monthly)", "farmer", ["insights"]),
)
_STATUS = "status IN ('pending','active','past_due','cancelled','expired'{extra})"


def _id(code: str) -> bytes:
    return uuid5(NAMESPACE_URL, f"mavuno:plan:{code}").bytes


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("payer_phone_e164", sa.String(16), nullable=True))
    op.add_column("subscriptions", sa.Column("failure_reason", sa.String(255), nullable=True))
    op.drop_constraint(op.f("ck_subscriptions_status_allowed"), "subscriptions", type_="check")
    op.create_check_constraint(
        op.f("ck_subscriptions_status_allowed"), "subscriptions", _STATUS.format(extra=",'failed'")
    )
    connection = op.get_bind()
    for code, name, audience, features in _PLANS:
        connection.execute(
            sa.text(
                "INSERT IGNORE INTO plans "
                "(id, code, name, audience, price_amount, currency, billing_interval, features, "
                "active) VALUES (:id, :code, :name, :audience, 1, 'KES', 'month', :features, 1)"
            ),
            {
                "id": _id(code),
                "code": code,
                "name": name,
                "audience": audience,
                "features": json.dumps(features),
            },
        )


def downgrade() -> None:
    connection = op.get_bind()
    for code, *_ in _PLANS:
        # Plans that already back a payment are kept; subscriptions restrict deletes.
        connection.execute(
            sa.text(
                "DELETE FROM plans WHERE code = :code "
                "AND NOT EXISTS (SELECT 1 FROM subscriptions s WHERE s.plan_id = plans.id)"
            ),
            {"code": code},
        )
    connection.execute(
        sa.text("UPDATE subscriptions SET status = 'cancelled' WHERE status = 'failed'")
    )
    op.drop_constraint(op.f("ck_subscriptions_status_allowed"), "subscriptions", type_="check")
    op.create_check_constraint(
        op.f("ck_subscriptions_status_allowed"), "subscriptions", _STATUS.format(extra="")
    )
    op.drop_column("subscriptions", "failure_reason")
    op.drop_column("subscriptions", "payer_phone_e164")
