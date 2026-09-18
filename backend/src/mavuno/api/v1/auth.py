from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from mavuno.api.dependencies import CurrentUser, get_auth_service
from mavuno.api.errors import ApiError
from mavuno.auth.rate_limit import AuthRateLimiter, AuthRateLimitExceeded
from mavuno.auth.schemas import (
    LoginRequest,
    LogoutRequest,
    LogoutResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from mavuno.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["authentication"])
AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest, request: Request, auth: AuthServiceDependency
) -> TokenResponse:
    _enforce_rate_limit(request, "register", f"{payload.email or ''}|{payload.phone or ''}")
    return await auth.register(payload)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest, request: Request, auth: AuthServiceDependency
) -> TokenResponse:
    _enforce_rate_limit(request, "login", payload.identifier)
    return await auth.login(payload.identifier, payload.password)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest, request: Request, auth: AuthServiceDependency
) -> TokenResponse:
    _enforce_rate_limit(request, "refresh", payload.refresh_token)
    return await auth.refresh(payload.refresh_token)


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    request: LogoutRequest, current_user: CurrentUser, auth: AuthServiceDependency
) -> LogoutResponse:
    await auth.logout(request.refresh_token, current_user.id)
    return LogoutResponse()


@router.get("/me", response_model=UserResponse)
async def me(current_user: CurrentUser) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        phone_e164=current_user.phone_e164,
        roles=sorted(current_user.roles),
    )


def _enforce_rate_limit(request: Request, scope: str, subject: str) -> None:
    limiter: AuthRateLimiter = request.app.state.auth_rate_limiter
    client_address = request.client.host if request.client is not None else "unknown"
    try:
        limiter.check(scope, client_address, subject)
    except AuthRateLimitExceeded as exc:
        raise ApiError(
            status_code=429,
            code="auth_rate_limit_exceeded",
            message="Too many authentication attempts; try again later",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
