from uuid import UUID

from fastapi import APIRouter, Request

from mavuno.api.dependencies import CurrentUser, DatabaseSession
from mavuno.commerce.repository import CommerceRepository
from mavuno.fulfilment.repository import FulfilmentRepository
from mavuno.fulfilment.schemas import FulfilmentResponse, FulfilmentTransition, FulfilmentUpdate
from mavuno.fulfilment.service import FulfilmentService

router = APIRouter(tags=["fulfilment"])


def _service(session: DatabaseSession, request: Request) -> FulfilmentService:
    return FulfilmentService(
        FulfilmentRepository(session),
        CommerceRepository(session),
        request.app.state.settings,
        getattr(request.app.state, "catalog_cache", None),
    )


@router.get("/fulfilments/{order_id}", response_model=FulfilmentResponse)
async def get_fulfilment(
    order_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
    request: Request,
    farmer_id: UUID | None = None,
) -> FulfilmentResponse:
    return await _service(session, request).get(current_user, order_id, farmer_id)


@router.get("/fulfilments/{order_id}/parts", response_model=list[FulfilmentResponse])
async def list_fulfilment_parts(
    order_id: UUID, current_user: CurrentUser, session: DatabaseSession, request: Request
) -> list[FulfilmentResponse]:
    return await _service(session, request).parts(current_user, order_id)


@router.patch("/fulfilments/{order_id}", response_model=FulfilmentResponse)
async def update_fulfilment(
    order_id: UUID,
    payload: FulfilmentUpdate,
    current_user: CurrentUser,
    session: DatabaseSession,
    request: Request,
    farmer_id: UUID | None = None,
) -> FulfilmentResponse:
    return await _service(session, request).update(current_user, order_id, payload, farmer_id)


@router.post("/fulfilments/{order_id}/status", response_model=FulfilmentResponse)
async def transition_fulfilment(
    order_id: UUID,
    payload: FulfilmentTransition,
    current_user: CurrentUser,
    session: DatabaseSession,
    request: Request,
    farmer_id: UUID | None = None,
) -> FulfilmentResponse:
    return await _service(session, request).transition(current_user, order_id, payload, farmer_id)
