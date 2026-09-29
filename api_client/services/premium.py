import uuid
from typing import List, Optional
from api_client.models.base import ApiResponse
from api_client.models.premium import (
    FarmerInsightsResponse,
    PlanCreate,
    PlanResponse,
    PrebookingCreate,
    PrebookingResponse,
    PrebookingTransition,
    SubscriptionCreate,
    SubscriptionResponse,
)
from api_client.services.base import BaseService


class PremiumService(BaseService):
    def list_plans(self) -> ApiResponse[List[PlanResponse]]:
        res = self._execute(method="GET", path="/premium/plans")
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=[PlanResponse.from_dict(item) for item in res.data],
            success=True,
        )

    def create_plan(self, req: PlanCreate) -> ApiResponse[PlanResponse]:
        res = self._execute(method="POST", path="/premium/plans", json_payload=req.to_dict())
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=PlanResponse.from_dict(res.data),
            success=True,
        )

    def list_subscriptions(self) -> ApiResponse[List[SubscriptionResponse]]:
        res = self._execute(method="GET", path="/premium/subscriptions")
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=[SubscriptionResponse.from_dict(item) for item in res.data],
            success=True,
        )

    def initiate_subscription(
        self, req: SubscriptionCreate, idempotency_key: Optional[str] = None
    ) -> ApiResponse[SubscriptionResponse]:
        key = idempotency_key or str(uuid.uuid4())
        url = f"{self.base_url}/premium/subscriptions"
        try:
            resp = self.session.post(
                url,
                json=req.to_dict(),
                headers={"Idempotency-Key": key},
            )
            status_code = resp.status_code
            if 200 <= status_code < 300:
                return ApiResponse(
                    status_code=status_code,
                    data=SubscriptionResponse.from_dict(resp.json()),
                    success=True,
                )
            return ApiResponse(status_code=status_code, error=resp.text, success=False)
        except Exception as exc:
            return ApiResponse(status_code=500, error=str(exc), success=False)

    def list_prebookings(self) -> ApiResponse[List[PrebookingResponse]]:
        res = self._execute(method="GET", path="/prebookings")
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=[PrebookingResponse.from_dict(item) for item in res.data],
            success=True,
        )

    def create_prebooking(self, req: PrebookingCreate) -> ApiResponse[PrebookingResponse]:
        res = self._execute(method="POST", path="/prebookings", json_payload=req.to_dict())
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=PrebookingResponse.from_dict(res.data),
            success=True,
        )

    def transition_prebooking(
        self, prebooking_id: str, req: PrebookingTransition
    ) -> ApiResponse[PrebookingResponse]:
        res = self._execute(
            method="POST",
            path=f"/prebookings/{prebooking_id}/status",
            json_payload=req.to_dict(),
        )
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=PrebookingResponse.from_dict(res.data),
            success=True,
        )

    def get_farmer_insights(self) -> ApiResponse[FarmerInsightsResponse]:
        res = self._execute(method="GET", path="/premium/insights/farmer")
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=FarmerInsightsResponse.from_dict(res.data),
            success=True,
        )