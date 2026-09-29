from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, Response, status

from mavuno.api.dependencies import CurrentUser, DatabaseSession
from mavuno.db.models import Address, DeviceInstallation
from mavuno.profiles.repository import ProfileRepository
from mavuno.profiles.schemas import (
    AddressCreate,
    AddressResponse,
    AddressUpdate,
    BuyerProfileResponse,
    BuyerProfileUpdate,
    FarmerProfileResponse,
    FarmerProfileUpdate,
    InstallationResponse,
    InstallationUpsert,
    ProfileResponse,
    ProfileUpdate,
)
from mavuno.profiles.service import ProfileService

router = APIRouter(prefix="/users/me", tags=["profiles"])


def _service(session: DatabaseSession, request: Request) -> ProfileService:
    return ProfileService(ProfileRepository(session), request.app.state.settings)


def _installation_response(installation: DeviceInstallation) -> InstallationResponse:
    return InstallationResponse(
        id=installation.id,
        user_id=installation.user_id,
        installation_id=installation.installation_id,
        platform=installation.platform,
        has_push_token=installation.push_token_hash is not None,
        last_seen_at=installation.last_seen_at,
        revoked_at=installation.revoked_at,
        created_at=installation.created_at,
        updated_at=installation.updated_at,
    )


@router.get("", response_model=ProfileResponse)
async def get_profile(
    current_user: CurrentUser, session: DatabaseSession, request: Request
) -> object:
    return await _service(session, request).get_profile(current_user)


@router.patch("", response_model=ProfileResponse)
async def update_profile(
    payload: ProfileUpdate,
    current_user: CurrentUser,
    session: DatabaseSession,
    request: Request,
) -> object:
    return await _service(session, request).update_profile(current_user, payload)


@router.patch("/farmer", response_model=FarmerProfileResponse)
async def update_farmer_profile(
    payload: FarmerProfileUpdate,
    current_user: CurrentUser,
    session: DatabaseSession,
    request: Request,
) -> object:
    return await _service(session, request).update_farmer(current_user, payload)


@router.patch("/buyer", response_model=BuyerProfileResponse)
async def update_buyer_profile(
    payload: BuyerProfileUpdate,
    current_user: CurrentUser,
    session: DatabaseSession,
    request: Request,
) -> object:
    return await _service(session, request).update_buyer(current_user, payload)


@router.get("/addresses", response_model=list[AddressResponse])
async def list_addresses(current_user: CurrentUser, session: DatabaseSession) -> list[Address]:
    return await ProfileRepository(session).list_addresses(current_user.id)


@router.post("/addresses", response_model=AddressResponse, status_code=status.HTTP_201_CREATED)
async def create_address(
    payload: AddressCreate,
    current_user: CurrentUser,
    session: DatabaseSession,
    request: Request,
) -> object:
    return await _service(session, request).create_address(current_user, payload)


@router.patch("/addresses/{address_id}", response_model=AddressResponse)
async def update_address(
    address_id: UUID,
    payload: AddressUpdate,
    current_user: CurrentUser,
    session: DatabaseSession,
    request: Request,
) -> object:
    return await _service(session, request).update_address(current_user, address_id, payload)


@router.delete("/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_address(
    address_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
    request: Request,
) -> Response:
    await _service(session, request).delete_address(current_user, address_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/installations/{installation_id}", response_model=InstallationResponse)
async def register_installation(
    installation_id: UUID,
    payload: InstallationUpsert,
    current_user: CurrentUser,
    session: DatabaseSession,
    request: Request,
) -> InstallationResponse:
    installation = await _service(session, request).upsert_installation(
        current_user, installation_id, payload
    )
    return _installation_response(installation)


@router.delete("/installations/{installation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_installation(
    installation_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
    request: Request,
) -> Response:
    await _service(session, request).revoke_installation(current_user, installation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
