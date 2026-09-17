from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from mavuno.db.models import User


async def get_database_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Provide one transaction-scoped session for an API request."""
    database = getattr(request.app.state, "database", None)
    if database is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable",
        )
    async with database.session() as session:
        yield session


async def get_current_user() -> User:
    """Authentication seam implemented by Feature 03.

    Deliberately fail closed until the authentication feature supplies token validation.
    """
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication is required",
        headers={"WWW-Authenticate": "Bearer"},
    )


DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]
