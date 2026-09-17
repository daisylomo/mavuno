"""Import all ORM models so Alembic can discover their metadata."""

from mavuno.db.models.identity import (
    Address,
    BuyerProfile,
    DeviceInstallation,
    FarmerProfile,
    Profile,
    ProfileAuditEvent,
    RefreshToken,
    Role,
    User,
    UserRole,
)

__all__ = [
    "Address",
    "BuyerProfile",
    "DeviceInstallation",
    "FarmerProfile",
    "Profile",
    "ProfileAuditEvent",
    "RefreshToken",
    "Role",
    "User",
    "UserRole",
]
