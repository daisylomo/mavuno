from api_client.models.base import ApiResponse
from api_client.models.fulfilment import (
    FulfilmentResponse,
    FulfilmentTransition,
    FulfilmentUpdate,
)
from api_client.services.base import BaseService


class FulfilmentService(BaseService):
    def get_fulfilment(self, order_id: str) -> ApiResponse[FulfilmentResponse]:
        res = self._execute(method="GET", path=f"/fulfilments/{order_id}")
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=FulfilmentResponse.from_dict(res.data),
            success=True,
        )

    def update_fulfilment(
        self, order_id: str, req: FulfilmentUpdate
    ) -> ApiResponse[FulfilmentResponse]:
        res = self._execute(
            method="PATCH",
            path=f"/fulfilments/{order_id}",
            json_payload=req.to_dict(),
        )
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=FulfilmentResponse.from_dict(res.data),
            success=True,
        )

    def transition_fulfilment(
        self, order_id: str, req: FulfilmentTransition
    ) -> ApiResponse[FulfilmentResponse]:
        res = self._execute(
            method="POST",
            path=f"/fulfilments/{order_id}/status",
            json_payload=req.to_dict(),
        )
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=FulfilmentResponse.from_dict(res.data),
            success=True,
        )