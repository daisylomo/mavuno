from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mavuno.db.models import (
    Address,
    BuyerProfile,
    DeviceInstallation,
    FarmerProfile,
    Profile,
    ProfileAuditEvent,
    User,
    UserRole,
)


class ProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_profile(self, user_id: UUID) -> Profile | None:
        return await self.session.get(Profile, user_id)

    async def get_roles(self, user_id: UUID) -> set[str]:
        result = await self.session.scalars(
            select(UserRole.role_name).where(UserRole.user_id == user_id)
        )
        return set(result)

    async def lock_user(self, user_id: UUID) -> None:
        await self.session.execute(select(User.id).where(User.id == user_id).with_for_update())

    async def get_farmer_profile(self, user_id: UUID) -> FarmerProfile | None:
        return await self.session.get(FarmerProfile, user_id)

    async def get_buyer_profile(self, user_id: UUID) -> BuyerProfile | None:
        return await self.session.get(BuyerProfile, user_id)

    async def list_addresses(self, user_id: UUID) -> list[Address]:
        result = await self.session.scalars(
            select(Address)
            .where(Address.user_id == user_id)
            .order_by(Address.is_default.desc(), Address.created_at.asc())
        )
        return list(result)

    async def get_address(self, user_id: UUID, address_id: UUID) -> Address | None:
        result = await self.session.scalars(
            select(Address).where(Address.id == address_id, Address.user_id == user_id)
        )
        return result.one_or_none()

    async def clear_default_addresses(
        self, user_id: UUID, *, except_id: UUID | None = None
    ) -> None:
        statement = update(Address).where(Address.user_id == user_id, Address.is_default.is_(True))
        if except_id is not None:
            statement = statement.where(Address.id != except_id)
        await self.session.execute(statement.values(is_default=False))

    async def address_count(self, user_id: UUID) -> int:
        result = await self.session.scalars(select(Address.id).where(Address.user_id == user_id))
        return len(list(result))

    async def delete_address(self, address: Address) -> None:
        await self.session.delete(address)

    async def get_installation(self, installation_id: UUID) -> DeviceInstallation | None:
        result = await self.session.scalars(
            select(DeviceInstallation).where(DeviceInstallation.installation_id == installation_id)
        )
        return result.one_or_none()

    async def add_audit(
        self,
        *,
        user_id: UUID,
        actor_user_id: UUID,
        action: str,
        entity_type: str,
        entity_id: UUID | None,
        changed_fields: list[str],
    ) -> None:
        self.session.add(
            ProfileAuditEvent(
                user_id=user_id,
                actor_user_id=actor_user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                changed_fields=changed_fields,
            )
        )

    async def commit(self) -> None:
        await self.session.commit()

    async def refresh(self, value: Any) -> None:
        await self.session.refresh(value)

    def add(self, value: Any) -> None:
        self.session.add(value)
