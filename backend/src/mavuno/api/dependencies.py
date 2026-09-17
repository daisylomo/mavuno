from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mavuno.api.errors import ApiError
from mavuno.auth.context import AuthenticatedUser
from mavuno.auth.security import InvalidAccessTokenError, PasswordManager, TokenManager
from mavuno.auth.service import AuthService
from mavuno.db import Database
from mavuno.db.models import User, UserRole

bearer_scheme = HTTPBearer(auto_error=False)


def get_database(request: Request) -> Database:
    database: Database | None = getattr(request.app.state, "database", None)
    if database is None:
        raise ApiError(
            status_code=503,
            code="database_unavailable",
            message="The service is temporarily unavailable",
        )
    return database


async def get_db_session(
    database: Annotated[Database, Depends(get_database)],
) -> AsyncIterator[AsyncSession]:
    async with database.session() as session:
        yield session


def get_token_manager(request: Request) -> TokenManager:
    return TokenManager(request.app.state.settings)


@lru_cache
def get_password_manager() -> PasswordManager:
    return PasswordManager()


def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    password_manager: Annotated[PasswordManager, Depends(get_password_manager)],
    token_manager: Annotated[TokenManager, Depends(get_token_manager)],
) -> AuthService:
    return AuthService(session, password_manager, token_manager)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    token_manager: Annotated[TokenManager, Depends(get_token_manager)],
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    try:
        claims = token_manager.decode_access_token(credentials.credentials)
    except InvalidAccessTokenError as exc:
        raise _unauthorized() from exc

    database = get_database(request)
    async with database.session() as session:
        user = await session.get(User, claims.user_id)
        if user is None or user.status != "active" or user.token_version != claims.token_version:
            raise _unauthorized()
        role_result = await session.scalars(
            select(UserRole.role_name).where(UserRole.user_id == user.id)
        )
    return AuthenticatedUser(
        id=user.id,
        email=user.email,
        phone_e164=user.phone_e164,
        roles=frozenset(role_result.all()),
        token_version=user.token_version,
    )


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


def require_roles(
    *allowed_roles: str,
) -> Callable[[AuthenticatedUser], Awaitable[AuthenticatedUser]]:
    async def authorize(
        current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    ) -> AuthenticatedUser:
        if not current_user.has_role(*allowed_roles):
            raise ApiError(
                status_code=403,
                code="insufficient_permissions",
                message="You do not have permission to perform this action",
            )
        return current_user

    return authorize


def _unauthorized() -> ApiError:
    return ApiError(
        status_code=401,
        code="invalid_access_token",
        message="Authentication is required",
        headers={"WWW-Authenticate": "Bearer"},
    )
