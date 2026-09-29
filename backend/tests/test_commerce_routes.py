from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from mavuno.api.errors import ApiError
from mavuno.api.v1 import commerce
from mavuno.auth.context import AuthenticatedUser
from mavuno.commerce.schemas import CartItemUpsert, CheckoutRequest, PaymentInitiateRequest
from mavuno.core.config import Settings


@pytest.mark.anyio
async def test_commerce_routes_delegate_to_services(monkeypatch: pytest.MonkeyPatch) -> None:
    user = AuthenticatedUser(uuid4(), "buyer@example.test", None, frozenset({"buyer"}), 0)
    listing_id, order_id = uuid4(), uuid4()
    session = MagicMock()
    request = cast(
        Any, SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=Settings())))
    )

    cart_service = MagicMock()
    cart_service.get = AsyncMock(return_value="cart")
    cart_service.upsert = AsyncMock(return_value="updated-cart")
    cart_service.remove = AsyncMock()
    checkout_service = MagicMock()
    checkout_service.checkout = AsyncMock(return_value="order")
    checkout_service.get = AsyncMock(return_value="stored-order")
    payment_service = MagicMock()
    payment_service.initiate = AsyncMock(return_value="payment")
    payment_service.accept_callback = AsyncMock()
    monkeypatch.setattr(commerce, "CartService", lambda *_args: cart_service)
    monkeypatch.setattr(commerce, "CheckoutService", lambda *_args: checkout_service)
    monkeypatch.setattr(commerce, "PaymentService", lambda *_args: payment_service)

    cart_result: Any = await commerce.get_cart(user, session)
    assert cart_result == "cart"
    upsert_result: Any = await commerce.upsert_cart_item(
        listing_id, CartItemUpsert(quantity=1), user, session
    )
    assert upsert_result == "updated-cart"
    response = await commerce.delete_cart_item(listing_id, user, session)
    assert response.status_code == 204
    checkout_result: Any = await commerce.checkout(
        CheckoutRequest(), "checkout-key", user, session, request
    )
    assert checkout_result == "order"
    order_result: Any = await commerce.get_order(order_id, user, session, request)
    assert order_result == "stored-order"
    assert (
        await commerce.initiate_payment(
            PaymentInitiateRequest(order_id=order_id, rail="mpesa", phone_e164="0712345678"),
            "payment-key",
            user,
            session,
            request,
        )
        == "payment"
    )
    assert await commerce.daraja_callback("token", {}, session, request) == {"accepted": True}


@pytest.mark.anyio
async def test_get_payment_enforces_buyer_ownership(monkeypatch: pytest.MonkeyPatch) -> None:
    user = AuthenticatedUser(uuid4(), "buyer@example.test", None, frozenset({"buyer"}), 0)
    repository = MagicMock()
    repository.payment = AsyncMock(return_value=None)
    repository.order = AsyncMock()
    monkeypatch.setattr(commerce, "CommerceRepository", lambda _session: repository)
    with pytest.raises(ApiError) as missing:
        await commerce.get_payment(uuid4(), user, MagicMock())
    assert missing.value.code == "payment_not_found"

    payment = SimpleNamespace(order_id=uuid4())
    repository.payment = AsyncMock(return_value=payment)
    repository.order = AsyncMock(return_value=SimpleNamespace(buyer_id=uuid4()))
    with pytest.raises(ApiError) as hidden:
        await commerce.get_payment(uuid4(), user, MagicMock())
    assert hidden.value.code == "payment_not_found"

    repository.order = AsyncMock(return_value=SimpleNamespace(buyer_id=user.id))
    assert await commerce.get_payment(uuid4(), user, MagicMock()) is payment
