from fastapi import APIRouter

from mavuno.api.v1.auth import router as auth_router
from mavuno.api.v1.catalog import router as catalog_router
from mavuno.api.v1.commerce import router as commerce_router
from mavuno.api.v1.fulfilment import router as fulfilment_router
from mavuno.api.v1.profiles import router as profiles_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(catalog_router)
router.include_router(commerce_router)
router.include_router(fulfilment_router)
router.include_router(profiles_router)
