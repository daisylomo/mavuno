from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, create_autospec
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy.exc import IntegrityError

from mavuno.api.errors import ApiError
from mavuno.api.v1 import premium
from mavuno.auth.context import AuthenticatedUser
from mavuno.core.config import Settings
from mavuno.db.models import OutboxJob, Plan, Subscription, SubscriptionEvent
from mavuno.payments.provider import (
    CallbackEvent,
    InitiationRequest,
    InitiationResult,
    PaymentOutcome,
    PaymentProviderError,
    ProviderStatus,
    ReversalResult,
)
from mavuno.premium.mpesa import (
    CALLBACK_PATH,
    MPESA_PROVIDER,
    STATUS_QUERY_JOB,
    MpesaPremiumService,
)
from mavuno.premium.repository import PremiumRepository
from mavuno.premium.schemas import MpesaPremiumPayment
from mavuno.premium.service import _now

TOKEN = "c" * 32
PHONE = "+254712345678"


def settings(enabled: bool = True) -> Settings:
    if not enabled:
        return Settings(environment="test")
    return Settings(
        environment="test",
        payments_enabled=True,
        daraja_consumer_key=SecretStr("key"),
        daraja_consumer_secret=SecretStr("secret"),
        daraja_shortcode="174379",
        daraja_passkey=SecretStr("passkey"),
        daraja_callback_base_url="https://api.example.test",
        daraja_callback_token=SecretStr(TOKEN),
    )


def member(role: str = "buyer") -> AuthenticatedUser:
    return AuthenticatedUser(uuid4(), "member@example.test", None, frozenset({role}), 0)


def mpesa_plan(audience: str = "buyer", price: str = "1") -> Plan:
    return Plan(
        id=uuid4(),
        code=f"mpesa_{audience}_monthly",
        name="Mavuno Premium (monthly)",
        audience=audience,
        price_amount=Decimal(price),
        currency="KES",
        billing_interval="month",
        features=["prebooking"],
        active=True,
    )


def status_of(
    outcome: PaymentOutcome,
    amount: Decimal | None = Decimal("1"),
    phone: str | None = PHONE,
    merchant: str | None = "174379",
) -> ProviderStatus:
    return ProviderStatus(
        provider_request_ref="ws_CO_1",
        outcome=outcome,
        amount=amount,
        currency="KES",
        payer_phone_e164=phone,
        merchant_account=merchant,
        transaction_ref="RCPT1" if outcome == "succeeded" and amount is not None else None,
        result_code="0" if outcome == "succeeded" else "1032",
        result_description="Request cancelled by user" if outcome != "succeeded" else "OK",
    )


class FakeDaraja:
    name = "daraja"

    def __init__(self, status: ProviderStatus | None = None, fail: bool = False) -> None:
        self.status = status
        self.fail = fail
        self.requests: list[InitiationRequest] = []

    async def initiate(self, request: InitiationRequest) -> InitiationResult:
        if self.fail:
            raise PaymentProviderError("Daraja request failed")
        self.requests.append(request)
        return InitiationResult("ws_CO_1", "merchant-1", "pending", "0")

    def parse_callback(self, payload: dict[str, object]) -> CallbackEvent:
        if not payload:
            raise PaymentProviderError("Malformed Daraja callback")
        return CallbackEvent(
            provider_event_ref="ws_CO_1:0",
            provider_request_ref="ws_CO_1",
            outcome_hint="succeeded",
            authenticated=False,
            redacted_payload={"Amount": "1", "MpesaReceiptNumber": "RCPT1"},
        )

    async def query_status(self, provider_request_ref: str) -> ProviderStatus:
        if self.fail:
            raise PaymentProviderError("Daraja request failed")
        assert self.status is not None
        return self.status

    async def reverse(self, transaction_ref: str, amount: Decimal, reason: str) -> ReversalResult:
        raise NotImplementedError


