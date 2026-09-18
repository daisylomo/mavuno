from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints


class ConversationCreate(BaseModel):
    scope_type: str = Field(pattern="^(order|listing)$")
    scope_id: UUID
    farmer_id: UUID | None = None


class ConversationResponse(BaseModel):
    id: UUID
    scope_type: str
    scope_id: UUID
    buyer_id: UUID
    farmer_id: UUID
    last_message_at: datetime | None

    model_config = {"from_attributes": True}


class MessageCreate(BaseModel):
    client_message_id: UUID
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class MessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    sender_id: UUID
    client_message_id: UUID
    body: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MessagePage(BaseModel):
    items: list[MessageResponse]
    next_cursor: UUID | None


class MarkReadRequest(BaseModel):
    last_read_message_id: UUID


class NotificationPreferencesUpdate(BaseModel):
    messages_push: bool
    orders_push: bool


class NotificationPreferencesResponse(NotificationPreferencesUpdate):
    pass


class NotificationResponse(BaseModel):
    id: UUID
    kind: str
    title: str
    body: str
    data: dict[str, object]
    read_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
