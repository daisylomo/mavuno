from typing import List
from api_client.models.base import ApiResponse
from api_client.models.profiles import (
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
from api_client.services.base import BaseService


class ProfilesService(BaseService):
    def get_profile(self) -> ApiResponse[ProfileResponse]:
        res = self._execute(method="GET", path="/users/me")
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=ProfileResponse.from_dict(res.data),
            success=True,
        )

    def update_profile(self, req: ProfileUpdate) -> ApiResponse[ProfileResponse]:
        res = self._execute(method="PATCH", path="/users/me", json_payload=req.to_dict())
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=ProfileResponse.from_dict(res.data),
            success=True,
        )

    def update_farmer_profile(self, req: FarmerProfileUpdate) -> ApiResponse[FarmerProfileResponse]:
        res = self._execute(method="PATCH", path="/users/me/farmer", json_payload=req.to_dict())
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=FarmerProfileResponse.from_dict(res.data),
            success=True,
        )

    def update_buyer_profile(self, req: BuyerProfileUpdate) -> ApiResponse[BuyerProfileResponse]:
        res = self._execute(method="PATCH", path="/users/me/buyer", json_payload=req.to_dict())
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=BuyerProfileResponse.from_dict(res.data),
            success=True,
        )

    def list_addresses(self) -> ApiResponse[List[AddressResponse]]:
        res = self._execute(method="GET", path="/users/me/addresses")
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=[AddressResponse.from_dict(item) for item in res.data],
            success=True,
        )

    def create_address(self, req: AddressCreate) -> ApiResponse[AddressResponse]:
        res = self._execute(method="POST", path="/users/me/addresses", json_payload=req.to_dict())
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=AddressResponse.from_dict(res.data),
            success=True,
        )

    def update_address(self, address_id: str, req: AddressUpdate) -> ApiResponse[AddressResponse]:
        res = self._execute(
            method="PATCH",
            path=f"/users/me/addresses/{address_id}",
            json_payload=req.to_dict(),
        )
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=AddressResponse.from_dict(res.data),
            success=True,
        )

    def delete_address(self, address_id: str) -> ApiResponse[None]:
        res = self._execute(method="DELETE", path=f"/users/me/addresses/{address_id}")
        return ApiResponse(status_code=res.status_code, error=res.error, success=res.success)

    def register_installation(
        self, installation_id: str, req: InstallationUpsert
    ) -> ApiResponse[InstallationResponse]:
        res = self._execute(
            method="PUT",
            path=f"/users/me/installations/{installation_id}",
            json_payload=req.to_dict(),
        )
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=InstallationResponse.from_dict(res.data),
            success=True,
        )

    def revoke_installation(self, installation_id: str) -> ApiResponse[None]:
        res = self._execute(
            method="DELETE",
            path=f"/users/me/installations/{installation_id}",
        )
        return ApiResponse(status_code=res.status_code, error=res.error, success=res.success)