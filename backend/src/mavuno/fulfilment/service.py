from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from mavuno.api.errors import ApiError
from mavuno.auth.context import AuthenticatedUser
from mavuno.db.models import Fulfilment, FulfilmentStatusHistory, Order, OrderStatusHistory
from mavuno.fulfilment.repository import FulfilmentRepository
from mavuno.fulfilment.schemas import (
    FulfilmentResponse,
    FulfilmentTransition,
    FulfilmentUpdate,
)

TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"scheduled", "cancelled"}),
    "scheduled": frozenset({"ready_for_handover", "cancelled"}),
    "ready_for_handover": frozenset({"in_transit", "completed", "cancelled"}),
    "in_transit": frozenset({"completed", "cancelled"}),
    "completed": frozenset(),
    "cancelled": frozenset(),
}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class FulfilmentService:
    def __init__(self, repository: FulfilmentRepository) -> None:
        self.repository = repository

    async def get(self, actor: AuthenticatedUser, order_id: UUID) -> FulfilmentResponse:
        order = await self.repository.order(order_id)
        await self._authorize(actor, order, order_id)
        fulfilment = await self.repository.fulfilment(order_id)
        if fulfilment is None:
            raise ApiError(
                status_code=404, code="fulfilment_not_found", message="Fulfilment was not found"
            )
        return await self._response(fulfilment)

    async def update(
        self, actor: AuthenticatedUser, order_id: UUID, payload: FulfilmentUpdate
    ) -> FulfilmentResponse:
        order = await self.repository.order(order_id, lock=True)
        await self._authorize(actor, order, order_id)
        assert order is not None
        if order.status not in {"paid", "fulfilment"}:
            raise ApiError(
                status_code=409,
                code="order_not_fulfillable",
                message="Order is not ready for fulfilment",
            )
        fulfilment = await self.repository.fulfilment(order.id, lock=True)
        if fulfilment is None:
            self._require_buyer_or_admin(actor, order.buyer_id)
            fulfilment = self._new(order.id, payload)
            self.repository.add(fulfilment)
            self.repository.add(
                FulfilmentStatusHistory(
                    id=uuid4(),
                    fulfilment_id=fulfilment.id,
                    actor_user_id=actor.id,
                    previous_status=None,
                    new_status="pending",
                    reason="Coordination created",
                )
            )
            if order.status == "paid":
                order.status = "fulfilment"
                order.version += 1
                self.repository.add(
                    OrderStatusHistory(
                        id=uuid4(),
                        order_id=order.id,
                        actor_user_id=actor.id,
                        previous_status="paid",
                        new_status="fulfilment",
                        reason="Fulfilment coordination created",
                    )
                )
        else:
            if payload.expected_version is None:
                raise ApiError(
                    status_code=422, code="version_required", message="expected_version is required"
                )
            if fulfilment.version != payload.expected_version:
                raise ApiError(
                    status_code=409, code="fulfilment_conflict", message="Fulfilment has changed"
                )
            if fulfilment.status not in {"pending", "scheduled"}:
                raise ApiError(
                    status_code=409,
                    code="coordination_locked",
                    message="Coordination details are locked",
                )
            self._require_buyer_farmer_or_admin(actor, order.buyer_id)
            self._apply(fulfilment, payload)
            fulfilment.version += 1
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ApiError(
                status_code=409, code="fulfilment_conflict", message="Fulfilment has changed"
            ) from exc
        await self.repository.refresh(fulfilment)
        return await self._response(fulfilment)

    async def transition(
        self, actor: AuthenticatedUser, order_id: UUID, payload: FulfilmentTransition
    ) -> FulfilmentResponse:
        order = await self.repository.order(order_id, lock=True)
        await self._authorize(actor, order, order_id)
        assert order is not None
        if order.status != "fulfilment":
            raise ApiError(
                status_code=409,
                code="order_fulfilment_inconsistent",
                message="Order is not in fulfilment",
            )
        fulfilment = await self.repository.fulfilment(order.id, lock=True)
        if fulfilment is None:
            raise ApiError(
                status_code=404, code="fulfilment_not_found", message="Fulfilment was not found"
            )
        if fulfilment.version != payload.expected_version:
            raise ApiError(
                status_code=409, code="fulfilment_conflict", message="Fulfilment has changed"
            )
        if payload.status not in TRANSITIONS[fulfilment.status]:
            raise ApiError(
                status_code=409,
                code="invalid_fulfilment_transition",
                message="Transition is not allowed",
            )
        if payload.status == "in_transit" and fulfilment.method != "delivery":
            raise ApiError(
                status_code=409,
                code="invalid_fulfilment_transition",
                message="Pickup fulfilment cannot enter transit",
            )
        self._authorize_transition(actor, order.buyer_id, fulfilment.method, payload.status)
        previous = fulfilment.status
        fulfilment.status = payload.status
        fulfilment.version += 1
        if payload.status == "completed":
            fulfilment.completed_at = _now()
            order.status = "completed"
            order.version += 1
            self.repository.add(
                OrderStatusHistory(
                    id=uuid4(),
                    order_id=order.id,
                    actor_user_id=actor.id,
                    previous_status="fulfilment",
                    new_status="completed",
                    reason="Fulfilment completed",
                )
            )
        elif payload.status == "cancelled":
            order.status = "cancelled"
            order.version += 1
            self.repository.add(
                OrderStatusHistory(
                    id=uuid4(),
                    order_id=order.id,
                    actor_user_id=actor.id,
                    previous_status="fulfilment",
                    new_status="cancelled",
                    reason="Fulfilment cancelled; payment resolution remains separate",
                )
            )
        self.repository.add(
            FulfilmentStatusHistory(
                id=uuid4(),
                fulfilment_id=fulfilment.id,
                actor_user_id=actor.id,
                previous_status=previous,
                new_status=payload.status,
                reason=payload.reason,
            )
        )
        await self.repository.commit()
        await self.repository.refresh(fulfilment)
        return await self._response(fulfilment)

    async def _authorize(
        self, actor: AuthenticatedUser, order: Order | None, order_id: UUID
    ) -> None:
        if order is None:
            raise ApiError(status_code=404, code="order_not_found", message="Order was not found")
        buyer_id = order.buyer_id
        if actor.has_role("administrator") or actor.id == buyer_id:
            return
        if actor.has_role("farmer") and actor.id in await self.repository.farmer_ids(order_id):
            return
        raise ApiError(status_code=404, code="order_not_found", message="Order was not found")

    @staticmethod
    def _require_buyer_or_admin(actor: AuthenticatedUser, buyer_id: UUID) -> None:
        if actor.id != buyer_id and not actor.has_role("administrator"):
            raise ApiError(
                status_code=403, code="fulfilment_forbidden", message="Action is not permitted"
            )

    @staticmethod
    def _require_buyer_farmer_or_admin(actor: AuthenticatedUser, buyer_id: UUID) -> None:
        if actor.id != buyer_id and not actor.has_role("farmer", "administrator"):
            raise ApiError(
                status_code=403, code="fulfilment_forbidden", message="Action is not permitted"
            )

    @staticmethod
    def _authorize_transition(
        actor: AuthenticatedUser, buyer_id: UUID, method: str, target: str
    ) -> None:
        if actor.has_role("administrator"):
            return
        if target in {"scheduled", "ready_for_handover"} and actor.has_role("farmer"):
            return
        if target == "in_transit" and method == "delivery" and actor.has_role("farmer"):
            return
        if target == "completed" and actor.id == buyer_id:
            return
        if target == "cancelled" and actor.id == buyer_id:
            return
        raise ApiError(
            status_code=403,
            code="fulfilment_transition_forbidden",
            message="Transition is not permitted",
        )

    @staticmethod
    def _new(order_id: UUID, payload: FulfilmentUpdate) -> Fulfilment:
        missing = [
            name
            for name in (
                "method",
                "location_label",
                "location_details",
                "window_start",
                "window_end",
            )
            if getattr(payload, name) is None
        ]
        if missing:
            raise ApiError(
                status_code=422,
                code="fulfilment_details_required",
                message="Initial coordination details are required",
                details={"fields": missing},
            )
        assert payload.window_start is not None and payload.window_end is not None
        assert payload.method is not None
        assert payload.location_label is not None and payload.location_details is not None
        if payload.window_end <= payload.window_start:
            raise ApiError(
                status_code=422,
                code="invalid_fulfilment_window",
                message="Window end must follow its start",
            )
        return Fulfilment(
            id=uuid4(),
            order_id=order_id,
            method=payload.method,
            status="pending",
            location_label=payload.location_label,
            location_details=payload.location_details,
            latitude=payload.latitude,
            longitude=payload.longitude,
            window_start=payload.window_start,
            window_end=payload.window_end,
            coordination_notes=payload.coordination_notes,
            version=1,
        )

    @staticmethod
    def _apply(value: Fulfilment, payload: FulfilmentUpdate) -> None:
        required = {
            "method",
            "location_label",
            "location_details",
            "window_start",
            "window_end",
        }
        for name in (
            "method",
            "location_label",
            "location_details",
            "latitude",
            "longitude",
            "window_start",
            "window_end",
            "coordination_notes",
        ):
            if name in payload.model_fields_set:
                if name in required and getattr(payload, name) is None:
                    raise ApiError(
                        status_code=422,
                        code="fulfilment_field_required",
                        message=f"{name} cannot be null",
                    )
                setattr(value, name, getattr(payload, name))
        if value.window_end <= value.window_start:
            raise ApiError(
                status_code=422,
                code="invalid_fulfilment_window",
                message="Window end must follow its start",
            )

    async def _response(self, value: Fulfilment) -> FulfilmentResponse:
        return FulfilmentResponse(
            id=value.id,
            order_id=value.order_id,
            method=value.method,
            status=value.status,
            location_label=value.location_label,
            location_details=value.location_details,
            latitude=value.latitude,
            longitude=value.longitude,
            window_start=value.window_start,
            window_end=value.window_end,
            coordination_notes=value.coordination_notes,
            version=value.version,
            completed_at=value.completed_at,
            created_at=value.created_at,
            updated_at=value.updated_at,
            history=await self.repository.history(value.id),
        )
