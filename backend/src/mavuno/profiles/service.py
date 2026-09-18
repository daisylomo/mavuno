from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import status

from mavuno.api.errors import ApiError
from mavuno.core.config import Settings
from mavuno.db.models import Address, BuyerProfile, DeviceInstallation, FarmerProfile, Profile
from mavuno.profiles.push_tokens import PushTokenProtector
from mavuno.profiles.repository import ProfileRepository
from mavuno.profiles.schemas import (
    AddressCreate,
    AddressUpdate,
    BuyerProfileUpdate,
    FarmerProfileUpdate,
    InstallationUpsert,
    ProfileUpdate,
)
from mavuno.profiles.types import ProfileActor


class ProfileService:
    def __init__(self, repository: ProfileRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    async def get_profile(self, user: ProfileActor) -> Profile:
        profile = await self.repository.get_profile(user.id)
        if profile is None:
            raise ApiError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="profile_not_found",
                message="Profile not found",
            )
        return profile

    async def update_profile(self, user: ProfileActor, payload: ProfileUpdate) -> Profile:
        profile = await self.get_profile(user)
        changes = payload.model_dump(exclude_unset=True)
        self._apply(profile, changes)
        await self._audit(user, "updated", "profile", user.id, changes)
        await self.repository.commit()
        await self.repository.refresh(profile)
        return profile

    async def update_farmer(
        self, user: ProfileActor, payload: FarmerProfileUpdate
    ) -> FarmerProfile:
        await self._require_role(user.id, "farmer")
        profile = await self.repository.get_farmer_profile(user.id)
        if profile is None:
            profile = FarmerProfile(user_id=user.id)
            self.repository.add(profile)
        changes = payload.model_dump(exclude_unset=True)
        self._apply(profile, changes)
        await self._audit(user, "updated", "farmer_profile", user.id, changes)
        await self.repository.commit()
        await self.repository.refresh(profile)
        return profile

    async def update_buyer(self, user: ProfileActor, payload: BuyerProfileUpdate) -> BuyerProfile:
        await self._require_role(user.id, "buyer")
        profile = await self.repository.get_buyer_profile(user.id)
        if profile is None:
            profile = BuyerProfile(user_id=user.id)
            self.repository.add(profile)
        changes = payload.model_dump(exclude_unset=True)
        resulting_type = changes.get("buyer_type", profile.buyer_type)
        resulting_name = changes.get("organization_name", profile.organization_name)
        if resulting_type in {"business", "institution"} and not resulting_name:
            raise ApiError(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                code="organization_name_required",
                message="organization_name is required for organizations",
            )
        self._apply(profile, changes)
        await self._audit(user, "updated", "buyer_profile", user.id, changes)
        await self.repository.commit()
        await self.repository.refresh(profile)
        return profile

    async def create_address(self, user: ProfileActor, payload: AddressCreate) -> Address:
        await self.repository.lock_user(user.id)
        values = payload.model_dump()
        if values["is_default"] or await self.repository.address_count(user.id) == 0:
            values["is_default"] = True
            await self.repository.clear_default_addresses(user.id)
        address = Address(id=uuid4(), user_id=user.id, **values)
        self.repository.add(address)
        await self._audit(user, "created", "address", address.id, values)
        await self.repository.commit()
        await self.repository.refresh(address)
        return address

    async def update_address(
        self, user: ProfileActor, address_id: UUID, payload: AddressUpdate
    ) -> Address:
        await self.repository.lock_user(user.id)
        address = await self._owned_address(user.id, address_id)
        changes = payload.model_dump(exclude_unset=True)
        if changes.get("is_default"):
            await self.repository.clear_default_addresses(user.id, except_id=address.id)
        self._apply(address, changes)
        await self._audit(user, "updated", "address", address.id, changes)
        await self.repository.commit()
        await self.repository.refresh(address)
        return address

    async def delete_address(self, user: ProfileActor, address_id: UUID) -> None:
        await self.repository.lock_user(user.id)
        address = await self._owned_address(user.id, address_id)
        if address.is_default and await self.repository.address_count(user.id) > 1:
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="default_address_required",
                message="Select another default address before deleting this address",
            )
        await self._audit(user, "deleted", "address", address.id, {})
        await self.repository.delete_address(address)
        await self.repository.commit()

    async def upsert_installation(
        self, user: ProfileActor, installation_id: UUID, payload: InstallationUpsert
    ) -> DeviceInstallation:
        installation = await self.repository.get_installation(installation_id)
        if installation is not None and installation.user_id != user.id:
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="installation_conflict",
                message="Installation is registered to another user",
            )
        now = datetime.now(UTC)
        token_ciphertext: bytes | None = None
        token_hash: bytes | None = None
        if payload.push_token is not None:
            token_ciphertext, token_hash = self._protect_token(payload.push_token)
        if installation is None:
            installation = DeviceInstallation(
                id=uuid4(),
                user_id=user.id,
                installation_id=installation_id,
                platform=payload.platform,
                push_token_hash=token_hash,
                push_token_ciphertext=token_ciphertext,
                last_seen_at=now,
            )
            self.repository.add(installation)
            action = "created"
        else:
            installation.platform = payload.platform
            installation.last_seen_at = now
            installation.revoked_at = None
            if payload.push_token is not None:
                installation.push_token_hash = token_hash
                installation.push_token_ciphertext = token_ciphertext
            action = "updated"
        await self._audit(
            user,
            action,
            "device_installation",
            installation.id,
            {"platform": payload.platform, "push_token": payload.push_token is not None},
        )
        await self.repository.commit()
        await self.repository.refresh(installation)
        return installation

    async def revoke_installation(self, user: ProfileActor, installation_id: UUID) -> None:
        installation = await self.repository.get_installation(installation_id)
        if installation is None or installation.user_id != user.id:
            raise ApiError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="installation_not_found",
                message="Installation not found",
            )
        installation.push_token_hash = None
        installation.push_token_ciphertext = None
        installation.revoked_at = datetime.now(UTC)
        await self._audit(user, "revoked", "device_installation", installation.id, {})
        await self.repository.commit()

    async def _owned_address(self, user_id: UUID, address_id: UUID) -> Address:
        address = await self.repository.get_address(user_id, address_id)
        if address is None:
            raise ApiError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="address_not_found",
                message="Address not found",
            )
        return address

    async def _require_role(self, user_id: UUID, role: str) -> None:
        if role not in await self.repository.get_roles(user_id):
            raise ApiError(
                status_code=status.HTTP_403_FORBIDDEN,
                code="role_required",
                message=f"The {role} role is required",
                details={"role": role},
            )

    async def _audit(
        self,
        user: ProfileActor,
        action: str,
        entity_type: str,
        entity_id: UUID | None,
        changes: dict[str, Any],
    ) -> None:
        await self.repository.add_audit(
            user_id=user.id,
            actor_user_id=user.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            changed_fields=sorted(changes),
        )

    def _protect_token(self, token: str) -> tuple[bytes, bytes]:
        hash_key = self.settings.push_token_hash_key
        encryption_key = self.settings.push_token_encryption_key
        if hash_key is None or encryption_key is None:
            raise ApiError(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="push_token_storage_unavailable",
                message="Push token registration is not configured",
            )
        return PushTokenProtector(
            encryption_key=encryption_key,
            hash_key=hash_key,
        ).protect(token)

    @staticmethod
    def _apply(target: Any, changes: dict[str, Any]) -> None:
        for field, value in changes.items():
            setattr(target, field, value)
