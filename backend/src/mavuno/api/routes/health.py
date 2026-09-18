from typing import Literal

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/health")


class HealthResponse(BaseModel):
    status: Literal["alive", "ready", "not_ready"]


@router.get("/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return HealthResponse(status="alive")


@router.get(
    "/ready",
    response_model=HealthResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse}},
)
async def readiness(request: Request) -> HealthResponse | JSONResponse:
    if not request.app.state.ready:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=HealthResponse(status="not_ready").model_dump(),
        )
    database = getattr(request.app.state, "database", None)
    if database is not None and not await database.is_ready():
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=HealthResponse(status="not_ready").model_dump(),
        )
    return HealthResponse(status="ready")


@router.get("/metrics")
async def metrics(request: Request) -> dict[str, int]:
    """Expose low-cardinality process counters; deployment may scrape or translate these."""
    return dict(request.app.state.metrics.snapshot())
