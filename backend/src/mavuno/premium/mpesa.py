from __future__ import annotations

import hmac
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from mavuno.api.errors import ApiError
from mavuno.auth.context import AuthenticatedUser
from mavuno.auth.normalization import normalize_phone
from mavuno.core.config import Settings
from mavuno.db.models import OutboxJob, Plan, Subscription, SubscriptionEvent
from mavuno.payments.daraja import DarajaProvider
from mavuno.payments.provider import (
    InitiationRequest,
    PaymentProvider,
    PaymentProviderError,
    ProviderStatus,
)
from mavuno.premium.repository import PremiumRepository
from mavuno.premium.revenuecat import STORE_PLAN_CODES
from mavuno.premium.service import _now

MPESA_PROVIDER = "mpesa"
STATUS_QUERY_JOB = "premium_mpesa_status_query"
CALLBACK_PATH = "/api/v1/webhooks/premium/mpesa"
PERIODS = {"month": timedelta(days=30), "year": timedelta(days=365)}
# Daraja outcomes that end a prompt without payment, as subscription statuses.
UNPAID_STATUSES = {
    "failed": "failed",
    "cancelled": "cancelled",
    "expired": "expired",
    "reversed": "failed",
}


class MpesaPremiumService:
    """Premium bought with an M-PESA STK push; each verified payment is one prepaid period.

    Like order payments, the STK callback is only a hint: Premium unlocks after Mavuno's own
    status query to Safaricom confirms the payment, the amount, payer and paybill.
    """

    def __init__(
        self,
        repository: PremiumRepository,
        settings: Settings,
        provider: PaymentProvider | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.provider = provider

    async def pay(
        self, user: AuthenticatedUser, plan_id: UUID, phone: str, idempotency_key: str
    ) -> Subscription:
        if not self.settings.payments_enabled:
            raise ApiError(
                status_code=503,
                code="mpesa_unavailable",
                message="M-PESA payments are temporarily unavailable",
            )
        existing = await self.repository.subscription_by_idempotency(user.id, idempotency_key)
        if existing is not None and existing.provider_subscription_ref is not None:
            return existing
        plan = await self.repository.plan(plan_id)
        if plan is None or not plan.active or plan.code in STORE_PLAN_CODES.values():
            raise ApiError(status_code=404, code="plan_not_found", message="Plan was not found")
        if plan.audience not in user.roles:
            raise ApiError(
                status_code=403, code="plan_not_available", message="Plan is not available"
            )
        if (
            plan.currency != "KES"
            or plan.price_amount <= 0
            or plan.price_amount != plan.price_amount.to_integral_value()
        ):
            raise ApiError(
                status_code=409,
                code="plan_not_payable",
                message="This plan cannot be paid with M-PESA",
            )
        try:
            payer = normalize_phone(phone)
        except ValueError as exc:
            raise ApiError(
                status_code=422, code="invalid_phone", message="Phone number is invalid"
            ) from exc
        since = _now() - timedelta(seconds=self.settings.payment_inflight_grace_seconds)
        if existing is None and await self.repository.open_prompt(user.id, MPESA_PROVIDER, since):
            raise ApiError(
                status_code=409,
                code="payment_in_progress",
                message="An M-PESA prompt is still open. Wait for it to finish or expire.",
            )
        subscription = existing or Subscription(
            id=uuid4(),
            user_id=user.id,
            plan_id=plan.id,
            status="pending",
            provider=MPESA_PROVIDER,
            # Daraja shows at most 12 characters of the account reference.
            account_reference=f"MVP{uuid4().hex[:9].upper()}",
            idempotency_key=idempotency_key,
            payer_phone_e164=payer,
        )
        if existing is None:
            self.repository.add(subscription)
            await self.repository.commit()
            await self.repository.refresh(subscription)
        subscription.status = "pending"
        provider: PaymentProvider | None = None
        try:
            provider = self._provider()
            result = await provider.initiate(
                InitiationRequest(
                    amount=plan.price_amount,
                    currency=plan.currency,
                    phone_e164=payer,
                    account_reference=subscription.account_reference,
                    description="Mavuno Premium",
                    callback_path=CALLBACK_PATH,
                )
            )
        except PaymentProviderError as exc:
            subscription.status = "failed"
            subscription.failure_reason = "M-PESA could not be reached"
            await self.repository.commit()
            raise ApiError(
                status_code=503,
                code="payment_provider_unavailable",
                message="M-PESA could not be reached. Try again shortly.",
            ) from exc
        finally:
            await self._close(provider)
        subscription.provider_subscription_ref = result.provider_request_ref
        subscription.failure_reason = None
        # Callbacks can be lost and a sleeping host may miss them, so the prompt is also
        # checked on a schedule while it is open.
        for offset in (30, 75, 150):
            self.repository.add(self._status_job(subscription.id, f"{offset}", offset))
        await self.repository.commit()
        await self.repository.refresh(subscription)
        return subscription

    async def refresh(self, user: AuthenticatedUser, subscription_id: UUID) -> Subscription:
        """Member-triggered status check, so Premium never waits on the worker being awake."""
        subscription = await self.repository.subscription(subscription_id)
        if (
            subscription is None
            or subscription.user_id != user.id
            or subscription.provider != MPESA_PROVIDER
        ):
            raise ApiError(
                status_code=404, code="payment_not_found", message="Payment was not found"
            )
        if (
            self.settings.payments_enabled
            and subscription.status == "pending"
            and subscription.provider_subscription_ref is not None
        ):
            try:
                await self.reconcile(subscription.id)
            except PaymentProviderError as exc:
                await self.repository.rollback()
                raise ApiError(
                    status_code=503,
                    code="payment_provider_unavailable",
                    message="M-PESA could not be reached. Try again shortly.",
                ) from exc
        refreshed = await self.repository.subscription(subscription_id)
        assert refreshed is not None
        await self.repository.refresh(refreshed)
        return refreshed

    async def callback(self, token: str, payload: dict[str, object]) -> None:
        expected = self.settings.daraja_callback_token
        if expected is None or not hmac.compare_digest(token, expected.get_secret_value()):
            raise ApiError(status_code=404, code="webhook_not_found", message="Webhook not found")
        provider: PaymentProvider | None = None
        try:
            provider = self._provider()
            event = provider.parse_callback(payload)
        except PaymentProviderError as exc:
            raise ApiError(
                status_code=422, code="malformed_payment_callback", message="Callback is malformed"
            ) from exc
        finally:
            await self._close(provider)
        subscription = await self.repository.subscription_by_provider_ref(
            MPESA_PROVIDER, event.provider_request_ref
        )
        if subscription is None:
            raise ApiError(
                status_code=202,
                code="payment_callback_unmatched",
                message="Callback accepted for reconciliation",
            )
        self.repository.add(
            SubscriptionEvent(
                id=uuid4(),
                subscription_id=subscription.id,
                provider=MPESA_PROVIDER,
                provider_event_ref=event.provider_event_ref[:160],
                event_type=event.outcome_hint,
                payload_redacted=event.redacted_payload,
            )
        )
        self.repository.add(
            self._status_job(subscription.id, f"callback:{event.provider_event_ref}", 0)
        )
        try:
            await self.repository.commit()
        except IntegrityError:
            # Safaricom retried a callback that is already recorded.
            await self.repository.rollback()

    async def reconcile(self, subscription_id: UUID) -> None:
        subscription = await self.repository.subscription(subscription_id)
        if (
            subscription is None
            or subscription.provider != MPESA_PROVIDER
            or subscription.provider_subscription_ref is None
            or subscription.status != "pending"
        ):
            return
        provider: PaymentProvider | None = None
        try:
            provider = self._provider()
            status = await provider.query_status(subscription.provider_subscription_ref)
        finally:
            await self._close(provider)
        subscription = await self.repository.subscription(subscription_id, lock=True)
        if subscription is None or subscription.status != "pending":
            return
        if status.outcome == "succeeded":
            plan = await self.repository.plan(subscription.plan_id)
            if plan is None:
                raise RuntimeError("Subscription plan is missing")
            status = await self._with_callback_evidence(subscription, status)
            discrepancy = self._discrepancy(subscription, plan, status)
            if discrepancy is not None:
                # Money may have moved but not as requested; keep Premium locked for review.
                subscription.failure_reason = discrepancy
                await self.repository.commit()
                return
            now = _now()
            paid_until = await self.repository.paid_until(
                subscription.user_id, MPESA_PROVIDER, plan.id
            )
            start = max(now, paid_until) if paid_until is not None else now
            subscription.status = "active"
            subscription.verified_at = now
            subscription.current_period_start = start
            subscription.current_period_end = start + PERIODS[plan.billing_interval]
            subscription.failure_reason = None
        elif status.outcome in UNPAID_STATUSES:
            subscription.status = UNPAID_STATUSES[status.outcome]
            subscription.failure_reason = (status.result_description or status.result_code)[:255]
        await self.repository.commit()

    async def _with_callback_evidence(
        self, subscription: Subscription, status: ProviderStatus
    ) -> ProviderStatus:
        """Daraja's status query omits the amount and receipt; the success callback has them."""
        if status.amount is not None and status.transaction_ref is not None:
            return status
        event = await self.repository.success_event(subscription.id)
        payload = event.payload_redacted if event is not None else {}
        amount = status.amount
        if amount is None and payload.get("Amount") not in (None, ""):
            amount = Decimal(str(payload["Amount"]))
        receipt = status.transaction_ref
        if receipt is None and payload.get("MpesaReceiptNumber"):
            receipt = str(payload["MpesaReceiptNumber"])
        return replace(status, amount=amount, transaction_ref=receipt)

    def _discrepancy(
        self, subscription: Subscription, plan: Plan, status: ProviderStatus
    ) -> str | None:
        if status.currency != plan.currency:
            return "amount_or_currency_mismatch"
        if status.amount is not None and status.amount != plan.price_amount:
            return "amount_or_currency_mismatch"
        if (
            status.payer_phone_e164
            and subscription.payer_phone_e164
            and status.payer_phone_e164 != subscription.payer_phone_e164
        ):
            return "payer_phone_mismatch"
        if status.merchant_account and status.merchant_account != self.settings.daraja_shortcode:
            return "merchant_account_mismatch"
        return None

    def _status_job(self, subscription_id: UUID, key: str, delay_seconds: int) -> OutboxJob:
        return OutboxJob(
            id=uuid4(),
            job_type=STATUS_QUERY_JOB,
            dedupe_key=f"premium-mpesa:{subscription_id}:{key}"[:160],
            payload={"subscription_id": str(subscription_id)},
            status="pending",
            attempts=0,
            max_attempts=max(1, self.settings.daraja_retry_limit),
            available_at=_now() + timedelta(seconds=delay_seconds),
        )

    def _provider(self) -> PaymentProvider:
        return self.provider or DarajaProvider(self.settings)

    @staticmethod
    async def _close(provider: PaymentProvider | None) -> None:
        if isinstance(provider, DarajaProvider):
            await provider.aclose()
