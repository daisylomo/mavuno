from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, create_autospec
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr, ValidationError

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
from mavuno.profiles.service import ProfileService


@dataclass
class Actor:
    id: UUID


@pytest.fixture
def actor() -> Actor:
    return Actor(uuid4())


@pytest.fixture
def repository() -> Any:
    repository = create_autospec(ProfileRepository, instance=True)
    repository.commit = AsyncMock()
    repository.add_audit = AsyncMock()
    repository.add = MagicMock()
    repository.lock_user = AsyncMock()
    repository.refresh = AsyncMock()
    return repository


@pytest.fixture
def service(repository: Any) -> ProfileService:
    return ProfileService(
        cast(ProfileRepository, repository),
        Settings(
            environment="test",
            push_token_hash_key=SecretStr("x" * 32),
            push_token_encryption_key=SecretStr(Fernet.generate_key().decode()),
        ),
    )


def address_payload(*, is_default: bool = False) -> AddressCreate:
    return AddressCreate(
        label="Home",
        line_1="1 Market Road",
        locality="Nairobi",
        county="Nairobi",
        latitude="-1.286389",
        longitude="36.817223",
        is_default=is_default,
    )


def test_profile_and_address_schema_validation() -> None:
    assert ProfileUpdate(display_name="  Amina  ").display_name == "Amina"
    with pytest.raises(ValidationError):
        ProfileUpdate()
    with pytest.raises(ValidationError):
        ProfileUpdate(avatar_object_key="https://cdn.example.test/avatar.jpg")
    with pytest.raises(ValidationError):
        ProfileUpdate(locale=None)
    with pytest.raises(ValidationError):
        AddressCreate(label="Home", line_1="Road", locality="Nairobi", county="Nairobi", latitude=1)
    with pytest.raises(ValidationError):
        AddressUpdate(is_default=False)
    with pytest.raises(ValidationError):
        AddressUpdate(label=None)
    with pytest.raises(ValidationError):
        BuyerProfileUpdate()
    with pytest.raises(ValidationError):
        BuyerProfileUpdate(buyer_type=None)


def test_push_token_protector_roundtrip_and_randomized_ciphertext() -> None:
    protector = PushTokenProtector(
        encryption_key=SecretStr(Fernet.generate_key().decode()),
        hash_key=SecretStr("hash-secret-that-is-at-least-32-chars"),
    )
    token = "ExponentPushToken[delivery-secret]"
    first_ciphertext, first_digest = protector.protect(token)
    second_ciphertext, second_digest = protector.protect(token)

    assert protector.decrypt(first_ciphertext) == token
    assert first_ciphertext != second_ciphertext
    assert first_digest == second_digest
    assert token.encode() not in first_ciphertext

    maximum_token = "t" * 4096
    maximum_ciphertext, _ = protector.protect(maximum_token)
    assert len(maximum_ciphertext) <= 8192
    assert protector.decrypt(maximum_ciphertext) == maximum_token


def test_push_token_config_validation() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="production")
    with pytest.raises(ValidationError):
        Settings(environment="test", push_token_encryption_key=SecretStr("not-a-fernet-key"))
    key = Fernet.generate_key().decode()
    with pytest.raises(ValidationError):
        Settings(
            environment="test",
            push_token_hash_key=SecretStr(key),
            push_token_encryption_key=SecretStr(key),
        )


