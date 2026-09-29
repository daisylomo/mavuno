"""Hand-over coordination, one record per farmer in an order.

An order can hold produce from several farmers who harvest, pack and hand over separately.
Each farmer therefore has their own fulfilment record for their own items: a farmer can only
see and advance their part, and the order is completed only when every part is finished.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from mavuno.api.errors import ApiError
from mavuno.auth.context import AuthenticatedUser
from mavuno.commerce import inventory
from mavuno.commerce.refunds import RefundService
from mavuno.commerce.repository import CommerceRepository
from mavuno.core.config import Settings
from mavuno.core.performance import CatalogCache
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
TERMINAL = frozenset({"completed", "cancelled"})
# A farmer may withdraw their part only before anything has been prepared for hand-over.
FARMER_CANCELLABLE = frozenset({"pending", "scheduled"})


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class FulfilmentService:
    def __init__(
        self,
        repository: FulfilmentRepository,
        commerce: CommerceRepository | None = None,
        settings: Settings | None = None,
        catalog_cache: CatalogCache | None = None,
    ) -> None:
        self.repository = repository
        self.commerce = commerce
        self.settings = settings
        self.catalog_cache = catalog_cache

    async def get(
        self, actor: AuthenticatedUser, order_id: UUID, farmer_id: UUID | None = None
    ) -> FulfilmentResponse:
        order = await self.repository.order(order_id)
        farmers = await self._authorize(actor, order, order_id)
        target = self._target_farmer(actor, farmers, farmer_id)
        fulfilment = await self.repository.part(order_id, target)
        if fulfilment is None:
            raise ApiError(
                status_code=404, code="fulfilment_not_found", message="Fulfilment was not found"
            )
        return await self._response(fulfilment)

    async def parts(self, actor: AuthenticatedUser, order_id: UUID) -> list[FulfilmentResponse]:
        order = await self.repository.order(order_id)
        await self._authorize(actor, order, order_id)
        parts = await self.repository.parts(order_id)
        if self._is_farmer_only(actor, order):
            parts = [part for part in parts if part.farmer_id == actor.id]
        return [await self._response(part) for part in parts]

    async def update(
        self,
        actor: AuthenticatedUser,
        order_id: UUID,
        payload: FulfilmentUpdate,
        farmer_id: UUID | None = None,
    ) -> FulfilmentResponse:
        order = await self.repository.order(order_id, lock=True)
        farmers = await self._authorize(actor, order, order_id)
        assert order is not None
        if order.status not in {"paid", "fulfilment"}:
            raise ApiError(
                status_code=409,
                code="order_not_fulfillable",
                message="Order is not ready for fulfilment",
            )
        existing = {part.farmer_id: part for part in await self.repository.parts(order.id, True)}
        if farmer_id is None and not existing and not self._is_farmer_only(actor, order):
            # The buyer's first coordination covers every farmer in the order; each farmer
            # then advances their own part independently.
            targets = sorted(farmers, key=lambda value: value.bytes)
        else:
            targets = [self._target_farmer(actor, farmers, farmer_id)]
        missing = [target for target in targets if target not in existing]
        result: Fulfilment
        if missing:
            self._require_buyer_or_admin(actor, order.buyer_id)
            created = [self._new(order.id, target, payload) for target in missing]
            for part in created:
                self.repository.add(part)
                self.repository.add(
                    FulfilmentStatusHistory(
                        id=uuid4(),
                        fulfilment_id=part.id,
                        actor_user_id=actor.id,
                        previous_status=None,
                        new_status="pending",
                        reason="Coordination created",
                    )
                )
            if order.status == "paid":
                self._order_status(order, "fulfilment", actor.id, "Fulfilment coordination created")
            result = created[0]
        else:
            result = existing[targets[0]]
            if payload.expected_version is None:
                raise ApiError(
                    status_code=422, code="version_required", message="expected_version is required"
                )
            if result.version != payload.expected_version:
                raise ApiError(
                    status_code=409, code="fulfilment_conflict", message="Fulfilment has changed"
                )
            if result.status not in {"pending", "scheduled"}:
                raise ApiError(
                    status_code=409,
                    code="coordination_locked",
                    message="Coordination details are locked",
                )
            self._apply(result, payload)
            result.version += 1
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ApiError(
                status_code=409, code="fulfilment_conflict", message="Fulfilment has changed"
            ) from exc
        await self.repository.refresh(result)
        return await self._response(result)

    async def transition(
        self,
        actor: AuthenticatedUser,
        order_id: UUID,
        payload: FulfilmentTransition,
        farmer_id: UUID | None = None,
    ) -> FulfilmentResponse:
        order = await self.repository.order(order_id, lock=True)
        farmers = await self._authorize(actor, order, order_id)
        assert order is not None
        if order.status != "fulfilment":
            raise ApiError(
                status_code=409,
                code="order_fulfilment_inconsistent",
                message="Order is not in fulfilment",
            )
        target = self._target_farmer(actor, farmers, farmer_id)
        fulfilment = await self.repository.part(order.id, target, lock=True)
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
        self._authorize_transition(actor, order.buyer_id, fulfilment, payload.status)
        previous = fulfilment.status
        fulfilment.status = payload.status
        fulfilment.version += 1
        if payload.status == "completed":
            fulfilment.completed_at = _now()
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
        changed: set[UUID] = set()
        if payload.status == "cancelled":
            changed = await self._settle_cancelled_part(order, fulfilment, actor, payload.reason)
        await self._roll_up(order, farmers, actor)
        await self.repository.commit()
        await self.repository.refresh(fulfilment)
        await self._invalidate(changed)
        return await self._response(fulfilment)

    async def _settle_cancelled_part(
        self,
        order: Order,
        part: Fulfilment,
        actor: AuthenticatedUser,
        reason: str | None,
    ) -> set[UUID]:
        """Return a cancelled farmer's stock and the buyer's money for those items."""
        if self.commerce is None or self.settings is None:
            return set()
        items = [
            item
            for item in await self.commerce.order_items(order.id)
            if item.farmer_id == part.farmer_id
        ]
        changed = await inventory.release(
            self.commerce,
            items,
            order_id=order.id,
            actor_user_id=actor.id,
            reason=(reason or "Fulfilment cancelled")[:255],
        )
        payment = await self.commerce.succeeded_payment(order.id)
        if payment is not None:
            await RefundService(self.commerce, self.settings).request(
                payment,
                amount=sum((item.line_total for item in items), Decimal("0")),
                reason="fulfilment_cancelled",
                dedupe_key=f"refund:{order.id}:farmer:{part.farmer_id}",
                farmer_id=part.farmer_id,
            )
        return changed

    async def _roll_up(self, order: Order, farmers: set[UUID], actor: AuthenticatedUser) -> None:
        """The order finishes only once every farmer's part has finished."""
        parts = await self.repository.parts(order.id)
        by_farmer = {part.farmer_id: part.status for part in parts}
        if set(by_farmer) != farmers or not all(
            status in TERMINAL for status in by_farmer.values()
        ):
            return
        if any(status == "completed" for status in by_farmer.values()):
            self._order_status(order, "completed", actor.id, "Every farmer's hand-over finished")
        else:
            self._order_status(
                order, "cancelled", actor.id, "All parts cancelled; buyer refund recorded"
            )

    def _order_status(self, order: Order, status: str, actor_id: UUID, reason: str) -> None:
        previous = order.status
        order.status = status
        order.version += 1
        self.repository.add(
            OrderStatusHistory(
                id=uuid4(),
                order_id=order.id,
                actor_user_id=actor_id,
                previous_status=previous,
                new_status=status,
                reason=reason,
            )
        )

    async def _authorize(
        self, actor: AuthenticatedUser, order: Order | None, order_id: UUID
    ) -> set[UUID]:
        if order is None:
            raise ApiError(status_code=404, code="order_not_found", message="Order was not found")
        farmers = await self.repository.farmer_ids(order_id)
        if actor.has_role("administrator") or actor.id == order.buyer_id:
            return farmers
        if actor.has_role("farmer") and actor.id in farmers:
            return farmers
        raise ApiError(status_code=404, code="order_not_found", message="Order was not found")

    @staticmethod
    def _is_farmer_only(actor: AuthenticatedUser, order: Order | None) -> bool:
        return (
            order is not None and actor.id != order.buyer_id and not actor.has_role("administrator")
        )

    def _target_farmer(
        self, actor: AuthenticatedUser, farmers: set[UUID], farmer_id: UUID | None
    ) -> UUID:
        """Farmers always act on their own part; buyers pick a farmer when there are several."""
        if actor.id in farmers and not actor.has_role("administrator"):
            if farmer_id is not None and farmer_id != actor.id:
                raise ApiError(
                    status_code=403,
                    code="fulfilment_forbidden",
                    message="Farmers can only manage their own items",
                )
            return actor.id
        if farmer_id is not None:
            if farmer_id not in farmers:
                raise ApiError(
                    status_code=404,
                    code="fulfilment_not_found",
                    message="That farmer has no items in this order",
                )
            return farmer_id
        if len(farmers) == 1:
            return next(iter(farmers))
        raise ApiError(
            status_code=422,
            code="farmer_id_required",
            message="This order has several farmers; choose whose hand-over to manage",
            details={"farmer_ids": sorted(str(value) for value in farmers)},
        )

    @staticmethod
    def _require_buyer_or_admin(actor: AuthenticatedUser, buyer_id: UUID) -> None:
        if actor.id != buyer_id and not actor.has_role("administrator"):
            raise ApiError(
                status_code=403, code="fulfilment_forbidden", message="Action is not permitted"
            )

    @staticmethod
    def _authorize_transition(
        actor: AuthenticatedUser, buyer_id: UUID, part: Fulfilment, target: str
    ) -> None:
        if actor.has_role("administrator"):
            return
        own_part = actor.id == part.farmer_id and actor.has_role("farmer")
        if own_part and target in {"scheduled", "ready_for_handover"}:
            return
        if own_part and target == "in_transit" and part.method == "delivery":
            return
        if own_part and target == "cancelled" and part.status in FARMER_CANCELLABLE:
            return
        if actor.id == buyer_id and target in {"completed", "cancelled"}:
            return
        raise ApiError(
            status_code=403,
            code="fulfilment_transition_forbidden",
            message="Transition is not permitted",
        )

    @staticmethod
    def _new(order_id: UUID, farmer_id: UUID, payload: FulfilmentUpdate) -> Fulfilment:
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
            farmer_id=farmer_id,
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

    async def _invalidate(self, listing_ids: set[UUID]) -> None:
        if self.catalog_cache is None:
            return
        for listing_id in listing_ids:
            await self.catalog_cache.invalidate_listing(str(listing_id))

    async def _response(self, value: Fulfilment) -> FulfilmentResponse:
        return FulfilmentResponse(
            id=value.id,
            order_id=value.order_id,
            farmer_id=value.farmer_id,
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
