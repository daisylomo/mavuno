from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response, status

from mavuno.api.dependencies import CurrentUser, DatabaseSession
from mavuno.commerce.repository import CommerceRepository
from mavuno.commerce.schemas import (
    CartItemUpsert,
    CartResponse,
    CheckoutRequest,
    FarmerOrderResponse,
    OrderItemResponse,
    OrderResponse,
    PaymentInitiateRequest,
    PaymentResponse,
)
from mavuno.commerce.service import CartService, CheckoutService, PaymentService

router = APIRouter(tags=["commerce"])
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)]


@router.get("/farmers/me/orders", response_model=list[FarmerOrderResponse])
async def farmer_orders(
    current_user: CurrentUser, session: DatabaseSession
) -> list[FarmerOrderResponse]:
    if not current_user.has_role("farmer"):
        from mavuno.api.errors import ApiError

        raise ApiError(
            status_code=403, code="farmer_role_required", message="The farmer role is required"
        )
    repository = CommerceRepository(session)
    rows = await repository.farmer_order_rows(current_user.id)
    grouped: dict[UUID, FarmerOrderResponse] = {}
    for order, item, buyer, profile, address in rows:
        response = grouped.get(order.id)
        if response is None:
            location = (
                None
                if address is None
                else f"{address.line_1}, {address.locality}, {address.county}"
            )
            phone = buyer.phone_e164 or await repository.paid_order_phone(order.id)
            response = FarmerOrderResponse(
                id=order.id,
                order_number=f"MVN-{str(order.id)[:8].upper()}",
                customer_name=profile.display_name if profile else buyer.email or "Buyer",
                customer_phone=phone,
                delivery_location=location,
                items=[],
                total_amount=Decimal("0"),
                status=order.status,
                created_at=order.created_at,
            )
            grouped[order.id] = response
        response.items.append(
            OrderItemResponse(
                listing_id=item.listing_id,
                farmer_id=item.farmer_id,
                product_name=item.product_name,
                listing_title=item.listing_title,
                quantity=item.quantity,
                quantity_unit=item.quantity_unit,
                unit_price=item.unit_price,
                line_total=item.line_total,
            )
        )
        response.total_amount += item.line_total
    return list(grouped.values())


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
    return await CheckoutService(
        CommerceRepository(session),
        request.app.state.settings,
        getattr(request.app.state, "catalog_cache", None),
    ).checkout(current_user, idempotency_key, payload.delivery_address_id)


@router.get("/users/me/orders", response_model=list[OrderResponse])
async def buyer_orders(
    current_user: CurrentUser, session: DatabaseSession, request: Request
) -> list[OrderResponse]:
    repository = CommerceRepository(session)
    service = CheckoutService(repository, request.app.state.settings)
    orders = await repository.buyer_orders(current_user.id)
    return [await service.response(order) for order in orders]


@router.get("/orders/{order_id}/payments", response_model=list[PaymentResponse])
async def order_payments(
    order_id: UUID, current_user: CurrentUser, session: DatabaseSession
) -> list[PaymentResponse]:
    repository = CommerceRepository(session)
    order = await repository.order(order_id)
    if order is None or order.buyer_id != current_user.id:
        from mavuno.api.errors import ApiError

        raise ApiError(status_code=404, code="order_not_found", message="Order was not found")
    return [
        PaymentResponse.model_validate(payment)
        for payment in await repository.order_payments(order_id)
    ]


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
