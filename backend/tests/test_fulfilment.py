from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, create_autospec
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from mavuno.api.errors import ApiError
from mavuno.auth.context import AuthenticatedUser
from mavuno.db.models import Fulfilment, FulfilmentStatusHistory, Order
from mavuno.fulfilment.repository import FulfilmentRepository
from mavuno.fulfilment.schemas import FulfilmentTransition, FulfilmentUpdate
from mavuno.fulfilment.service import FulfilmentService, _now


def user(role: str, *, user_id: UUID | None = None) -> AuthenticatedUser:
    return AuthenticatedUser(user_id or uuid4(), f"{role}@example.test", None, frozenset({role}), 0)


def order(buyer_id: UUID, status: str = "paid") -> Order:
    value = Order(
        id=uuid4(),
        buyer_id=buyer_id,
        status=status,
        currency="KES",
        subtotal_amount=Decimal("100"),
        total_amount=Decimal("100"),
        idempotency_key="checkout-key",
        reservation_expires_at=_now(),
        version=1,
    )
    value.created_at = _now()
    value.updated_at = _now()
    return value


def fulfilment(order_id: UUID, status: str = "pending", method: str = "pickup") -> Fulfilment:
    value = Fulfilment(
        id=uuid4(),
        order_id=order_id,
        method=method,
        status=status,
        location_label="Farm gate",
        location_details="Near the market",
        window_start=_now() + timedelta(hours=1),
        window_end=_now() + timedelta(hours=2),
        version=1,
    )
    value.created_at = _now()
    value.updated_at = _now()
    return value


def payload(**updates: Any) -> FulfilmentUpdate:
    values: dict[str, Any] = {
        "method": "pickup",
        "location_label": "Farm gate",
        "location_details": "Near the market",
        "window_start": _now() + timedelta(hours=1),
        "window_end": _now() + timedelta(hours=2),
    }
    values.update(updates)
    return FulfilmentUpdate(**values)


@pytest.fixture
def repository() -> Any:
    repo = create_autospec(FulfilmentRepository, instance=True)
    repo.add = MagicMock()
    repo.commit = AsyncMock()
    repo.rollback = AsyncMock()
    repo.refresh = AsyncMock()
    repo.history = AsyncMock(return_value=[])
    repo.farmer_ids = AsyncMock(return_value=set())
    return repo


@pytest.mark.anyio
async def test_buyer_creates_coordination_and_advances_order(repository: Any) -> None:
    buyer = user("buyer")
    current_order = order(buyer.id)
    repository.order = AsyncMock(return_value=current_order)
    repository.fulfilment = AsyncMock(return_value=None)

    async def stamp(value: Fulfilment) -> None:
        value.created_at = _now()
        value.updated_at = _now()

    repository.refresh = AsyncMock(side_effect=stamp)
    result = await FulfilmentService(cast(FulfilmentRepository, repository)).update(
        buyer, current_order.id, payload()
    )
    assert result.method == "pickup"
    assert current_order.status == "fulfilment"
    assert current_order.version == 2
    assert repository.add.call_count == 3
    repository.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_creation_requires_paid_order_buyer_and_complete_details(repository: Any) -> None:
    buyer = user("buyer")
    current_order = order(buyer.id, "pending_payment")
    repository.order = AsyncMock(return_value=current_order)
    with pytest.raises(ApiError, match="ready") as state:
        await FulfilmentService(cast(FulfilmentRepository, repository)).update(
            buyer, current_order.id, payload()
        )
    assert state.value.code == "order_not_fulfillable"

    current_order.status = "paid"
    repository.fulfilment = AsyncMock(return_value=None)
    farmer = user("farmer")
    repository.farmer_ids = AsyncMock(return_value={farmer.id})
    with pytest.raises(ApiError) as forbidden:
        await FulfilmentService(cast(FulfilmentRepository, repository)).update(
            farmer, current_order.id, payload()
        )
    assert forbidden.value.code == "fulfilment_forbidden"

    with pytest.raises(ApiError) as missing:
        await FulfilmentService(cast(FulfilmentRepository, repository)).update(
            buyer, current_order.id, FulfilmentUpdate(method="pickup")
        )
    assert missing.value.code == "fulfilment_details_required"


def test_payload_rejects_unpaired_coordinates() -> None:
    with pytest.raises(ValidationError):
        payload(latitude=Decimal("-1.2"))