@pytest.fixture
def repository() -> Any:
    value = create_autospec(PremiumRepository, instance=True)
    value.add = MagicMock()
    value.commit = AsyncMock()
    value.rollback = AsyncMock()
    value.refresh = AsyncMock()
    value.subscription_by_idempotency = AsyncMock(return_value=None)
    value.open_prompt = AsyncMock(return_value=False)
    value.paid_until = AsyncMock(return_value=None)
    value.success_event = AsyncMock(return_value=None)
    return value


def pending(user_id: Any = None, plan_id: Any = None) -> Subscription:
    return Subscription(
        id=uuid4(),
        user_id=user_id or uuid4(),
        plan_id=plan_id or uuid4(),
        status="pending",
        provider=MPESA_PROVIDER,
        provider_subscription_ref="ws_CO_1",
        account_reference="MVPABC123456",
        idempotency_key="key-1",
        payer_phone_e164=PHONE,
    )


@pytest.mark.anyio
async def test_pay_sends_stk_prompt_to_premium_callback_and_schedules_checks(
    repository: Any,
) -> None:
    buyer, plan = member(), mpesa_plan()
    repository.plan = AsyncMock(return_value=plan)
    daraja = FakeDaraja()
    subscription = await MpesaPremiumService(
        cast(PremiumRepository, repository), settings(), daraja
    ).pay(buyer, plan.id, "0712 345 678", "premium-key")
    assert subscription.status == "pending"
    assert subscription.provider == MPESA_PROVIDER
    assert subscription.provider_subscription_ref == "ws_CO_1"
    assert subscription.payer_phone_e164 == PHONE
    assert len(subscription.account_reference) == 12
    sent = daraja.requests[0]
    assert sent.amount == Decimal("1") and sent.phone_e164 == PHONE
    assert sent.callback_path == CALLBACK_PATH
    jobs = [c.args[0] for c in repository.add.call_args_list if isinstance(c.args[0], OutboxJob)]
    assert [job.job_type for job in jobs] == [STATUS_QUERY_JOB] * 3

    repository.subscription_by_idempotency = AsyncMock(return_value=subscription)
    assert (
        await MpesaPremiumService(cast(PremiumRepository, repository), settings(), daraja).pay(
            buyer, plan.id, PHONE, "premium-key"
        )
        is subscription
    )
    assert len(daraja.requests) == 1


@pytest.mark.anyio
async def test_pay_rejects_unpayable_requests(repository: Any) -> None:
    buyer, plan = member(), mpesa_plan()
    repository.plan = AsyncMock(return_value=plan)

    async def code(
        service_settings: Settings, user: AuthenticatedUser = buyer, phone: str = PHONE
    ) -> str:
        with pytest.raises(ApiError) as error:
            await MpesaPremiumService(
                cast(PremiumRepository, repository), service_settings, FakeDaraja()
            ).pay(user, plan.id, phone, "k")
        return error.value.code

    assert await code(settings(enabled=False)) == "mpesa_unavailable"
    assert await code(settings(), user=member("farmer")) == "plan_not_available"
    assert await code(settings(), phone="12") == "invalid_phone"
    repository.open_prompt = AsyncMock(return_value=True)
    assert await code(settings()) == "payment_in_progress"
    repository.open_prompt = AsyncMock(return_value=False)
    repository.plan = AsyncMock(return_value=mpesa_plan(price="1.50"))
    assert await code(settings()) == "plan_not_payable"
    store = mpesa_plan()
    store.code = "revenuecat_buyer"
    repository.plan = AsyncMock(return_value=store)
    assert await code(settings()) == "plan_not_found"
    repository.plan = AsyncMock(return_value=None)
    assert await code(settings()) == "plan_not_found"


@pytest.mark.anyio
async def test_unreachable_mpesa_marks_the_attempt_failed(repository: Any) -> None:
    plan = mpesa_plan()
    repository.plan = AsyncMock(return_value=plan)
    with pytest.raises(ApiError) as error:
        await MpesaPremiumService(
            cast(PremiumRepository, repository), settings(), FakeDaraja(fail=True)
        ).pay(member(), plan.id, PHONE, "k")
    assert error.value.status_code == 503
    added = repository.add.call_args_list[0].args[0]
    assert added.status == "failed" and added.failure_reason == "M-PESA could not be reached"


