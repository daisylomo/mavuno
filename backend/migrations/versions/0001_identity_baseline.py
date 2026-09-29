"""Create the identity and profile baseline.

Revision ID: 0001_identity_baseline
Revises:
"""

from collections.abc import Iterator, Sequence
from pathlib import Path

from alembic import op
from sqlalchemy import text

revision: str = "0001_identity_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DROP_ORDER = (
    "refresh_tokens",
    "device_installations",
    "addresses",
    "buyer_profiles",
    "farmer_profiles",
    "profiles",
    "user_roles",
    "users",
    "roles",
)


def _baseline_statements() -> Iterator[str]:
    schema_path = Path(__file__).resolve().parents[2] / "db" / "schema.sql"
    statement_lines: list[str] = []

    for line in schema_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        statement_lines.append(line)
        if stripped.endswith(";"):
            yield "\n".join(statement_lines).rstrip().removesuffix(";")
            statement_lines.clear()

    if statement_lines:
        raise RuntimeError(f"Unterminated SQL statement in {schema_path}")


def upgrade() -> None:
    for statement in _baseline_statements():
        op.execute(text(statement))


def downgrade() -> None:
    for table_name in _DROP_ORDER:
        op.drop_table(table_name)
