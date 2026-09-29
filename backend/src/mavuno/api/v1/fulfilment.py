from uuid import UUID

from fastapi import APIRouter

from mavuno.api.dependencies import CurrentUser, DatabaseSession
from mavuno.fulfilment.repository import FulfilmentRepository
from mavuno.fulfilment.schemas import FulfilmentResponse, FulfilmentTransition, FulfilmentUpdate
from mavuno.fulfilment.service import FulfilmentService

router = APIRouter(tags=["fulfilment"])


@router.get("/fulfilments/{order_id}", response_model=FulfilmentResponse)
async def get_fulfilment(
    order_id: UUID, current_user: CurrentUser, session: DatabaseSession
) -> FulfilmentResponse:
    return await FulfilmentService(FulfilmentRepository(session)).get(current_user, order_id)


@router.patch("/fulfilments/{order_id}", response_model=FulfilmentResponse)
async def update_fulfilment(
    order_id: UUID,
    payload: FulfilmentUpdate,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> FulfilmentResponse:
    return await FulfilmentService(FulfilmentRepository(session)).update(
        current_user, order_id, payload
    )


@router.post("/fulfilments/{order_id}/status", response_model=FulfilmentResponse)
async def transition_fulfilment(
    order_id: UUID,
    payload: FulfilmentTransition,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> FulfilmentResponse:
    return await FulfilmentService(FulfilmentRepository(session)).transition(
        current_user, order_id, payload
    )