@pytest.mark.anyio
async def test_update_requires_version_and_detects_conflict(repository: Any) -> None:
    buyer = user("buyer")
    current_order = order(buyer.id, "fulfilment")
    current = fulfilment(current_order.id)
    repository.order = AsyncMock(return_value=current_order)
    repository.fulfilment = AsyncMock(return_value=current)
    service = FulfilmentService(cast(FulfilmentRepository, repository))
    with pytest.raises(ApiError) as required:
        await service.update(buyer, current_order.id, FulfilmentUpdate(coordination_notes="Call"))
    assert required.value.code == "version_required"
    with pytest.raises(ApiError) as conflict:
        await service.update(
            buyer,
            current_order.id,
            FulfilmentUpdate(expected_version=2, coordination_notes="Call"),
        )
    assert conflict.value.code == "fulfilment_conflict"


@pytest.mark.anyio
async def test_update_validates_window_and_locks_late_coordination(repository: Any) -> None:
    buyer = user("buyer")
    current_order = order(buyer.id, "fulfilment")
    current = fulfilment(current_order.id)
    repository.order = AsyncMock(return_value=current_order)
    repository.fulfilment = AsyncMock(return_value=current)
    service = FulfilmentService(cast(FulfilmentRepository, repository))
    with pytest.raises(ApiError) as window:
        await service.update(
            buyer,
            current_order.id,
            FulfilmentUpdate(expected_version=1, window_end=current.window_start),
        )
    assert window.value.code == "invalid_fulfilment_window"
    with pytest.raises(ApiError) as required:
        await service.update(
            buyer,
            current_order.id,
            FulfilmentUpdate(expected_version=1, location_label=None),
        )
    assert required.value.code == "fulfilment_field_required"
    current.status = "ready_for_handover"
    with pytest.raises(ApiError) as locked:
        await service.update(
            buyer, current_order.id, FulfilmentUpdate(expected_version=1, coordination_notes="x")
        )
    assert locked.value.code == "coordination_locked"


@pytest.mark.anyio
async def test_visibility_is_order_linked(repository: Any) -> None:
    buyer = user("buyer")
    current_order = order(buyer.id, "fulfilment")
    current = fulfilment(current_order.id)
    repository.order = AsyncMock(return_value=current_order)
    repository.fulfilment = AsyncMock(return_value=current)
    service = FulfilmentService(cast(FulfilmentRepository, repository))
    assert (await service.get(buyer, current_order.id)).id == current.id

    farmer = user("farmer")
    repository.farmer_ids = AsyncMock(return_value={farmer.id})
    assert (await service.get(farmer, current_order.id)).id == current.id
    repository.farmer_ids = AsyncMock(return_value=set())
    with pytest.raises(ApiError) as hidden:
        await service.get(farmer, current_order.id)
    assert hidden.value.status_code == 404

    repository.order = AsyncMock(return_value=None)
    with pytest.raises(ApiError) as missing:
        await service.get(buyer, uuid4())
    assert missing.value.code == "order_not_found"


@pytest.mark.anyio
async def test_transition_permissions_and_method_consistency(repository: Any) -> None:
    buyer = user("buyer")
    farmer = user("farmer")
    current_order = order(buyer.id, "fulfilment")
    current = fulfilment(current_order.id)
    repository.order = AsyncMock(return_value=current_order)
    repository.fulfilment = AsyncMock(return_value=current)
    repository.farmer_ids = AsyncMock(return_value={farmer.id})
    service = FulfilmentService(cast(FulfilmentRepository, repository))
    result = await service.transition(
        farmer, current_order.id, FulfilmentTransition(status="scheduled", expected_version=1)
    )
    assert result.status == "scheduled"

    current.status = "ready_for_handover"
    current.version = 3
    with pytest.raises(ApiError) as pickup_transit:
        await service.transition(
            farmer,
            current_order.id,
            FulfilmentTransition(status="in_transit", expected_version=3),
        )
    assert pickup_transit.value.code == "invalid_fulfilment_transition"


@pytest.mark.anyio
async def test_buyer_completion_keeps_order_consistent(repository: Any) -> None:
    buyer = user("buyer")
    current_order = order(buyer.id, "fulfilment")
    current = fulfilment(current_order.id, "ready_for_handover")
    repository.order = AsyncMock(return_value=current_order)
    repository.fulfilment = AsyncMock(return_value=current)
    result = await FulfilmentService(cast(FulfilmentRepository, repository)).transition(
        buyer,
        current_order.id,
        FulfilmentTransition(status="completed", expected_version=1, reason="Collected"),
    )
    assert result.status == "completed"
    assert result.completed_at is not None
    assert current_order.status == "completed"
    assert repository.add.call_count == 2


