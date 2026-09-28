"""Seed common produce types so farmers can publish their first listings.

Revision ID: 0008_catalog_seed
Revises: 0007_premium
"""

from collections.abc import Sequence
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op

revision: str = "0008_catalog_seed"
down_revision: str | None = "0007_premium"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORIES = (
    ("Vegetables", "vegetables"),
    ("Fruits", "fruits"),
    ("Grains & Cereals", "grains-cereals"),
    ("Tubers & Roots", "tubers-roots"),
    ("Dairy & Poultry", "dairy-poultry"),
)
PRODUCTS = (
    ("Tomatoes", "tomatoes", "vegetables", "kg"),
    ("Spinach", "spinach", "vegetables", "bunch"),
    ("Sukuma wiki", "sukuma-wiki", "vegetables", "bunch"),
    ("Mangoes", "mangoes", "fruits", "kg"),
    ("Bananas", "bananas", "fruits", "bunch"),
    ("Avocados", "avocados", "fruits", "piece"),
    ("Maize", "maize", "grains-cereals", "bag"),
    ("Beans", "beans", "grains-cereals", "kg"),
    ("Potatoes", "potatoes", "tubers-roots", "kg"),
    ("Sweet potatoes", "sweet-potatoes", "tubers-roots", "kg"),
    ("Eggs", "eggs", "dairy-poultry", "crate"),
    ("Milk", "milk", "dairy-poultry", "piece"),
)


def _id(kind: str, slug: str) -> bytes:
    return uuid5(NAMESPACE_URL, f"mavuno:{kind}:{slug}").bytes


def upgrade() -> None:
    connection = op.get_bind()
    for name, slug in CATEGORIES:
        connection.execute(
            sa.text(
                "INSERT IGNORE INTO produce_categories (id, name, slug) VALUES (:id, :name, :slug)"
            ),
            {"id": _id("category", slug), "name": name, "slug": slug},
        )
    for name, slug, category_slug, unit in PRODUCTS:
        connection.execute(
            sa.text(
                "INSERT IGNORE INTO products (id, category_id, name, slug, default_unit) "
                "VALUES (:id, (SELECT id FROM produce_categories WHERE slug = :category_slug), "
                ":name, :slug, :unit)"
            ),
            {
                "id": _id("product", slug),
                "category_slug": category_slug,
                "name": name,
                "slug": slug,
                "unit": unit,
            },
        )


def downgrade() -> None:
    connection = op.get_bind()
    for _, slug, _, _ in PRODUCTS:
        connection.execute(
            sa.text("DELETE FROM products WHERE id = :id"), {"id": _id("product", slug)}
        )
    for _, slug in CATEGORIES:
        connection.execute(
            sa.text("DELETE FROM produce_categories WHERE id = :id"), {"id": _id("category", slug)}
        )