@pytest.mark.anyio
async def test_profile_update_is_audited(
    service: ProfileService, repository: Any, actor: Actor
) -> None:
    profile = Profile(user_id=actor.id, display_name="Old")
    repository.get_profile = AsyncMock(return_value=profile)

    result = await service.update_profile(actor, ProfileUpdate(display_name="New", bio="Grower"))

    assert result.display_name == "New"
    repository.add_audit.assert_awaited_once()
    repository.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_missing_profile_returns_not_found(
    service: ProfileService, repository: Any, actor: Actor
) -> None:
    repository.get_profile = AsyncMock(return_value=None)
    with pytest.raises(ApiError) as error:
        await service.get_profile(actor)
    assert error.value.status_code == 404
    assert error.value.code == "profile_not_found"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("role", "method", "payload", "model"),
    [
        ("farmer", "update_farmer", FarmerProfileUpdate(farm_name="Sunrise"), FarmerProfile),
        (
            "buyer",
            "update_buyer",
            BuyerProfileUpdate(buyer_type="business", organization_name="Soko Ltd"),
            BuyerProfile,
        ),
    ],
)
async def test_role_profile_created(
    service: ProfileService,
    repository: Any,
    actor: Actor,
    role: str,
    method: str,
    payload: object,
    model: type[object],
) -> None:
    repository.get_roles = AsyncMock(return_value={role})
    setattr(repository, f"get_{role}_profile", AsyncMock(return_value=None))

    result = await getattr(service, method)(actor, payload)

    assert isinstance(result, model)
    repository.add.assert_called_once()


@pytest.mark.anyio
async def test_role_profile_requires_assignment(
    service: ProfileService, repository: Any, actor: Actor
) -> None:
    repository.get_roles = AsyncMock(return_value=set())
    with pytest.raises(ApiError) as error:
        await service.update_farmer(actor, FarmerProfileUpdate(county="Nakuru"))
    assert error.value.status_code == 403
    assert error.value.code == "role_required"


@pytest.mark.anyio
async def test_existing_business_requires_organization_name(
    service: ProfileService, repository: Any, actor: Actor
) -> None:
    repository.get_roles = AsyncMock(return_value={"buyer"})
    repository.get_buyer_profile = AsyncMock(
        return_value=BuyerProfile(user_id=actor.id, buyer_type="individual")
    )
    with pytest.raises(ApiError) as error:
        await service.update_buyer(actor, BuyerProfileUpdate(buyer_type="institution"))
    assert error.value.status_code == 422
    assert error.value.code == "organization_name_required"


@pytest.mark.anyio
async def test_first_address_becomes_default(
    service: ProfileService, repository: Any, actor: Actor
) -> None:
    repository.address_count = AsyncMock(return_value=0)
    repository.clear_default_addresses = AsyncMock()

    result = await service.create_address(actor, address_payload())

    assert result.is_default is True
    repository.clear_default_addresses.assert_awaited_once_with(actor.id)


@pytest.mark.anyio
async def test_address_updates_are_owned_and_default_is_exclusive(
    service: ProfileService, repository: Any, actor: Actor
) -> None:
    address = Address(id=uuid4(), user_id=actor.id, **address_payload().model_dump())
    repository.get_address = AsyncMock(return_value=address)
    repository.clear_default_addresses = AsyncMock()

    result = await service.update_address(actor, address.id, AddressUpdate(is_default=True))

    assert result.is_default is True
    repository.clear_default_addresses.assert_awaited_once_with(actor.id, except_id=address.id)


@pytest.mark.anyio
async def test_foreign_address_is_hidden_as_not_found(
    service: ProfileService, repository: Any, actor: Actor
) -> None:
    repository.get_address = AsyncMock(return_value=None)
    with pytest.raises(ApiError) as error:
        await service.update_address(actor, uuid4(), AddressUpdate(label="Farm"))
    assert error.value.status_code == 404
    assert error.value.code == "address_not_found"


@pytest.mark.anyio
async def test_default_address_cannot_be_deleted_while_others_exist(
    service: ProfileService, repository: Any, actor: Actor
) -> None:
    address = Address(
        id=uuid4(),
        user_id=actor.id,
        is_default=True,
        **address_payload().model_dump(exclude={"is_default"}),
    )
    repository.get_address = AsyncMock(return_value=address)
    repository.address_count = AsyncMock(return_value=2)
    with pytest.raises(ApiError) as error:
        await service.delete_address(actor, address.id)
    assert error.value.status_code == 409
    assert error.value.code == "default_address_required"


