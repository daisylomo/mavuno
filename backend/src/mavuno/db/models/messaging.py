from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.mysql import DATETIME, JSON, TEXT
from sqlalchemy.orm import Mapped, mapped_column

from mavuno.db.base import Base, TimestampMixin, UUIDBinary


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint("scope_type IN ('order','listing')", name="scope_type_allowed"),
        UniqueConstraint(
            "scope_type", "scope_id", "buyer_id", "farmer_id", name="uq_conversation_scope_members"
        ),
        Index("ix_conversations_buyer_updated", "buyer_id", "updated_at"),
        Index("ix_conversations_farmer_updated", "farmer_id", "updated_at"),
    )
    id: Mapped[UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid4)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[UUID] = mapped_column(UUIDBinary(), nullable=False)
    buyer_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    farmer_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "sender_id", "client_message_id", name="uq_message_client_id"
        ),
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    sender_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    client_message_id: Mapped[UUID] = mapped_column(UUIDBinary(), nullable=False)
    body: Mapped[str] = mapped_column(TEXT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")
    )


class ConversationReadState(Base):
    __tablename__ = "conversation_read_states"
    conversation_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    last_read_message_id: Mapped[UUID | None] = mapped_column(
        UUIDBinary(), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    read_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")
    )


class NotificationPreference(TimestampMixin, Base):
    __tablename__ = "notification_preferences"
    user_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    messages_push: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    orders_push: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe"),
        Index("ix_notifications_user_created", "user_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(48), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(String(500), nullable=False)
    data: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(160), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")
    )


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "notification_id", "device_installation_id", name="uq_delivery_notification_device"
        ),
        CheckConstraint(
            "status IN ('pending','delivered','failed','skipped')", name="status_allowed"
        ),
    )
    id: Mapped[UUID] = mapped_column(UUIDBinary(), primary_key=True, default=uuid4)
    notification_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False
    )
    device_installation_id: Mapped[UUID] = mapped_column(
        UUIDBinary(), ForeignKey("device_installations.id", ondelete="CASCADE"), nullable=False
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    attempts: Mapped[int] = mapped_column(nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
