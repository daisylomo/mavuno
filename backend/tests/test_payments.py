from __future__ import annotations

from decimal import Decimal
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, create_autospec
from uuid import uuid4

import httpx2 as httpx
import pytest
from pydantic import SecretStr, ValidationError

from mavuno.api.errors import ApiError
from mavuno.auth.context import AuthenticatedUser
from mavuno.commerce.repository import CommerceRepository
from mavuno.commerce.schemas import PaymentInitiateRequest
from mavuno.commerce.service import PaymentService, _now
from mavuno.core.config import Settings
from mavuno.db.models import Order, Payment
from mavuno.payments.bank import UnconfiguredBankProvider
from mavuno.payments.daraja import DarajaProvider
from mavuno.payments.provider import (
    CallbackEvent,
    InitiationRequest,
    InitiationResult,
    PaymentProviderError,
    ProviderStatus,
)


def payment_settings() -> Settings:
    return Settings(
        environment="test",
        payments_enabled=True,
        daraja_consumer_key=SecretStr("consumer-key"),
        daraja_consumer_secret=SecretStr("consumer-secret"),
        daraja_shortcode="174379",
        daraja_passkey=SecretStr("passkey"),
        daraja_callback_base_url="https://api.example.test",
        daraja_callback_token=SecretStr("c" * 32),
    )


@pytest.mark.anyio
async def test_daraja_stk_and_status_contract() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/oauth/v1/generate":
            return httpx.Response(200, json={"access_token": "sandbox-token"})
        if request.url.path.endswith("processrequest"):
            return httpx.Response(
                200,
                json={
                    "ResponseCode": "0",
                    "MerchantRequestID": "merchant-1",
                    "CheckoutRequestID": "checkout-1",
                },
            )
        return httpx.Response(
            200,
            json={
                "ResultCode": "0",
                "Amount": "125",
                "PhoneNumber": "254712345678",
                "BusinessShortCode": "174379",
                "MpesaReceiptNumber": "RCP123",
                "ResultDesc": "Processed",
            },
        )

    client = httpx.AsyncClient(
        base_url="https://sandbox.safaricom.co.ke", transport=httpx.MockTransport(handler)
    )
    provider = DarajaProvider(payment_settings(), client)
    initiated = await provider.initiate(
        InitiationRequest(
            amount=Decimal("125"),
            currency="KES",
            phone_e164="+254712345678",
            account_reference="MVN123",
            description="Mavuno order",
        )
    )
    assert initiated.provider_request_ref == "checkout-1"
    status = await provider.query_status("checkout-1")
    assert status.outcome == "succeeded"
    assert status.amount == Decimal("125")
    assert status.payer_phone_e164 == "+254712345678"
    assert len(requests) == 4
    assert "consumer-secret" not in str(requests[-1].content)
    await client.aclose()


@pytest.mark.anyio
async def test_daraja_callback_is_redacted_and_untrusted() -> None:
    client = httpx.AsyncClient()
    provider = DarajaProvider(payment_settings(), client)
    event = provider.parse_callback(
        {
            "Body": {
                "stkCallback": {
                    "MerchantRequestID": "merchant-1",
                    "CheckoutRequestID": "checkout-1",
                    "ResultCode": 0,
                    "ResultDesc": "Success",
                    "CallbackMetadata": {"Item": [{"Name": "PhoneNumber", "Value": 254700000000}]},
                }
            }
        }
    )
    assert event.authenticated is False
    assert "CallbackMetadata" not in event.redacted_payload
    assert event.outcome_hint == "succeeded"
    with pytest.raises(PaymentProviderError):
        provider.parse_callback({"unexpected": True})
    await client.aclose()