@pytest.mark.anyio
async def test_only_address_can_be_deleted(
    service: ProfileService, repository: Any, actor: Actor
) -> None:
    address = Address(
        id=uuid4(),
        user_id=actor.id,
        is_default=True,
        **address_payload().model_dump(exclude={"is_default"}),
    )
    repository.get_address = AsyncMock(return_value=address)
    repository.address_count = AsyncMock(return_value=1)
    repository.delete_address = AsyncMock()
    await service.delete_address(actor, address.id)
    repository.delete_address.assert_awaited_once_with(address)


@pytest.mark.anyio
async def test_installation_token_is_hashed_and_raw_value_discarded(
    service: ProfileService, repository: Any, actor: Actor
) -> None:
    repository.get_installation = AsyncMock(return_value=None)
    token = "ExponentPushToken[secret-value]"

    result = await service.upsert_installation(
        actor, uuid4(), InstallationUpsert(platform="android", push_token=token)
    )

    assert result.push_token_hash is not None
    assert result.push_token_hash != token.encode()
    assert result.push_token_ciphertext is not None
    assert service.settings.push_token_encryption_key is not None
    assert service.settings.push_token_hash_key is not None
    protector = PushTokenProtector(
        encryption_key=service.settings.push_token_encryption_key,
        hash_key=service.settings.push_token_hash_key,
    )
    assert protector.decrypt(result.push_token_ciphertext) == token


@pytest.mark.anyio
async def test_installation_cannot_transfer_between_users(
    service: ProfileService, repository: Any, actor: Actor
) -> None:
    repository.get_installation = AsyncMock(
        return_value=DeviceInstallation(user_id=uuid4(), installation_id=uuid4(), platform="ios")
    )
    with pytest.raises(ApiError) as error:
        await service.upsert_installation(actor, uuid4(), InstallationUpsert(platform="ios"))
    assert error.value.status_code == 409
    assert error.value.code == "installation_conflict"


@pytest.mark.anyio
async def test_existing_installation_is_reactivated(
    service: ProfileService, repository: Any, actor: Actor
) -> None:
    installation_id = uuid4()
    installation = DeviceInstallation(
        id=uuid4(),
        user_id=actor.id,
        installation_id=installation_id,
        platform="web",
        revoked_at=datetime.now(UTC),
    )
    repository.get_installation = AsyncMock(return_value=installation)
    result = await service.upsert_installation(
        actor, installation_id, InstallationUpsert(platform="android")
    )
    assert result.platform == "android"
    assert result.revoked_at is None


@pytest.mark.anyio
async def test_push_registration_fails_closed_without_secret(repository: Any, actor: Actor) -> None:
    repository.get_installation = AsyncMock(return_value=None)
    service = ProfileService(cast(ProfileRepository, repository), Settings(environment="test"))
    with pytest.raises(ApiError) as error:
        await service.upsert_installation(
            actor,
            uuid4(),
            InstallationUpsert(platform="web", push_token="long-enough-token"),
        )
    assert error.value.status_code == 503
    assert error.value.code == "push_token_storage_unavailable"


@pytest.mark.anyio
async def test_installation_revoke_is_owned(
    service: ProfileService, repository: Any, actor: Actor
) -> None:
    repository.get_installation = AsyncMock(return_value=None)
    with pytest.raises(ApiError) as error:
        await service.revoke_installation(actor, uuid4())
    assert error.value.status_code == 404
    assert error.value.code == "installation_not_found"

    installation = DeviceInstallation(
        id=uuid4(), user_id=actor.id, installation_id=uuid4(), platform="ios", push_token_hash=b"x"
    )
    repository.get_installation = AsyncMock(return_value=installation)
    await service.revoke_installation(actor, installation.installation_id)
    assert installation.push_token_hash is None
    assert installation.revoked_at is not None


def test_profiles_fail_closed_without_authentication(client: Any) -> None:
    response = client.get("/api/v1/users/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
