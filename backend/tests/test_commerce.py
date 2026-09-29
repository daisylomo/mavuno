from __future__ import annotations

from decimal import Decimal
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, create_autospec
from uuid import uuid4

import pytest

from mavuno.api.errors import ApiError
from mavuno.auth.context import AuthenticatedUser
from mavuno.commerce.repository import CommerceRepository
from mavuno.commerce.service import CartService, CheckoutService, _now
from mavuno.core.config import Settings
from mavuno.db.models import Cart, CartItem, Listing, Order, OrderItem


@pytest.fixture
def repository() -> Any:
    repo = create_autospec(CommerceRepository, instance=True)
    repo.add = MagicMock()
    repo.commit = AsyncMock()
    repo.rollback = AsyncMock()
    repo.refresh = AsyncMock()
    repo.lock_user = AsyncMock()
    return repo


@pytest.fixture
def buyer() -> AuthenticatedUser:
    return AuthenticatedUser(uuid4(), "buyer@example.test", None, frozenset({"buyer"}), 0)


def listing(quantity: str = "10") -> Listing:
    value = Listing(
        id=uuid4(),
        farmer_id=uuid4(),
        product_id=uuid4(),
        title="Maize",
        price_amount=Decimal("100"),
        currency="KES",
        available_quantity=Decimal(quantity),
        quantity_unit="kg",
        status="active",
        version=1,
    )
    value.created_at = _now()
    value.updated_at = _now()
    return value


@pytest.mark.anyio
async def test_cart_creation_response_and_role_guard(
    repository: Any, buyer: AuthenticatedUser
) -> None:
    repository.active_cart = AsyncMock(return_value=None)
    repository.cart_items = AsyncMock(return_value=[])

    async def stamp(value: Cart) -> None:
        value.created_at = _now()
        value.updated_at = _now()

    repository.refresh = AsyncMock(side_effect=stamp)
    response = await CartService(cast(CommerceRepository, repository)).get(buyer)
    assert response.items == []
    repository.lock_user.assert_awaited_once_with(buyer.id)
    repository.commit.assert_awaited_once()

    outsider = AuthenticatedUser(uuid4(), "farmer@example.test", None, frozenset({"farmer"}), 0)
    with pytest.raises(ApiError) as forbidden:
        await CartService(cast(CommerceRepository, repository)).get(outsider)
    assert forbidden.value.code == "buyer_role_required"


@pytest.mark.anyio
async def test_cart_upsert_validation_update_and_remove(
    repository: Any, buyer: AuthenticatedUser
) -> None:
    cart = Cart(id=uuid4(), buyer_id=buyer.id, status="active")
    repository.active_cart = AsyncMock(return_value=cart)
    repository.listing = AsyncMock(return_value=None)
    service = CartService(cast(CommerceRepository, repository))
    with pytest.raises(ApiError) as missing:
        await service.upsert(buyer, uuid4(), Decimal("1"))
    assert missing.value.code == "listing_not_found"

    available = listing("2")
    repository.listing = AsyncMock(return_value=available)
    with pytest.raises(ApiError) as insufficient:
        await service.upsert(buyer, available.id, Decimal("3"))
    assert insufficient.value.code == "insufficient_inventory"

    item = CartItem(id=uuid4(), cart_id=cart.id, listing_id=available.id, quantity=Decimal("1"))
    repository.cart_item = AsyncMock(return_value=item)
    repository.cart_items = AsyncMock(return_value=[item])
    response = await service.upsert(buyer, available.id, Decimal("2"))
    assert item.quantity == Decimal("2")
    assert response.subtotal_amount == Decimal("200")

    await service.remove(buyer, available.id)
    repository.delete_cart_item.assert_awaited_once_with(item)
    repository.active_cart = AsyncMock(return_value=None)
    await service.remove(buyer, available.id)


@pytest.mark.anyio
async def test_checkout_rejects_bad_address_empty_and_changed_inventory(
    repository: Any, buyer: AuthenticatedUser
) -> None:
    service = CheckoutService(cast(CommerceRepository, repository), Settings(environment="test"))
    repository.existing_order = AsyncMock(return_value=None)
    repository.address = AsyncMock(return_value=None)
    with pytest.raises(ApiError) as address:
        await service.checkout(buyer, "checkout-key", uuid4())
    assert address.value.code == "address_not_found"

    repository.active_cart = AsyncMock(return_value=None)
    with pytest.raises(ApiError) as empty:
        await service.checkout(buyer, "checkout-key", None)
    assert empty.value.code == "cart_empty"

    cart = Cart(id=uuid4(), buyer_id=buyer.id, status="active")
    item = CartItem(id=uuid4(), cart_id=cart.id, listing_id=uuid4(), quantity=Decimal("2"))
    repository.active_cart = AsyncMock(return_value=cart)
    repository.cart_items = AsyncMock(return_value=[item])
    repository.listing = AsyncMock(return_value=listing("1"))
    with pytest.raises(ApiError) as changed:
        await service.checkout(buyer, "checkout-key", None)
    assert changed.value.code == "inventory_changed"
    repository.rollback.assert_awaited()


@pytest.mark.anyio
async def test_order_visibility_response_and_expiry_noop(
    repository: Any, buyer: AuthenticatedUser
) -> None:
    settings = Settings(environment="test")
    service = CheckoutService(cast(CommerceRepository, repository), settings)
    repository.order = AsyncMock(return_value=None)
    with pytest.raises(ApiError) as missing:
        await service.get(buyer, uuid4())
    assert missing.value.code == "order_not_found"

    order = Order(
        id=uuid4(),
        buyer_id=buyer.id,
        status="pending_payment",
        currency="KES",
        subtotal_amount=Decimal("100"),
        total_amount=Decimal("100"),
        idempotency_key="key",
        reservation_expires_at=_now(),
        version=1,
    )
    order.created_at = _now()
    order.updated_at = _now()
    order_item = OrderItem(
        id=uuid4(),
        order_id=order.id,
        listing_id=uuid4(),
        farmer_id=uuid4(),
        product_name="Maize",
        listing_title="Dry maize",
        quantity=Decimal("1"),
        quantity_unit="kg",
        unit_price=Decimal("100"),
        line_total=Decimal("100"),
    )
    repository.order = AsyncMock(return_value=order)
    repository.order_items = AsyncMock(return_value=[order_item])
    response = await service.get(buyer, order.id)
    assert response.total_amount == Decimal("100")
    assert response.items[0].product_name == "Maize"

    order.status = "paid"
    await service.expire(order.id)
    repository.commit.assert_not_awaited()