@pytest.mark.anyio
async def test_transition_rejects_missing_stale_invalid_and_forbidden(repository: Any) -> None:
    buyer = user("buyer")
    current_order = order(buyer.id, "fulfilment")
    repository.order = AsyncMock(return_value=current_order)
    repository.fulfilment = AsyncMock(return_value=None)
    service = FulfilmentService(cast(FulfilmentRepository, repository))
    current_order.status = "paid"
    with pytest.raises(ApiError) as inconsistent:
        await service.transition(
            buyer, current_order.id, FulfilmentTransition(status="scheduled", expected_version=1)
        )
    assert inconsistent.value.code == "order_fulfilment_inconsistent"
    current_order.status = "fulfilment"
    with pytest.raises(ApiError) as missing:
        await service.transition(
            buyer, current_order.id, FulfilmentTransition(status="scheduled", expected_version=1)
        )
    assert missing.value.code == "fulfilment_not_found"

    current = fulfilment(current_order.id)
    repository.fulfilment = AsyncMock(return_value=current)
    with pytest.raises(ApiError) as stale:
        await service.transition(
            buyer, current_order.id, FulfilmentTransition(status="scheduled", expected_version=2)
        )
    assert stale.value.code == "fulfilment_conflict"
    with pytest.raises(ApiError) as invalid:
        await service.transition(
            buyer, current_order.id, FulfilmentTransition(status="completed", expected_version=1)
        )
    assert invalid.value.code == "invalid_fulfilment_transition"
    with pytest.raises(ApiError) as forbidden:
        await service.transition(
            buyer, current_order.id, FulfilmentTransition(status="scheduled", expected_version=1)
        )
    assert forbidden.value.code == "fulfilment_transition_forbidden"


@pytest.mark.anyio
async def test_buyer_can_cancel_and_admin_can_drive_delivery(repository: Any) -> None:
    buyer = user("buyer")
    admin = user("administrator")
    current_order = order(buyer.id, "fulfilment")
    current = fulfilment(current_order.id)
    repository.order = AsyncMock(return_value=current_order)
    repository.fulfilment = AsyncMock(return_value=current)
    service = FulfilmentService(cast(FulfilmentRepository, repository))
    assert (
        await service.transition(
            buyer,
            current_order.id,
            FulfilmentTransition(status="cancelled", expected_version=1),
        )
    ).status == "cancelled"
    assert current_order.status == "cancelled"
    assert current_order.version == 2
    assert repository.add.call_count == 2

    current_order.status = "fulfilment"
    current.status = "ready_for_handover"
    current.method = "delivery"
    current.version = 3
    assert (
        await service.transition(
            admin,
            current_order.id,
            FulfilmentTransition(status="in_transit", expected_version=3),
        )
    ).status == "in_transit"


@pytest.mark.anyio
async def test_admin_cannot_put_pickup_in_transit(repository: Any) -> None:
    admin = user("administrator")
    current_order = order(uuid4(), "fulfilment")
    current = fulfilment(current_order.id, "ready_for_handover", method="pickup")
    repository.order = AsyncMock(return_value=current_order)
    repository.fulfilment = AsyncMock(return_value=current)

    with pytest.raises(ApiError) as invalid:
        await FulfilmentService(cast(FulfilmentRepository, repository)).transition(
            admin,
            current_order.id,
            FulfilmentTransition(status="in_transit", expected_version=1),
        )
    assert invalid.value.code == "invalid_fulfilment_transition"
    assert current.status == "ready_for_handover"
    repository.commit.assert_not_awaited()


@pytest.mark.anyio
async def test_unique_creation_race_becomes_stable_conflict(repository: Any) -> None:
    buyer = user("buyer")
    current_order = order(buyer.id)
    repository.order = AsyncMock(return_value=current_order)
    repository.fulfilment = AsyncMock(return_value=None)
    repository.commit = AsyncMock(side_effect=IntegrityError("insert", {}, Exception()))
    with pytest.raises(ApiError) as conflict:
        await FulfilmentService(cast(FulfilmentRepository, repository)).update(
            buyer, current_order.id, payload()
        )
    assert conflict.value.code == "fulfilment_conflict"
    repository.rollback.assert_awaited_once()


@pytest.mark.anyio
async def test_get_missing_fulfilment_and_history_response(repository: Any) -> None:
    admin = user("administrator")
    current_order = order(uuid4(), "fulfilment")
    repository.order = AsyncMock(return_value=current_order)
    repository.fulfilment = AsyncMock(return_value=None)
    service = FulfilmentService(cast(FulfilmentRepository, repository))
    with pytest.raises(ApiError) as missing:
        await service.get(admin, current_order.id)
    assert missing.value.code == "fulfilment_not_found"

    current = fulfilment(current_order.id)
    event = FulfilmentStatusHistory(
        id=uuid4(),
        fulfilment_id=current.id,
        actor_user_id=admin.id,
        previous_status=None,
        new_status="pending",
        reason="Created",
    )
    event.created_at = _now()
    repository.fulfilment = AsyncMock(return_value=current)
    repository.history = AsyncMock(return_value=[event])
    assert (await service.get(admin, current_order.id)).history[0].new_status == "pending"
