from __future__ import annotations

import hmac
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from mavuno.api.errors import ApiError
from mavuno.auth.context import AuthenticatedUser
from mavuno.core.config import Settings
from mavuno.db.models import OutboxJob, Plan, Prebooking, Subscription, SubscriptionEvent
from mavuno.premium.provider import (
    HttpPremiumProvider,
    PremiumProvider,
    PremiumProviderError,
    SubscriptionInitiation,
    SubscriptionStatus,
)
from mavuno.premium.repository import PremiumRepository
from mavuno.premium.schemas import (
    FarmerInsightsResponse,
    PlanCreate,
    PrebookingCreate,
    PrebookingTransition,
)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class SubscriptionService:
    def __init__(
        self,
        repository: PremiumRepository,
        settings: Settings,
        provider: PremiumProvider | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.provider = provider

    async def plans(self) -> list[Plan]:
        return await self.repository.plans()

    async def create_plan(self, payload: PlanCreate) -> Plan:
        plan = Plan(**payload.model_dump())
        plan.features = list(dict.fromkeys(payload.features))
        self.repository.add(plan)
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ApiError(
                status_code=409, code="plan_exists", message="Plan already exists"
            ) from exc
        await self.repository.refresh(plan)
        return plan

    async def subscriptions(self, user: AuthenticatedUser) -> list[Subscription]:
        return await self.repository.subscriptions(user.id)

    async def initiate(
        self, user: AuthenticatedUser, plan_id: UUID, idempotency_key: str
    ) -> Subscription:
        if not self.settings.premium_enabled:
            raise ApiError(
                status_code=503,
                code="premium_provider_unavailable",
                message="Premium subscriptions are temporarily unavailable",
            )
        existing = await self.repository.subscription_by_idempotency(user.id, idempotency_key)
        if existing is not None and existing.provider_subscription_ref is not None:
            return existing
        plan = await self.repository.plan(plan_id)
        if plan is None or not plan.active:
            raise ApiError(status_code=404, code="plan_not_found", message="Plan was not found")
        if plan.audience not in user.roles:
            raise ApiError(
                status_code=403, code="plan_not_available", message="Plan is not available"
            )
        subscription = existing or Subscription(
            id=uuid4(),
            user_id=user.id,
            plan_id=plan.id,
            status="pending",
            provider="premium_http",
            account_reference=f"MVS{uuid4().hex[:16].upper()}",
            idempotency_key=idempotency_key,
        )
        if existing is None:
            self.repository.add(subscription)
            await self.repository.commit()
            await self.repository.refresh(subscription)
        provider: PremiumProvider | None = None
        try:
            provider = self._provider()
            subscription.provider_subscription_ref = await provider.initiate(
                SubscriptionInitiation(
                    account_reference=subscription.account_reference,
                    user_reference=str(user.id),
                    plan_code=plan.code,
                    amount=plan.price_amount,
                    currency=plan.currency,
                    interval=plan.billing_interval,
                )
            )
        except PremiumProviderError as exc:
            raise ApiError(
                status_code=503,
                code="premium_provider_unavailable",
                message="Premium provider is unavailable",
            ) from exc
        finally:
            await self._close(provider)
        self.repository.add(
            OutboxJob(
                id=uuid4(),
                job_type="subscription_status_query",
                dedupe_key=f"subscription-query:{subscription.id}:initial",
                payload={"subscription_id": str(subscription.id)},
                status="pending",
                attempts=0,
                max_attempts=self.settings.premium_reconcile_attempts,
                available_at=_now() + timedelta(seconds=30),
            )
        )
        await self.repository.commit()
        await self.repository.refresh(subscription)
        return subscription

    async def callback(
        self,
        token: str,
        raw_body: bytes,
        payload: dict[str, object],
        signature: str,
    ) -> None:
        expected = self.settings.premium_callback_token
        if expected is None or not hmac.compare_digest(token, expected.get_secret_value()):
            raise ApiError(status_code=404, code="webhook_not_found", message="Webhook not found")
        provider: PremiumProvider | None = None
        try:
            provider = self._provider()
            event = provider.parse_callback(raw_body, payload, signature)
        except PremiumProviderError as exc:
            raise ApiError(
                status_code=422,
                code="invalid_premium_callback",
                message="Premium callback is invalid",
            ) from exc
        finally:
            await self._close(provider)
        assert provider is not None
        subscription = await self.repository.subscription_by_reference(event.account_reference)
        if subscription is None:
            raise ApiError(
                status_code=202,
                code="premium_callback_unmatched",
                message="Callback accepted for reconciliation",
            )
        if (
            subscription.provider_subscription_ref is not None
            and subscription.provider_subscription_ref != event.provider_subscription_ref
        ):
            raise ApiError(
                status_code=409,
                code="premium_reference_mismatch",
                message="Provider reference does not match",
            )
        subscription.provider_subscription_ref = event.provider_subscription_ref
        self.repository.add(
            SubscriptionEvent(
                id=uuid4(),
                subscription_id=subscription.id,
                provider=provider.name,
                provider_event_ref=event.provider_event_ref,
                event_type=event.event_type,
                payload_redacted=event.redacted_payload,
            )
        )
        self.repository.add(
            OutboxJob(
                id=uuid4(),
                job_type="subscription_status_query",
                dedupe_key=f"subscription-event:{event.provider_event_ref}",
                payload={"subscription_id": str(subscription.id)},
                status="pending",
                attempts=0,
                max_attempts=self.settings.premium_reconcile_attempts,
                available_at=_now(),
            )
        )
        try:
            await self.repository.commit()
        except IntegrityError:
            await self.repository.rollback()

    async def reconcile(self, subscription_id: UUID) -> None:
        subscription = await self.repository.subscription(subscription_id)
        if subscription is None or subscription.provider_subscription_ref is None:
            return
        plan = await self.repository.plan(subscription.plan_id)
        if plan is None:
            raise RuntimeError("Subscription plan is missing")
        provider = self._provider()
        try:
            status = await provider.query_status(subscription.provider_subscription_ref)
        finally:
            await self._close(provider)
        subscription = await self.repository.subscription(subscription_id, lock=True)
        if subscription is None:
            return
        discrepancy = self._discrepancy(subscription, plan, status)
        if discrepancy is not None:
            subscription.status = "past_due"
            await self.repository.commit()
            return
        subscription.status = status.outcome
        subscription.current_period_start = status.period_start
        subscription.current_period_end = status.period_end
        if status.outcome == "active":
            subscription.verified_at = _now()
        elif status.outcome == "cancelled":
            subscription.cancelled_at = _now()
        await self.repository.commit()

    @staticmethod
    def _discrepancy(
        subscription: Subscription, plan: Plan, status: SubscriptionStatus
    ) -> str | None:
        if status.account_reference != subscription.account_reference:
            return "account_reference_mismatch"
        if status.plan_code != plan.code:
            return "plan_mismatch"
        if status.amount != plan.price_amount or status.currency != plan.currency:
            return "amount_or_currency_mismatch"
        if status.outcome == "active" and (
            status.period_start is None
            or status.period_end is None
            or status.period_end <= status.period_start
        ):
            return "invalid_period"
        return None

    def _provider(self) -> PremiumProvider:
        return self.provider or HttpPremiumProvider(self.settings)

    @staticmethod
    async def _close(provider: PremiumProvider | None) -> None:
        if isinstance(provider, HttpPremiumProvider):
            await provider.aclose()


class PrebookingService:
    def __init__(self, repository: PremiumRepository) -> None:
        self.repository = repository

    async def create(self, user: AuthenticatedUser, payload: PrebookingCreate) -> Prebooking:
        if "buyer" not in user.roles:
            raise ApiError(
                status_code=403, code="buyer_role_required", message="Buyer role required"
            )
        await self._entitled(user.id, "prebooking")
        if not await self.repository.user_has_role(payload.farmer_id, "farmer"):
            raise ApiError(status_code=404, code="farmer_not_found", message="Farmer not found")
        if await self.repository.product(payload.product_id) is None:
            raise ApiError(status_code=404, code="product_not_found", message="Product not found")
        if payload.listing_id is not None:
            listing = await self.repository.listing(payload.listing_id)
            if (
                listing is None
                or listing.farmer_id != payload.farmer_id
                or listing.product_id != payload.product_id
            ):
                raise ApiError(
                    status_code=404, code="listing_not_found", message="Listing not found"
                )
        value = Prebooking(
            id=uuid4(),
            buyer_id=user.id,
            status="requested",
            currency="KES",
            version=1,
            **payload.model_dump(),
        )
        self.repository.add(value)
        await self.repository.commit()
        await self.repository.refresh(value)
        return value

    async def list(self, user: AuthenticatedUser) -> list[Prebooking]:
        return await self.repository.prebookings(user.id)

    async def transition(
        self, user: AuthenticatedUser, prebooking_id: UUID, payload: PrebookingTransition
    ) -> Prebooking:
        value = await self.repository.prebooking(prebooking_id, lock=True)
        if value is None or (
            user.id not in {value.buyer_id, value.farmer_id} and "administrator" not in user.roles
        ):
            raise ApiError(
                status_code=404, code="prebooking_not_found", message="Prebooking not found"
            )
        if value.version != payload.expected_version:
            raise ApiError(
                status_code=409, code="prebooking_conflict", message="Prebooking changed"
            )
        allowed = {
            "requested": {"accepted", "rejected", "cancelled"},
            "accepted": {"fulfilled", "cancelled"},
            "rejected": set(),
            "cancelled": set(),
            "fulfilled": set(),
        }
        if payload.status not in allowed[value.status]:
            raise ApiError(
                status_code=409,
                code="invalid_prebooking_transition",
                message="Transition not allowed",
            )
        if "administrator" not in user.roles:
            if (
                payload.status in {"accepted", "rejected", "fulfilled"}
                and user.id != value.farmer_id
            ):
                raise ApiError(
                    status_code=403, code="prebooking_forbidden", message="Action not permitted"
                )
            if payload.status == "cancelled" and user.id != value.buyer_id:
                raise ApiError(
                    status_code=403, code="prebooking_forbidden", message="Action not permitted"
                )
        value.status = payload.status
        value.version += 1
        await self.repository.commit()
        await self.repository.refresh(value)
        return value

    async def _entitled(self, user_id: UUID, feature: str) -> None:
        if not await self.repository.entitlement(user_id, feature, _now()):
            raise ApiError(
                status_code=403,
                code="premium_entitlement_required",
                message="An active verified premium entitlement is required",
            )


class InsightsService:
    def __init__(self, repository: PremiumRepository) -> None:
        self.repository = repository

    async def farmer(self, user: AuthenticatedUser) -> FarmerInsightsResponse:
        if "farmer" not in user.roles:
            raise ApiError(
                status_code=403, code="farmer_role_required", message="Farmer role required"
            )
        if not await self.repository.entitlement(user.id, "insights", _now()):
            raise ApiError(
                status_code=403,
                code="premium_entitlement_required",
                message="An active verified premium entitlement is required",
            )
        active, units, lines, gross = await self.repository.farmer_insights(user.id)
        return FarmerInsightsResponse(
            active_listings=active,
            units_available=units,
            completed_order_lines=lines,
            gross_sales=gross,
        )
