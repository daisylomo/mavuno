from fastapi import APIRouter

from mavuno.api.routes.health import router as health_router
from mavuno.api.v1.router import router as v1_router
from mavuno.core.config import API_V1_PREFIX

router = APIRouter()
router.include_router(health_router, tags=["health"])
router.include_router(v1_router, prefix=API_V1_PREFIX)
