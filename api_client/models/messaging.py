from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Literal, Optional


# --- Request Models ---

@dataclass
class ConversationCreate:
    scope_type: Literal["order", "listing"]
    scope_id: str
    farmer_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class MessageCreate:
    client_message_id: str
    body: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MarkReadRequest:
    last_read_message_id: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class NotificationPreferencesUpdate:
    messages_push: bool
    orders_push: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --- Response Models ---

@dataclass
class MessageResponse:
    id: str
    conversation_id: str
    sender_id: str
    client_message_id: str
    body: str
    created_at: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessageResponse":
        return cls(
            id=str(data.get("id", "")),
            conversation_id=str(data.get("conversation_id", "")),
            sender_id=str(data.get("sender_id", "")),
            client_message_id=str(data.get("client_message_id", "")),
            body=data.get("body", ""),
            created_at=data.get("created_at", ""),
        )


@dataclass
class ConversationResponse:
    id: str
    scope_type: str
    scope_id: str
    buyer_id: str
    farmer_id: str
    last_message_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationResponse":
        return cls(
            id=str(data.get("id", "")),
            scope_type=data.get("scope_type", ""),
            scope_id=str(data.get("scope_id", "")),
            buyer_id=str(data.get("buyer_id", "")),
            farmer_id=str(data.get("farmer_id", "")),
            last_message_at=data.get("last_message_at"),
        )


@dataclass
class MessagePage:
    items: List[MessageResponse]
    next_cursor: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessagePage":
        raw_items = data.get("items") or []
        return cls(
            items=[MessageResponse.from_dict(item) for item in raw_items],
            next_cursor=data.get("next_cursor"),
        )


@dataclass
class NotificationResponse:
    id: str
    kind: str
    title: str
    body: str
    data: Dict[str, Any]
    read_at: Optional[str] = None
    created_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NotificationResponse":
        return cls(
            id=str(data.get("id", "")),
            kind=data.get("kind", ""),
            title=data.get("title", ""),
            body=data.get("body", ""),
            data=data.get("data", {}),
            read_at=data.get("read_at"),
            created_at=data.get("created_at"),
        )


@dataclass
class NotificationPreferencesResponse:
    messages_push: bool
    orders_push: bool

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NotificationPreferencesResponse":
        return cls(
            messages_push=data.get("messages_push", True),
            orders_push=data.get("orders_push", True),
        )
