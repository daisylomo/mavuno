from typing import Protocol
from uuid import UUID


class ProfileActor(Protocol):
    """Smallest authentication contract required by profile ownership rules."""

    id: UUID
