from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import MetaData, text
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import BINARY, TypeDecorator

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class UUIDBinary(TypeDecorator[UUID]):
    """Store UUID values as compact MySQL BINARY(16) columns."""

    impl = BINARY(16)
    cache_ok = True

    def process_bind_param(self, value: UUID | str | None, dialect: object) -> bytes | None:
        if value is None:
            return None
        return (value if isinstance(value, UUID) else UUID(value)).bytes

    def process_result_value(self, value: bytes | None, dialect: object) -> UUID | None:
        return UUID(bytes=value) if value is not None else None


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)"),
    )
