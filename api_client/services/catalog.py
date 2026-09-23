from typing import Optional
from api_client.models.base import ApiResponse
from api_client.models.catalog import (
    InventoryChangeRequest,
    ListingCreateRequest,
    ListingFilterRequest,
    ListingPage,
    ListingResponse,
    ListingUpdateRequest,
)
from api_client.services.base import BaseService


class CatalogService(BaseService):
    def list_listings(self, filters: Optional[ListingFilterRequest] = None) -> ApiResponse[ListingPage]:
        params = filters.to_params() if filters else None
        res = self._execute(method="GET", path="/listings", params=params)
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=ListingPage.from_dict(res.data),
            success=True,
        )

    def get_listing(self, listing_id: str) -> ApiResponse[ListingResponse]:
        res = self._execute(method="GET", path=f"/listings/{listing_id}")
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=ListingResponse.from_dict(res.data),
            success=True,
        )

    def create_listing(self, req: ListingCreateRequest) -> ApiResponse[ListingResponse]:
        res = self._execute(method="POST", path="/listings", json_payload=req.to_dict())
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=ListingResponse.from_dict(res.data),
            success=True,
        )

    def update_listing(self, listing_id: str, req: ListingUpdateRequest) -> ApiResponse[ListingResponse]:
        res = self._execute(method="PATCH", path=f"/listings/{listing_id}", json_payload=req.to_dict())
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=ListingResponse.from_dict(res.data),
            success=True,
        )

    def archive_listing(self, listing_id: str, expected_version: int) -> ApiResponse[None]:
        res = self._execute(
            method="DELETE",
            path=f"/listings/{listing_id}",
            params={"expected_version": expected_version},
        )
        return ApiResponse(status_code=res.status_code, error=res.error, success=res.success)

    def change_inventory(self, listing_id: str, req: InventoryChangeRequest) -> ApiResponse[ListingResponse]:
        res = self._execute(
            method="POST",
            path=f"/listings/{listing_id}/inventory",
            json_payload=req.to_dict(),
        )
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=ListingResponse.from_dict(res.data),
            success=True,
        )