@pytest.mark.anyio
async def test_daraja_rejects_fractional_mpesa_and_provider_failures() -> None:
    client = httpx.AsyncClient()
    provider = DarajaProvider(payment_settings(), client)
    with pytest.raises(PaymentProviderError):
        await provider.initiate(
            InitiationRequest(
                amount=Decimal("1.50"),
                currency="KES",
                phone_e164="+254712345678",
                account_reference="MVN",
                description="Order",
            )
        )
    with pytest.raises(PaymentProviderError):
        await provider.reverse("RCP", Decimal("1"), "Test")
    bank = UnconfiguredBankProvider()
    with pytest.raises(PaymentProviderError):
        await bank.initiate(
            InitiationRequest(
                amount=Decimal("1"),
                currency="KES",
                phone_e164="+254712345678",
                account_reference="MVN",
                description="Order",
            )
        )
    with pytest.raises(PaymentProviderError):
        bank.parse_callback({})
    with pytest.raises(PaymentProviderError):
        await bank.query_status("request")
    with pytest.raises(PaymentProviderError):
        await bank.reverse("receipt", Decimal("1"), "reason")
    await client.aclose()


@pytest.mark.anyio
async def test_daraja_fails_closed_on_configuration_and_bad_responses() -> None:
    with pytest.raises(PaymentProviderError, match="not configured"):
        DarajaProvider(Settings(environment="test"))

    request = InitiationRequest(
        amount=Decimal("125"),
        currency="KES",
        phone_e164="+254712345678",
        account_reference="MVN123",
        description="Order",
    )

    def missing_token(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    client = httpx.AsyncClient(
        base_url="https://sandbox.safaricom.co.ke", transport=httpx.MockTransport(missing_token)
    )
    with pytest.raises(PaymentProviderError, match="no token"):
        await DarajaProvider(payment_settings(), client).initiate(request)
    await client.aclose()

    def missing_reference(http_request: httpx.Request) -> httpx.Response:
        if http_request.url.path == "/oauth/v1/generate":
            return httpx.Response(200, json={"access_token": "token"})
        return httpx.Response(200, json={"ResponseCode": "0"})

    client = httpx.AsyncClient(
        base_url="https://sandbox.safaricom.co.ke",
        transport=httpx.MockTransport(missing_reference),
    )
    with pytest.raises(PaymentProviderError, match="request reference"):
        await DarajaProvider(payment_settings(), client).initiate(request)
    await client.aclose()

    assert DarajaProvider._failure_outcome("1032") == "cancelled"
    assert DarajaProvider._failure_outcome("1037") == "expired"
    assert DarajaProvider._failure_outcome("9999") == "failed"
    assert DarajaProvider._normalize_optional_phone(None) is None
    assert DarajaProvider._normalize_optional_phone("+254712345678") == "+254712345678"


class FakeProvider:
    name = "daraja"

    def __init__(self, status: ProviderStatus | None = None) -> None:
        self.status = status

    async def initiate(self, request: InitiationRequest) -> InitiationResult:
        return InitiationResult("checkout-1", "merchant-1", "pending", "0")

    def parse_callback(self, payload: dict[str, object]) -> CallbackEvent:
        return CallbackEvent("checkout-1:0", "checkout-1", "succeeded", False, {"ResultCode": "0"})

    async def query_status(self, provider_request_ref: str) -> ProviderStatus:
        assert self.status is not None
        return self.status

    async def reverse(self, transaction_ref: str, amount: Decimal, reason: str) -> str:
        return "reversal-1"


@pytest.fixture
def repository() -> Any:
    repo = create_autospec(CommerceRepository, instance=True)
    repo.add = MagicMock()
    repo.commit = AsyncMock()
    repo.rollback = AsyncMock()
    repo.refresh = AsyncMock()
    return repo


@pytest.fixture
def buyer() -> AuthenticatedUser:
    return AuthenticatedUser(uuid4(), "buyer@example.test", None, frozenset({"buyer"}), 0)


def payable_order(buyer: AuthenticatedUser) -> Order:
    order = Order(
        id=uuid4(),
        buyer_id=buyer.id,
        status="pending_payment",
        currency="KES",
        subtotal_amount=Decimal("125"),
        total_amount=Decimal("125"),
        idempotency_key="checkout-key",
        reservation_expires_at=_now().replace(year=_now().year + 1),
        version=1,
    )
    order.created_at = _now()
    order.updated_at = _now()
    return order


@pytest.mark.anyio
async def test_payment_initiation_is_idempotent(repository: Any, buyer: AuthenticatedUser) -> None:
    order = payable_order(buyer)
    repository.order = AsyncMock(return_value=order)
    repository.existing_payment = AsyncMock(return_value=None)

    async def set_values(value: Payment) -> None:
        value.created_at = _now()
        value.updated_at = _now()

    repository.refresh = AsyncMock(side_effect=set_values)
    service = PaymentService(
        cast(CommerceRepository, repository), payment_settings(), FakeProvider()
    )
    payment = await service.initiate(
        buyer,
        PaymentInitiateRequest(order_id=order.id, rail="mpesa", phone_e164="0712345678"),
        "payment-key",
    )
    assert payment.state == "pending_customer"
    assert payment.provider_request_ref == "checkout-1"
    assert payment.payer_phone_e164 == "+254712345678"
    assert repository.add.call_count == 2

    repository.existing_payment = AsyncMock(return_value=payment)
    same = await service.initiate(
        buyer,
        PaymentInitiateRequest(order_id=order.id, rail="mpesa", phone_e164="0712345678"),
        "payment-key",
    )
    assert same is payment


@pytest.mark.anyio
async def test_verified_matching_status_is_the_only_success_path(
    repository: Any, buyer: AuthenticatedUser
) -> None:
    order = payable_order(buyer)
    payment = Payment(
        id=uuid4(),
        order_id=order.id,
        rail="mpesa",
        provider="daraja",
        amount=Decimal("125"),
        currency="KES",
        state="processing",
        idempotency_key="key",
        provider_request_ref="checkout-1",
        payer_phone_e164="+254712345678",
        account_reference="MVN123",
    )
    status = ProviderStatus(
        "checkout-1",
        "succeeded",
        Decimal("125"),
        "KES",
        "+254712345678",
        "174379",
        "RCP123",
        "0",
        "Success",
    )
    repository.payment = AsyncMock(side_effect=[payment, payment])
    repository.order = AsyncMock(return_value=order)
    service = PaymentService(
        cast(CommerceRepository, repository), payment_settings(), FakeProvider(status)
    )
    await service.reconcile(payment.id)
    assert payment.state == "succeeded"
    assert order.status == "paid"
    assert order.paid_at is not None

    payment.state = "processing"
    mismatch = ProviderStatus(
        "checkout-1",
        "succeeded",
        Decimal("124"),
        "KES",
        "+254712345678",
        "174379",
        "RCP124",
        "0",
        "Success",
    )
    repository.payment = AsyncMock(side_effect=[payment, payment])
    await PaymentService(
        cast(CommerceRepository, repository), payment_settings(), FakeProvider(mismatch)
    ).reconcile(payment.id)
    assert payment.state == "processing"


@pytest.mark.anyio
async def test_payment_validation_and_provider_failure_paths(
    repository: Any, buyer: AuthenticatedUser
) -> None:
    disabled = PaymentService(
        cast(CommerceRepository, repository), Settings(environment="test"), FakeProvider()
    )
    request = PaymentInitiateRequest(order_id=uuid4(), rail="mpesa", phone_e164="0712345678")
    with pytest.raises(ApiError) as unavailable:
        await disabled.initiate(buyer, request, "payment-key")
    assert unavailable.value.code == "payments_disabled"

    service = PaymentService(
        cast(CommerceRepository, repository), payment_settings(), FakeProvider()
    )
    repository.order = AsyncMock(return_value=None)
    with pytest.raises(ApiError) as missing:
        await service.initiate(buyer, request, "payment-key")
    assert missing.value.code == "order_not_found"

    order = payable_order(buyer)
    repository.order = AsyncMock(return_value=order)
    repository.existing_payment = AsyncMock(return_value=None)
    for phone, code in ((None, "phone_required"), ("abcdefghij", "invalid_phone")):
        with pytest.raises(ApiError) as invalid:
            await service.initiate(
                buyer,
                PaymentInitiateRequest(order_id=order.id, rail="mpesa", phone_e164=phone),
                "payment-key",
            )
        assert invalid.value.code == code

    order.status = "expired"
    with pytest.raises(ApiError) as not_payable:
        await service.initiate(buyer, request, "payment-key")
    assert not_payable.value.code == "order_not_payable"


@pytest.mark.anyio
async def test_callback_is_queued_but_never_credits_directly(
    repository: Any, buyer: AuthenticatedUser
) -> None:
    payment = Payment(
        id=uuid4(),
        order_id=uuid4(),
        rail="mpesa",
        provider="daraja",
        amount=Decimal("125"),
        currency="KES",
        state="processing",
        idempotency_key="key",
        provider_request_ref="checkout-1",
        payer_phone_e164="+254712345678",
        account_reference="MVN123",
    )
    service = PaymentService(
        cast(CommerceRepository, repository), payment_settings(), FakeProvider()
    )
    with pytest.raises(ApiError) as hidden:
        await service.accept_callback("wrong-token", {})
    assert hidden.value.code == "webhook_not_found"

    repository.payment_by_request_ref = AsyncMock(return_value=None)
    with pytest.raises(ApiError) as unmatched:
        await service.accept_callback("c" * 32, {})
    assert unmatched.value.code == "payment_callback_unmatched"

    repository.payment_by_request_ref = AsyncMock(return_value=payment)
    await service.accept_callback("c" * 32, {})
    assert repository.add.call_count == 2
    assert payment.state == "processing"


@pytest.mark.anyio
async def test_failed_provider_status_is_persisted(repository: Any) -> None:
    payment = Payment(
        id=uuid4(),
        order_id=uuid4(),
        rail="mpesa",
        provider="daraja",
        amount=Decimal("125"),
        currency="KES",
        state="processing",
        idempotency_key="key",
        provider_request_ref="checkout-1",
        payer_phone_e164="+254712345678",
        account_reference="MVN123",
    )
    failed = ProviderStatus(
        "checkout-1", "cancelled", None, "KES", None, None, None, "1032", "Cancelled"
    )
    repository.payment = AsyncMock(side_effect=[payment, payment])
    await PaymentService(
        cast(CommerceRepository, repository), payment_settings(), FakeProvider(failed)
    ).reconcile(payment.id)
    assert payment.state == "cancelled"
    assert payment.failure_code == "1032"


def test_reconciliation_discrepancy_reasons(repository: Any) -> None:
    settings = payment_settings()
    service = PaymentService(cast(CommerceRepository, repository), settings, FakeProvider())
    payment = Payment(
        id=uuid4(),
        order_id=uuid4(),
        rail="mpesa",
        provider="daraja",
        amount=Decimal("125"),
        currency="KES",
        state="processing",
        idempotency_key="key",
        payer_phone_e164="+254712345678",
        account_reference="MVN123",
    )
    base = ProviderStatus(
        provider_request_ref="checkout",
        outcome="succeeded",
        amount=Decimal("125"),
        currency="KES",
        payer_phone_e164="+254712345678",
        merchant_account="174379",
        transaction_ref="RCP",
        result_code="0",
        result_description="Success",
    )
    assert service._discrepancy(payment, base) is None
    assert (
        service._discrepancy(
            payment,
            ProviderStatus(
                "checkout",
                "succeeded",
                Decimal("124"),
                "KES",
                "+254712345678",
                "174379",
                "RCP",
                "0",
                "Success",
            ),
        )
        == "amount_or_currency_mismatch"
    )
    assert (
        service._discrepancy(
            payment,
            ProviderStatus(
                "checkout",
                "succeeded",
                Decimal("125"),
                "KES",
                "+254700000000",
                "174379",
                "RCP",
                "0",
                "Success",
            ),
        )
        == "payer_phone_mismatch"
    )
    assert (
        service._discrepancy(
            payment,
            ProviderStatus(
                "checkout",
                "succeeded",
                Decimal("125"),
                "KES",
                "+254712345678",
                "999999",
                "RCP",
                "0",
                "Success",
            ),
        )
        == "merchant_account_mismatch"
    )
    assert (
        service._discrepancy(
            payment,
            ProviderStatus(
                "checkout",
                "succeeded",
                Decimal("125"),
                "KES",
                "+254712345678",
                "174379",
                None,
                "0",
                "Success",
            ),
        )
        == "transaction_reference_missing"
    )


def test_payment_configuration_fails_closed() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="test", payments_enabled=True)
