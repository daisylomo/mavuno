import uuid
from typing import Optional

from api_client.models.base import ApiResponse
from api_client.models.commerce import (
    CartItemUpsert,
    CartResponse,
    CheckoutRequest,
    OrderResponse,
    PaymentInitiateRequest,
    PaymentResponse,
)
from api_client.services.base import BaseService


class CommerceService(BaseService):
    def get_cart(self) -> ApiResponse[CartResponse]:
        res = self._execute(method="GET", path="/cart")
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=CartResponse.from_dict(res.data),
            success=True,
        )

    def upsert_cart_item(self, listing_id: str, req: CartItemUpsert) -> ApiResponse[CartResponse]:
        res = self._execute(
            method="PUT",
            path=f"/cart/items/{listing_id}",
            json_payload=req.to_dict(),
        )
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=CartResponse.from_dict(res.data),
            success=True,
        )

    def delete_cart_item(self, listing_id: str) -> ApiResponse[None]:
        res = self._execute(method="DELETE", path=f"/cart/items/{listing_id}")
        return ApiResponse(status_code=res.status_code, error=res.error, success=res.success)

    def checkout(
        self, req: CheckoutRequest, idempotency_key: Optional[str] = None
    ) -> ApiResponse[OrderResponse]:
        key = idempotency_key or str(uuid.uuid4())
        # Pass Idempotency-Key directly in request headers
        headers = {"Idempotency-Key": key}

        # Use session to send with custom headers
        url = f"{self.base_url}/orders"
        try:
            resp = self.session.post(url, json=req.to_dict(), headers=headers)
            status_code = resp.status_code
            if 200 <= status_code < 300:
                return ApiResponse(
                    status_code=status_code,
                    data=OrderResponse.from_dict(resp.json()),
                    success=True,
                )
            return ApiResponse(
                status_code=status_code,
                error=resp.text,
                success=False,
            )
        except Exception as exc:
            return ApiResponse(status_code=500, error=str(exc), success=False)

    def get_order(self, order_id: str) -> ApiResponse[OrderResponse]:
        res = self._execute(method="GET", path=f"/orders/{order_id}")
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=OrderResponse.from_dict(res.data),
            success=True,
        )

    def initiate_payment(
        self, req: PaymentInitiateRequest, idempotency_key: Optional[str] = None
    ) -> ApiResponse[PaymentResponse]:
        key = idempotency_key or str(uuid.uuid4())
        headers = {"Idempotency-Key": key}
        url = f"{self.base_url}/payments"

        try:
            resp = self.session.post(url, json=req.to_dict(), headers=headers)
            status_code = resp.status_code
            if 200 <= status_code < 300:
                return ApiResponse(
                    status_code=status_code,
                    data=PaymentResponse.from_dict(resp.json()),
                    success=True,
                )
            return ApiResponse(
                status_code=status_code,
                error=resp.text,
                success=False,
            )
        except Exception as exc:
            return ApiResponse(status_code=500, error=str(exc), success=False)

    def get_payment(self, payment_id: str) -> ApiResponse[PaymentResponse]:
        res = self._execute(method="GET", path=f"/payments/{payment_id}")
        if not res.success or res.data is None:
            return ApiResponse(status_code=res.status_code, error=res.error, success=False)
        return ApiResponse(
            status_code=res.status_code,
            data=PaymentResponse.from_dict(res.data),
            success=True,
        )