@pytest.mark.anyio
async def test_verified_payment_unlocks_one_period_and_renewals_extend_it(
    repository: Any,
) -> None:
    plan = mpesa_plan()
    subscription = pending(plan_id=plan.id)
    repository.subscription = AsyncMock(return_value=subscription)
    repository.plan = AsyncMock(return_value=plan)
    await MpesaPremiumService(
        cast(PremiumRepository, repository), settings(), FakeDaraja(status_of("succeeded"))
    ).reconcile(subscription.id)
    assert subscription.status == "active" and subscription.verified_at is not None
    assert subscription.current_period_start is not None
    assert subscription.current_period_end is not None
    period = subscription.current_period_end - subscription.current_period_start
    assert period == timedelta(days=30)

    renewal = pending(plan_id=plan.id)
    paid_until = _now() + timedelta(days=10)
    repository.subscription = AsyncMock(return_value=renewal)
    repository.paid_until = AsyncMock(return_value=paid_until)
    await MpesaPremiumService(
        cast(PremiumRepository, repository), settings(), FakeDaraja(status_of("succeeded"))
    ).reconcile(renewal.id)
    assert renewal.current_period_start == paid_until
    assert renewal.current_period_end == paid_until + timedelta(days=30)


@pytest.mark.anyio
async def test_query_without_amount_uses_callback_evidence(repository: Any) -> None:
    plan = mpesa_plan()
    subscription = pending(plan_id=plan.id)
    repository.subscription = AsyncMock(return_value=subscription)
    repository.plan = AsyncMock(return_value=plan)
    repository.success_event = AsyncMock(
        return_value=SubscriptionEvent(payload_redacted={"Amount": "5", "MpesaReceiptNumber": "R"})
    )
    await MpesaPremiumService(
        cast(PremiumRepository, repository), settings(), FakeDaraja(status_of("succeeded", None))
    ).reconcile(subscription.id)
    assert subscription.status == "pending"
    assert subscription.failure_reason == "amount_or_currency_mismatch"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (status_of("succeeded", Decimal("2")), "amount_or_currency_mismatch"),
        (status_of("succeeded", phone="+254700000000"), "payer_phone_mismatch"),
        (status_of("succeeded", merchant="999999"), "merchant_account_mismatch"),
    ],
)
async def test_discrepancies_keep_premium_locked(
    repository: Any, status: ProviderStatus, reason: str
) -> None:
    plan = mpesa_plan()
    subscription = pending(plan_id=plan.id)
    repository.subscription = AsyncMock(return_value=subscription)
    repository.plan = AsyncMock(return_value=plan)
    await MpesaPremiumService(
        cast(PremiumRepository, repository), settings(), FakeDaraja(status)
    ).reconcile(subscription.id)
    assert subscription.status == "pending" and subscription.verified_at is None
    assert subscription.failure_reason == reason


@pytest.mark.anyio
async def test_unpaid_outcomes_close_the_attempt(repository: Any) -> None:
    for outcome, expected in [
        ("cancelled", "cancelled"),
        ("failed", "failed"),
        ("expired", "expired"),
    ]:
        subscription = pending()
        repository.subscription = AsyncMock(return_value=subscription)
        await MpesaPremiumService(
            cast(PremiumRepository, repository),
            settings(),
            FakeDaraja(status_of(cast(PaymentOutcome, outcome))),
        ).reconcile(subscription.id)
        assert subscription.status == expected
        assert subscription.failure_reason == "Request cancelled by user"

    still_open = pending()
    repository.subscription = AsyncMock(return_value=still_open)
    await MpesaPremiumService(
        cast(PremiumRepository, repository), settings(), FakeDaraja(status_of("pending"))
    ).reconcile(still_open.id)
    assert still_open.status == "pending"

    for settled in (Subscription(status="active", provider=MPESA_PROVIDER), None):
        repository.subscription = AsyncMock(return_value=settled)
        await MpesaPremiumService(
            cast(PremiumRepository, repository), settings(), FakeDaraja()
        ).reconcile(uuid4())


