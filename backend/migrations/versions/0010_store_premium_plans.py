"""Plans that record Premium bought through the app stores (RevenueCat).

Revision ID: 0010_store_premium_plans
Revises: 0009_release_blockers

The store sets the price, so these plans carry a zero placeholder amount. They exist so a
RevenueCat purchase becomes an ordinary verified subscription and every entitlement check keeps
reading one table. They are hidden from the directly-sold plan list.
"""

import json
from collections.abc import Sequence
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op

revision: str = "0010_store_premium_plans"
down_revision: str | None = "0009_release_blockers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PLANS = (
    ("revenuecat_buyer", "Mavuno Premium", "buyer"),
    ("revenuecat_farmer", "Mavuno Premium", "farmer"),
)
_FEATURES = json.dumps(["insights", "prebooking"])


def _id(code: str) -> bytes:
    return uuid5(NAMESPACE_URL, f"mavuno:plan:{code}").bytes


def upgrade() -> None:
    connection = op.get_bind()
    for code, name, audience in _PLANS:
        connection.execute(
            sa.text(
                "INSERT IGNORE INTO plans "
                "(id, code, name, audience, price_amount, currency, billing_interval, features, "
                "active) VALUES (:id, :code, :name, :audience, 0, 'KES', 'month', :features, 1)"
            ),
            {
                "id": _id(code),
                "code": code,
                "name": name,
                "audience": audience,
                "features": _FEATURES,
            },
        )


def downgrade() -> None:
    connection = op.get_bind()
    for code, _, _ in _PLANS:
        # Plans that already back a store subscription are kept; subscriptions restrict deletes.
        connection.execute(
            sa.text(
                "DELETE FROM plans WHERE code = :code "
                "AND NOT EXISTS (SELECT 1 FROM subscriptions s WHERE s.plan_id = plans.id)"
            ),
            {"code": code},
        )
