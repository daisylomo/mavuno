from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response, status

from mavuno.api.dependencies import CurrentUser, DatabaseSession
from mavuno.commerce.repository import CommerceRepository
from mavuno.commerce.schemas import (
    CartItemUpsert,
    CartResponse,
    CheckoutRequest,
    OrderResponse,
    PaymentInitiateRequest,
    PaymentResponse,
)
from mavuno.commerce.service import CartService, CheckoutService, PaymentService

router = APIRouter(tags=["commerce"])
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)]


@router.get("/cart", response_model=CartResponse)
async def get_cart(current_user: CurrentUser, session: DatabaseSession) -> CartResponse:
    return await CartService(CommerceRepository(session)).get(current_user)


@router.put("/cart/items/{listing_id}", response_model=CartResponse)
async def upsert_cart_item(
    listing_id: UUID,
    payload: CartItemUpsert,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> CartResponse:
    return await CartService(CommerceRepository(session)).upsert(
        current_user, listing_id, payload.quantity
    )


@router.delete("/cart/items/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cart_item(
    listing_id: UUID, current_user: CurrentUser, session: DatabaseSession
) -> Response:
    await CartService(CommerceRepository(session)).remove(current_user, listing_id)
    return Response(status_code=204)


@router.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def checkout(
    payload: CheckoutRequest,
    idempotency_key: IdempotencyKey,
    current_user: CurrentUser,
    session: DatabaseSession,
    request: Request,
) -> OrderResponse:
    return await CheckoutService(CommerceRepository(session), request.app.state.settings).checkout(
        current_user, idempotency_key, payload.delivery_address_id
    )


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
    request: Request,
) -> OrderResponse:
    return await CheckoutService(CommerceRepository(session), request.app.state.settings).get(
        current_user, order_id
    )


@router.post("/payments", response_model=PaymentResponse, status_code=status.HTTP_202_ACCEPTED)
async def initiate_payment(
    payload: PaymentInitiateRequest,
    idempotency_key: IdempotencyKey,
    current_user: CurrentUser,
    session: DatabaseSession,
    request: Request,
) -> object:
    return await PaymentService(CommerceRepository(session), request.app.state.settings).initiate(
        current_user, payload, idempotency_key
    )


@router.get("/payments/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: UUID, current_user: CurrentUser, session: DatabaseSession
) -> object:
    repository = CommerceRepository(session)
    payment = await repository.payment(payment_id)
    if payment is None:
        from mavuno.api.errors import ApiError

        raise ApiError(status_code=404, code="payment_not_found", message="Payment was not found")
    order = await repository.order(payment.order_id)
    if order is None or order.buyer_id != current_user.id:
        from mavuno.api.errors import ApiError

        raise ApiError(status_code=404, code="payment_not_found", message="Payment was not found")
    return payment


@router.post("/webhooks/payments/daraja/{callback_token}", status_code=202)
async def daraja_callback(
    callback_token: str,
    payload: dict[str, object],
    session: DatabaseSession,
    request: Request,
) -> dict[str, bool]:
    await PaymentService(CommerceRepository(session), request.app.state.settings).accept_callback(
        callback_token, payload
    )
    return {"accepted": True}
