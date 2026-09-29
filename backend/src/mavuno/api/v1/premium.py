from __future__ import annotations

import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, status

from mavuno.api.dependencies import CurrentUser, DatabaseSession, require_roles
from mavuno.auth.context import AuthenticatedUser
from mavuno.premium.repository import PremiumRepository
from mavuno.premium.schemas import (
    FarmerInsightsResponse,
    PlanCreate,
    PlanResponse,
    PrebookingCreate,
    PrebookingResponse,
    PrebookingTransition,
    SubscriptionCreate,
    SubscriptionResponse,
)
from mavuno.premium.service import InsightsService, PrebookingService, SubscriptionService

router = APIRouter(tags=["premium"])
AdminUser = Annotated[AuthenticatedUser, Depends(require_roles("administrator"))]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)]


@router.get("/premium/plans", response_model=list[PlanResponse])
async def list_plans(session: DatabaseSession, request: Request) -> object:
    return await SubscriptionService(PremiumRepository(session), request.app.state.settings).plans()


@router.post("/premium/plans", response_model=PlanResponse, status_code=201)
async def create_plan(
    payload: PlanCreate, _: AdminUser, session: DatabaseSession, request: Request
) -> object:
    return await SubscriptionService(
        PremiumRepository(session), request.app.state.settings
    ).create_plan(payload)


@router.get("/premium/subscriptions", response_model=list[SubscriptionResponse])
async def list_subscriptions(
    current_user: CurrentUser, session: DatabaseSession, request: Request
) -> object:
    return await SubscriptionService(
        PremiumRepository(session), request.app.state.settings
    ).subscriptions(current_user)


@router.post(
    "/premium/subscriptions",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def initiate_subscription(
    payload: SubscriptionCreate,
    idempotency_key: IdempotencyKey,
    current_user: CurrentUser,
    session: DatabaseSession,
    request: Request,
) -> object:
    return await SubscriptionService(
        PremiumRepository(session), request.app.state.settings
    ).initiate(current_user, payload.plan_id, idempotency_key)


@router.post("/webhooks/premium/{callback_token}", status_code=202)
async def premium_callback(
    callback_token: str,
    request: Request,
    session: DatabaseSession,
    signature: Annotated[str, Header(alias="X-Premium-Signature")],
) -> dict[str, bool]:
    raw = await request.body()
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        payload = {}
    await SubscriptionService(PremiumRepository(session), request.app.state.settings).callback(
        callback_token, raw, payload, signature
    )
    return {"accepted": True}


@router.get("/prebookings", response_model=list[PrebookingResponse])
async def list_prebookings(current_user: CurrentUser, session: DatabaseSession) -> object:
    return await PrebookingService(PremiumRepository(session)).list(current_user)


@router.post("/prebookings", response_model=PrebookingResponse, status_code=201)
async def create_prebooking(
    payload: PrebookingCreate, current_user: CurrentUser, session: DatabaseSession
) -> object:
    return await PrebookingService(PremiumRepository(session)).create(current_user, payload)


@router.post("/prebookings/{prebooking_id}/status", response_model=PrebookingResponse)
async def transition_prebooking(
    prebooking_id: UUID,
    payload: PrebookingTransition,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> object:
    return await PrebookingService(PremiumRepository(session)).transition(
        current_user, prebooking_id, payload
    )


@router.get("/premium/insights/farmer", response_model=FarmerInsightsResponse)
async def farmer_insights(current_user: CurrentUser, session: DatabaseSession) -> object:
    return await InsightsService(PremiumRepository(session)).farmer(current_user)
