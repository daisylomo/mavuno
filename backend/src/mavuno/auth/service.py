from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mavuno.api.errors import ApiError
from mavuno.auth.normalization import normalize_login_identifier, normalize_phone
from mavuno.auth.schemas import RegisterRequest, TokenResponse, UserResponse
from mavuno.auth.security import PasswordManager, TokenManager
from mavuno.db.models import Profile, RefreshToken, User, UserRole

_INVALID_CREDENTIALS = "The identifier or password is incorrect"


def _utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        password_manager: PasswordManager,
        token_manager: TokenManager,
    ) -> None:
        self._session = session
        self._passwords = password_manager
        self._tokens = token_manager

    async def register(self, request: RegisterRequest) -> TokenResponse:
        email = str(request.email).lower() if request.email is not None else None
        try:
            phone = normalize_phone(request.phone) if request.phone is not None else None
        except ValueError as exc:
            raise ApiError(
                status_code=422, code="invalid_phone", message="The phone number is invalid"
            ) from exc

        conditions = []
        if email is not None:
            conditions.append(User.email == email)
        if phone is not None:
            conditions.append(User.phone_e164 == phone)
        existing = await self._session.scalar(select(User.id).where(or_(*conditions)))
        if existing is not None:
            raise ApiError(
                status_code=409,
                code="identifier_unavailable",
                message="An account with that email address or phone number already exists",
            )

        user = User(
            email=email,
            phone_e164=phone,
            password_hash=self._passwords.hash(request.password),
            status="active",
            token_version=0,
        )
        self._session.add(user)
        try:
            await self._session.flush()
            self._session.add(UserRole(user_id=user.id, role_name=request.role))
            self._session.add(Profile(user_id=user.id, display_name="Mavuno User"))
            await self._session.flush()
            response = await self._issue_token_pair(user, frozenset({request.role}))
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ApiError(
                status_code=409,
                code="identifier_unavailable",
                message="An account with that email address or phone number already exists",
            ) from exc
        return response

    async def login(self, identifier: str, password: str) -> TokenResponse:
        try:
            field, normalized = normalize_login_identifier(identifier)
        except ValueError as exc:
            self._passwords.verify_unknown(password)
            raise self._invalid_credentials() from exc

        criterion = User.email == normalized if field == "email" else User.phone_e164 == normalized
        user = await self._session.scalar(select(User).where(criterion))
        if user is None:
            self._passwords.verify_unknown(password)
            raise self._invalid_credentials()
        if not self._passwords.verify(user.password_hash, password):
            raise self._invalid_credentials()
        if user.status != "active":
            raise ApiError(
                status_code=403,
                code="account_unavailable",
                message="This account is not available",
            )

        roles = await self._roles_for(user.id)
        user.last_login_at = _utc_naive()
        response = await self._issue_token_pair(user, roles)
        await self._session.commit()
        return response

    async def refresh(self, raw_token: str) -> TokenResponse:
        token_hash = self._tokens.hash_refresh_token(raw_token)
        stored = await self._session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
        )
        if stored is None:
            raise self._invalid_refresh()

        now = _utc_naive()
        if stored.rotated_at is not None or stored.revoked_at is not None:
            await self._revoke_family(stored.family_id, now)
            await self._session.execute(
                update(User)
                .where(User.id == stored.user_id)
                .values(token_version=User.token_version + 1)
            )
            await self._session.commit()
            raise ApiError(
                status_code=401,
                code="refresh_token_reuse",
                message="Refresh token reuse was detected; sign in again",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if stored.expires_at <= now:
            stored.revoked_at = now
            await self._session.commit()
            raise self._invalid_refresh()

        user = await self._session.get(User, stored.user_id)
        if user is None or user.status != "active":
            stored.revoked_at = now
            await self._session.commit()
            raise self._invalid_refresh()

        roles = await self._roles_for(user.id)
        raw_replacement = self._tokens.create_refresh_token()
        replacement = RefreshToken(
            user_id=user.id,
            device_installation_id=stored.device_installation_id,
            family_id=stored.family_id,
            token_hash=self._tokens.hash_refresh_token(raw_replacement),
            expires_at=now + self._tokens.refresh_ttl,
        )
        self._session.add(replacement)
        await self._session.flush()
        stored.rotated_at = now
        stored.replaced_by_id = replacement.id
        response = self._token_response(user, roles, raw_replacement)
        await self._session.commit()
        return response

    async def logout(self, raw_token: str, current_user_id: UUID) -> None:
        stored = await self._session.scalar(
            select(RefreshToken)
            .where(RefreshToken.token_hash == self._tokens.hash_refresh_token(raw_token))
            .with_for_update()
        )
        if stored is None or stored.user_id != current_user_id:
            raise self._invalid_refresh()
        await self._revoke_family(stored.family_id, _utc_naive())
        await self._session.commit()

    async def _issue_token_pair(
        self, user: User, roles: frozenset[str], *, family_id: UUID | None = None
    ) -> TokenResponse:
        raw_refresh = self._tokens.create_refresh_token()
        self._session.add(
            RefreshToken(
                user_id=user.id,
                family_id=family_id or uuid4(),
                token_hash=self._tokens.hash_refresh_token(raw_refresh),
                expires_at=_utc_naive() + self._tokens.refresh_ttl,
            )
        )
        return self._token_response(user, roles, raw_refresh)

    def _token_response(self, user: User, roles: frozenset[str], raw_refresh: str) -> TokenResponse:
        return TokenResponse(
            access_token=self._tokens.create_access_token(user.id, user.token_version),
            refresh_token=raw_refresh,
            expires_in=int(self._tokens.access_ttl.total_seconds()),
            user=UserResponse(
                id=user.id,
                email=user.email,
                phone_e164=user.phone_e164,
                roles=sorted(roles),
            ),
        )

    async def _roles_for(self, user_id: UUID) -> frozenset[str]:
        result = await self._session.scalars(
            select(UserRole.role_name).where(UserRole.user_id == user_id)
        )
        return frozenset(result.all())

    async def _revoke_family(self, family_id: UUID, now: datetime) -> None:
        await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    @staticmethod
    def _invalid_credentials() -> ApiError:
        return ApiError(
            status_code=401,
            code="invalid_credentials",
            message=_INVALID_CREDENTIALS,
            headers={"WWW-Authenticate": "Bearer"},
        )

    @staticmethod
    def _invalid_refresh() -> ApiError:
        return ApiError(
            status_code=401,
            code="invalid_refresh_token",
            message="The refresh token is invalid or expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
