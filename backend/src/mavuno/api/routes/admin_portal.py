from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()
ASSETS = Path(__file__).resolve().parents[2] / "admin"
HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
        "img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    ),
}


@router.get("/admin", include_in_schema=False)
@router.get("/admin/", include_in_schema=False)
async def admin_portal() -> FileResponse:
    return FileResponse(ASSETS / "index.html", headers=HEADERS)


@router.get("/admin/portal.js", include_in_schema=False)
async def admin_script() -> FileResponse:
    return FileResponse(ASSETS / "portal.js", media_type="text/javascript", headers=HEADERS)


@router.get("/admin/portal.css", include_in_schema=False)
async def admin_styles() -> FileResponse:
    return FileResponse(ASSETS / "portal.css", media_type="text/css", headers=HEADERS)
