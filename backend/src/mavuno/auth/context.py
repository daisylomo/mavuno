from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """Validated request identity shared by protected feature modules."""

    id: UUID
    email: str | None
    phone_e164: str | None
    roles: frozenset[str]
    token_version: int

    def has_role(self, *roles: str) -> bool:
        return bool(self.roles.intersection(roles))