@pytest.mark.anyio
async def test_callback_is_authenticated_recorded_and_triggers_a_check(repository: Any) -> None:
    service = MpesaPremiumService(cast(PremiumRepository, repository), settings(), FakeDaraja())
    with pytest.raises(ApiError) as forbidden:
        await service.callback("wrong", {"Body": {}})
    assert forbidden.value.status_code == 404
    with pytest.raises(ApiError) as malformed:
        await service.callback(TOKEN, {})
    assert malformed.value.status_code == 422
    repository.subscription_by_provider_ref = AsyncMock(return_value=None)
    with pytest.raises(ApiError) as unmatched:
        await service.callback(TOKEN, {"Body": {}})
    assert unmatched.value.status_code == 202

    subscription = pending()
    repository.subscription_by_provider_ref = AsyncMock(return_value=subscription)
    await service.callback(TOKEN, {"Body": {}})
    added = [c.args[0] for c in repository.add.call_args_list]
    assert isinstance(added[0], SubscriptionEvent) and added[0].event_type == "succeeded"
    assert isinstance(added[1], OutboxJob) and added[1].job_type == STATUS_QUERY_JOB
    repository.commit = AsyncMock(side_effect=IntegrityError("insert", {}, Exception()))
    await service.callback(TOKEN, {"Body": {}})
    repository.rollback.assert_awaited()


@pytest.mark.anyio
async def test_member_refresh_checks_their_own_pending_payment(repository: Any) -> None:
    buyer, plan = member(), mpesa_plan()
    subscription = pending(user_id=buyer.id, plan_id=plan.id)
    repository.subscription = AsyncMock(return_value=subscription)
    repository.plan = AsyncMock(return_value=plan)
    value = await MpesaPremiumService(
        cast(PremiumRepository, repository), settings(), FakeDaraja(status_of("succeeded"))
    ).refresh(buyer, subscription.id)
    assert value.status == "active"

    with pytest.raises(ApiError) as other:
        await MpesaPremiumService(
            cast(PremiumRepository, repository), settings(), FakeDaraja()
        ).refresh(member(), subscription.id)
    assert other.value.status_code == 404

    subscription.status = "pending"
    with pytest.raises(ApiError) as down:
        await MpesaPremiumService(
            cast(PremiumRepository, repository), settings(), FakeDaraja(fail=True)
        ).refresh(buyer, subscription.id)
    assert down.value.status_code == 503


@pytest.mark.anyio
async def test_mpesa_routes_delegate_to_the_service(monkeypatch: pytest.MonkeyPatch) -> None:
    current = member()
    request = cast(
        Any,
        SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(settings=settings())),
            body=AsyncMock(return_value=json.dumps({"Body": {}}).encode()),
        ),
    )
    service = MagicMock()
    service.pay = AsyncMock(return_value="pending")
    service.refresh = AsyncMock(return_value="active")
    service.callback = AsyncMock()
    monkeypatch.setattr(premium, "MpesaPremiumService", lambda *_args: service)
    session = MagicMock()
    plan_id, subscription_id = uuid4(), uuid4()
    payload = MpesaPremiumPayment(plan_id=plan_id, phone_e164=PHONE)
    assert (
        await premium.pay_premium_with_mpesa(payload, "key-12345", current, session, request)
        == "pending"
    )
    service.pay.assert_awaited_once_with(current, plan_id, PHONE, "key-12345")
    assert (
        await premium.refresh_premium_mpesa_payment(subscription_id, current, session, request)
        == "active"
    )
    assert await premium.premium_mpesa_callback(TOKEN, request, session) == {"accepted": True}
    service.callback.assert_awaited_with(TOKEN, {"Body": {}})
    for body in (b"not-json", b"[1]"):
        request.body = AsyncMock(return_value=body)
        await premium.premium_mpesa_callback(TOKEN, request, session)
        service.callback.assert_awaited_with(TOKEN, {})
