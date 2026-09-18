from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ListingCursor:
    value: str
    listing_id: UUID


def encode_cursor(value: datetime | Decimal, listing_id: UUID) -> str:
    payload = json.dumps([str(value), str(listing_id)], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_cursor(raw: str) -> ListingCursor:
    try:
        padded = raw + "=" * (-len(raw) % 4)
        value, listing_id = json.loads(base64.urlsafe_b64decode(padded).decode())
        return ListingCursor(value=str(value), listing_id=UUID(str(listing_id)))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid listing cursor") from exc
