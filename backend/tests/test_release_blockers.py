"""Payment confirmation, late payments, refunds and cancellation (unit level)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, create_autospec
from uuid import UUID, uuid4

import httpx2 as httpx
import pytest
from pydantic import SecretStr

from mavuno.api.errors import ApiError
from mavuno.auth.context import AuthenticatedUser
from mavuno.commerce.refunds import RefundService
from mavuno.commerce.repository import CommerceRepository
from mavuno.commerce.service import CheckoutService, PaymentService, _now, payable_total
from mavuno.core.config import Settings
from mavuno.db.models import (
    Cart,
    CartItem,
    Fulfilment,
    Listing,
    Order,
    OrderItem,
    OrderStatusHistory,
    OutboxJob,
    Payment,
    PaymentEvent,
    PaymentRefund,
)
from mavuno.payments.daraja import DarajaProvider
from mavuno.payments.provider import (
    CallbackEvent,
    InitiationRequest,
    InitiationResult,
    PaymentOutcome,
    PaymentProviderError,
    ProviderStatus,
    ReversalNotConfiguredError,
    ReversalResult,
)

TOKEN = "c" * 32


def settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "environment": "test",
        "payments_enabled": True,
        "daraja_consumer_key": SecretStr("consumer-key"),
        "daraja_consumer_secret": SecretStr("consumer-secret"),
        "daraja_shortcode": "174379",
        "daraja_passkey": SecretStr("passkey"),
        "daraja_callback_base_url": "https://api.example.test",
        "daraja_callback_token": SecretStr(TOKEN),
    }
    values.update(overrides)
    return Settings(**values)


def status(
    outcome: PaymentOutcome = "succeeded",
    amount: Decimal | None = None,
    receipt: str | None = None,
    code: str = "0",
) -> ProviderStatus:
    return ProviderStatus(
        "checkout-1", outcome, amount, "KES", None, "174379", receipt, code, "Result"
    )


class Provider:
    name = "daraja"

    def __init__(
        self,
        result: ProviderStatus | None = None,
        reversal: ReversalResult | Exception | None = None,
    ) -> None:
        self.result = result
        self.reversal = reversal
        self.reversed: list[tuple[str, Decimal]] = []

    async def initiate(self, request: InitiationRequest) -> InitiationResult:
        return InitiationResult("checkout-1", "merchant-1", "pending", "0")

    def parse_callback(self, payload: dict[str, object]) -> CallbackEvent:
        return CallbackEvent(
            "checkout-1:0",
            "checkout-1",
            "succeeded",
            False,
            {"ResultCode": "0"},
            Decimal("125"),
            "RCP777",
            "+254712345678",
        )

    async def query_status(self, provider_request_ref: str) -> ProviderStatus:
        assert self.result is not None
        return self.result

    async def reverse(self, transaction_ref: str, amount: Decimal, reason: str) -> ReversalResult:
        self.reversed.append((transaction_ref, amount))
        if isinstance(self.reversal, Exception):
            raise self.reversal
        return self.reversal or ReversalResult("conversation-1", True)


def buyer() -> AuthenticatedUser:
    return AuthenticatedUser(uuid4(), "buyer@example.test", None, frozenset({"buyer"}), 0)


def make_order(buyer_id: UUID, state: str = "pending_payment", total: str = "125") -> Order:
    value = Order(
        id=uuid4(),
        buyer_id=buyer_id,
        status=state,
        currency="KES",
        subtotal_amount=Decimal(total),
        total_amount=Decimal(total),
        idempotency_key="checkout",
        reservation_expires_at=_now() + timedelta(minutes=10),
        version=1,
    )
    value.created_at = _now()
    value.updated_at = _now()
    return value


def make_payment(order: Order, state: str = "processing", receipt: str | None = None) -> Payment:
    value = Payment(
        id=uuid4(),
        order_id=order.id,
        rail="mpesa",
        provider="daraja",
        amount=order.total_amount,
        currency="KES",
        state=state,
        idempotency_key="pay",
        provider_request_ref="checkout-1",
        provider_transaction_ref=receipt,
        payer_phone_e164="+254712345678",
        account_reference="MVN",
    )
    value.created_at = _now()
    value.updated_at = _now()
    return value


def make_listing(quantity: str, state: str = "active") -> Listing:
    return Listing(
        id=uuid4(),
        farmer_id=uuid4(),
        product_id=uuid4(),
        title="Maize",
        price_amount=Decimal("125"),
        currency="KES",
        available_quantity=Decimal(quantity),
        quantity_unit="kg",
        status=state,
        version=1,
    )


def item(order: Order, listing: Listing, quantity: str = "1") -> OrderItem:
    return OrderItem(
        id=uuid4(),
        order_id=order.id,
        listing_id=listing.id,
        farmer_id=listing.farmer_id,
        product_name="Maize",
        listing_title="Maize",
        quantity=Decimal(quantity),
        quantity_unit="kg",
        unit_price=Decimal("125"),
        line_total=Decimal("125") * Decimal(quantity),
    )


def added(repository: Any, kind: type) -> list[Any]:
    return [
        call.args[0] for call in repository.add.call_args_list if isinstance(call.args[0], kind)
    ]


@pytest.fixture
def repository() -> Any:
    repo = create_autospec(CommerceRepository, instance=True)
    repo.add = MagicMock()
    repo.commit = AsyncMock()
    repo.rollback = AsyncMock()
    repo.refresh = AsyncMock()
    repo.flush = AsyncMock()
    repo.in_flight_payment = AsyncMock(return_value=None)
    repo.success_callback = AsyncMock(return_value=None)
    repo.refunded_total = AsyncMock(return_value=Decimal("0"))
    repo.order_refunds = AsyncMock(return_value=[])
    return repo


def test_payable_total_rounds_down_to_whole_shillings() -> None:
    assert payable_total(Decimal("151.5")) == Decimal("151")
    assert payable_total(Decimal("100.0000")) == Decimal("100")
    assert payable_total(Decimal("0.75")) == Decimal("0")


@pytest.mark.anyio
async def test_approved_payment_confirmed_by_query_completes_the_order(repository: Any) -> None:
    """Daraja's STK query returns neither the amount nor the receipt; the order still pays."""
    order = make_order(uuid4())
    payment = make_payment(order)
    repository.payment = AsyncMock(return_value=payment)
    repository.order = AsyncMock(return_value=order)
    service = PaymentService(cast(CommerceRepository, repository), settings(), Provider(status()))
    await service.reconcile(payment.id)
    assert payment.state == "succeeded"
    assert payment.provider_transaction_ref is None
    assert order.status == "paid"
    assert order.paid_at is not None
    reconciliation = repository.add.call_args_list[0].args[0]
    assert reconciliation.state == "matched_query_only"


@pytest.mark.anyio
async def test_callback_evidence_supplies_receipt_and_amount(repository: Any) -> None:
    order = make_order(uuid4())
    payment = make_payment(order)
    evidence = PaymentEvent(
        id=uuid4(),
        payment_id=payment.id,
        provider="daraja",
        provider_event_ref="checkout-1:0",
        direction="callback",
        event_type="succeeded",
        payload_redacted={"Amount": "125", "MpesaReceiptNumber": "RCP900"},
        processing_state="queued",
    )
    repository.payment = AsyncMock(return_value=payment)
    repository.order = AsyncMock(return_value=order)
    repository.success_callback = AsyncMock(return_value=evidence)
    await PaymentService(
        cast(CommerceRepository, repository), settings(), Provider(status())
    ).reconcile(payment.id)
    assert payment.provider_transaction_ref == "RCP900"
    assert order.status == "paid"

    # A callback that reports a different amount is a discrepancy, never a payment.
    order.status, order.paid_at = "pending_payment", None
    payment.state = "processing"
    evidence.payload_redacted = {"Amount": "5", "MpesaReceiptNumber": "RCP901"}
    await PaymentService(
        cast(CommerceRepository, repository), settings(), Provider(status())
    ).reconcile(payment.id)
    assert payment.state == "processing"
    assert payment.failure_code == "reconciliation_discrepancy"
    assert order.status == "pending_payment"


@pytest.mark.anyio
async def test_pending_status_and_final_payments_do_not_change_orders(repository: Any) -> None:
    order = make_order(uuid4())
    payment = make_payment(order)
    repository.payment = AsyncMock(return_value=payment)
    repository.order = AsyncMock(return_value=order)
    await PaymentService(
        cast(CommerceRepository, repository), settings(), Provider(status("pending"))
    ).reconcile(payment.id)
    assert payment.state == "processing"
    assert order.status == "pending_payment"

    payment.state = "succeeded"
    before = repository.commit.await_count
    await PaymentService(
        cast(CommerceRepository, repository), settings(), Provider(status())
    ).reconcile(payment.id)
    assert repository.commit.await_count == before


@pytest.mark.anyio
async def test_late_payment_takes_stock_back_when_it_is_still_there(repository: Any) -> None:
    order = make_order(uuid4(), "expired")
    payment = make_payment(order)
    listing = make_listing("3")
    repository.payment = AsyncMock(return_value=payment)
    repository.order = AsyncMock(return_value=order)
    repository.order_items = AsyncMock(return_value=[item(order, listing, "3")])
    repository.listing = AsyncMock(return_value=listing)
    await PaymentService(
        cast(CommerceRepository, repository), settings(), Provider(status())
    ).reconcile(payment.id)
    assert order.status == "paid"
    assert listing.available_quantity == 0
    assert listing.status == "sold_out"
    history = added(repository, OrderStatusHistory)
    assert history[0].previous_status == "expired"
    assert added(repository, PaymentRefund) == []


@pytest.mark.anyio
async def test_late_payment_for_resold_stock_is_refunded_not_oversold(repository: Any) -> None:
    order = make_order(uuid4(), "expired")
    payment = make_payment(order)
    listing = make_listing("1")
    repository.payment = AsyncMock(return_value=payment)
    repository.order = AsyncMock(return_value=order)
    repository.order_items = AsyncMock(return_value=[item(order, listing, "2")])
    repository.listing = AsyncMock(return_value=listing)
    evidence = MagicMock(payload_redacted={"Amount": "125", "MpesaReceiptNumber": "RCP5"})
    repository.success_callback = AsyncMock(return_value=evidence)
    await PaymentService(
        cast(CommerceRepository, repository), settings(), Provider(status())
    ).reconcile(payment.id)
    assert order.status == "expired"
    assert listing.available_quantity == 1
    assert payment.state == "succeeded"
    refund = added(repository, PaymentRefund)[0]
    assert refund.reason == "late_payment_stock_unavailable"
    assert refund.state == "pending"
    assert added(repository, OutboxJob)[0].job_type == "payment_refund"


@pytest.mark.anyio
async def test_payment_for_cancelled_or_paid_order_is_refunded(repository: Any) -> None:
    for state, reason in (("cancelled", "order_cancelled"), ("paid", "duplicate_payment")):
        repository.add.reset_mock()
        order = make_order(uuid4(), state)
        payment = make_payment(order)
        repository.payment = AsyncMock(return_value=payment)
        repository.order = AsyncMock(return_value=order)
        await PaymentService(
            cast(CommerceRepository, repository), settings(), Provider(status())
        ).reconcile(payment.id)
        assert order.status == state
        refund = added(repository, PaymentRefund)[0]
        assert refund.reason == reason
        # No receipt is known yet, so an operator has to send the money back.
        assert refund.state == "manual_required"


@pytest.mark.anyio
async def test_failed_prompt_shortens_the_reservation(repository: Any) -> None:
    order = make_order(uuid4())
    order.reservation_expires_at = _now() + timedelta(minutes=14)
    payment = make_payment(order)
    repository.payment = AsyncMock(return_value=payment)
    repository.order = AsyncMock(return_value=order)
    await PaymentService(
        cast(CommerceRepository, repository),
        settings(),
        Provider(status("cancelled", code="1032")),
    ).reconcile(payment.id)
    assert payment.state == "cancelled"
    assert order.reservation_expires_at < _now() + timedelta(minutes=6)
    assert added(repository, OutboxJob)[0].job_type == "order_expire"

    # Another open prompt keeps the original window.
    order.reservation_expires_at = original = _now() + timedelta(minutes=14)
    payment.state = "processing"
    repository.in_flight_payment = AsyncMock(return_value=make_payment(order))
    await PaymentService(
        cast(CommerceRepository, repository),
        settings(),
        Provider(status("cancelled", code="1032")),
    ).reconcile(payment.id)
    assert order.reservation_expires_at == original


@pytest.mark.anyio
async def test_expiry_waits_for_an_open_prompt(repository: Any) -> None:
    order = make_order(uuid4())
    order.reservation_expires_at = _now() - timedelta(seconds=1)
    open_payment = make_payment(order, "pending_customer")
    repository.order = AsyncMock(return_value=order)
    repository.in_flight_payment = AsyncMock(return_value=open_payment)
    await CheckoutService(cast(CommerceRepository, repository), settings()).expire(order.id)
    assert order.status == "pending_payment"
    jobs = added(repository, OutboxJob)
    assert {job.job_type for job in jobs} == {"order_expire", "payment_status_query"}

    repository.in_flight_payment = AsyncMock(return_value=None)
    listing = make_listing("0", "sold_out")
    repository.order_items = AsyncMock(return_value=[item(order, listing, "2")])
    repository.listing = AsyncMock(return_value=listing)
    cache = MagicMock(invalidate_listing=AsyncMock())
    await CheckoutService(cast(CommerceRepository, repository), settings(), cache).expire(order.id)
    assert order.status == "expired"
    assert listing.available_quantity == 2
    assert listing.status == "active"
    cache.invalidate_listing.assert_awaited_once_with(str(listing.id))


@pytest.mark.anyio
async def test_buyer_cancels_unpaid_order_and_releases_stock(repository: Any) -> None:
    user = buyer()
    order = make_order(user.id)
    listing = make_listing("0", "sold_out")
    repository.order = AsyncMock(return_value=order)
    repository.order_items = AsyncMock(return_value=[item(order, listing)])
    repository.listing = AsyncMock(return_value=listing)
    service = CheckoutService(cast(CommerceRepository, repository), settings())

    repository.in_flight_payment = AsyncMock(return_value=make_payment(order))
    with pytest.raises(ApiError) as busy:
        await service.cancel(user, order.id, None)
    assert busy.value.code == "payment_in_progress"

    repository.in_flight_payment = AsyncMock(return_value=None)
    cancelled = await service.cancel(user, order.id, "Changed my mind")
    assert cancelled.status == "cancelled"
    assert listing.available_quantity == 1
    assert added(repository, PaymentRefund) == []
    assert (await service.cancel(user, order.id, None)).status == "cancelled"

    with pytest.raises(ApiError) as hidden:
        await service.cancel(buyer(), order.id, None)
    assert hidden.value.code == "order_not_found"


@pytest.mark.anyio
async def test_cancelling_a_paid_order_refunds_it(repository: Any) -> None:
    user = buyer()
    order = make_order(user.id, "fulfilment")
    listing = make_listing("4")
    payment = make_payment(order, "succeeded", receipt="RCP1")
    part = Fulfilment(id=uuid4(), order_id=order.id, farmer_id=listing.farmer_id, version=1)
    part.status = "scheduled"
    repository.order = AsyncMock(return_value=order)
    repository.order_items = AsyncMock(return_value=[item(order, listing)])
    repository.listing = AsyncMock(return_value=listing)
    repository.order_fulfilments = AsyncMock(return_value=[part])
    repository.succeeded_payment = AsyncMock(return_value=payment)
    service = CheckoutService(cast(CommerceRepository, repository), settings())
    await service.cancel(user, order.id, None)
    assert order.status == "cancelled"
    assert part.status == "cancelled"
    refund = added(repository, PaymentRefund)[0]
    assert (refund.amount, refund.state) == (Decimal("125"), "pending")

    order.status = "fulfilment"
    part.status = "ready_for_handover"
    with pytest.raises(ApiError) as late:
        await service.cancel(user, order.id, None)
    assert late.value.code == "order_not_cancellable"
    order.status = "completed"
    with pytest.raises(ApiError) as done:
        await service.cancel(user, order.id, None)
    assert done.value.code == "order_not_cancellable"


@pytest.mark.anyio
async def test_checkout_rejects_totals_below_one_shilling(repository: Any) -> None:
    user = buyer()
    cart = Cart(id=uuid4(), buyer_id=user.id, status="active")
    listing = make_listing("10")
    listing.price_amount = Decimal("0.5")
    repository.existing_order = AsyncMock(return_value=None)
    repository.active_cart = AsyncMock(return_value=cart)
    repository.cart_items = AsyncMock(
        return_value=[
            CartItem(id=uuid4(), cart_id=cart.id, listing_id=listing.id, quantity=Decimal("1"))
        ]
    )
    repository.listing = AsyncMock(return_value=listing)
    with pytest.raises(ApiError) as small:
        await CheckoutService(cast(CommerceRepository, repository), settings()).checkout(
            user, "checkout-key", None
        )
    assert small.value.code == "order_total_too_small"


@pytest.mark.anyio
async def test_buyer_refresh_checks_payment_on_demand(repository: Any) -> None:
    user = buyer()
    order = make_order(user.id)
    payment = make_payment(order, "pending_customer")
    repository.payment = AsyncMock(return_value=payment)
    repository.order = AsyncMock(return_value=order)
    service = PaymentService(cast(CommerceRepository, repository), settings(), Provider(status()))
    refreshed = await service.refresh(user, payment.id)
    assert refreshed.state == "succeeded"
    assert order.status == "paid"

    with pytest.raises(ApiError) as hidden:
        await service.refresh(buyer(), payment.id)
    assert hidden.value.code == "payment_not_found"

    class Down(Provider):
        async def query_status(self, provider_request_ref: str) -> ProviderStatus:
            raise PaymentProviderError("offline")

    payment.state = "pending_customer"
    with pytest.raises(ApiError) as offline:
        await PaymentService(cast(CommerceRepository, repository), settings(), Down()).refresh(
            user, payment.id
        )
    assert offline.value.code == "payment_provider_unavailable"


@pytest.mark.anyio
async def test_initiation_failure_is_not_left_in_flight(repository: Any) -> None:
    user = buyer()
    order = make_order(user.id)
    repository.order = AsyncMock(return_value=order)
    repository.existing_payment = AsyncMock(return_value=None)

    class Refusing(Provider):
        async def initiate(self, request: InitiationRequest) -> InitiationResult:
            raise PaymentProviderError("down")

    from mavuno.commerce.schemas import PaymentInitiateRequest

    with pytest.raises(ApiError):
        await PaymentService(cast(CommerceRepository, repository), settings(), Refusing()).initiate(
            user,
            PaymentInitiateRequest(order_id=order.id, rail="mpesa", phone_e164="0712345678"),
            "payment-key",
        )
    assert added(repository, Payment)[0].state == "failed"


@pytest.mark.anyio
async def test_late_callback_records_receipt_on_query_confirmed_payment(repository: Any) -> None:
    order = make_order(uuid4(), "paid")
    payment = make_payment(order, "succeeded")
    repository.payment_by_request_ref = AsyncMock(return_value=payment)
    await PaymentService(
        cast(CommerceRepository, repository), settings(), Provider()
    ).accept_callback(TOKEN, {})
    assert payment.provider_transaction_ref == "RCP777"


@pytest.mark.anyio
async def test_refund_lifecycle_through_provider(repository: Any) -> None:
    order = make_order(uuid4(), "cancelled")
    payment = make_payment(order, "succeeded", receipt="RCP1")
    provider = Provider()
    service = RefundService(cast(CommerceRepository, repository), settings(), provider)
    refund = await service.request(
        payment, amount=Decimal("500"), reason="order_cancelled", dedupe_key="refund:1"
    )
    assert refund is not None and refund.amount == Decimal("125") and refund.state == "pending"

    repository.refund = AsyncMock(return_value=refund)
    repository.payment = AsyncMock(return_value=payment)
    await service.process(refund.id)
    assert refund.state == "submitted"
    assert refund.provider_ref == "conversation-1"
    assert provider.reversed == [("RCP1", Decimal("125"))]

    repository.refund_by_provider_ref = AsyncMock(return_value=refund)
    repository.order = AsyncMock(return_value=order)
    repository.order_refunds = AsyncMock(return_value=[refund])
    await service.reversal_result("conversation-1", True, "Reversed")
    assert refund.state == "completed"
    assert payment.state == "reversed"
    assert order.status == "refunded"
    await service.reversal_result("conversation-1", True, "Again")

    repository.refunded_total = AsyncMock(return_value=Decimal("125"))
    assert (
        await service.request(payment, amount=Decimal("1"), reason="x", dedupe_key="refund:2")
    ) is None


@pytest.mark.anyio
async def test_refunds_fall_back_to_an_operator(repository: Any) -> None:
    order = make_order(uuid4(), "cancelled")
    payment = make_payment(order, "succeeded", receipt="RCP1")
    service = RefundService(
        cast(CommerceRepository, repository),
        settings(),
        Provider(reversal=ReversalNotConfiguredError("no initiator")),
    )
    refund = await service.request(
        payment, amount=Decimal("125"), reason="order_cancelled", dedupe_key="r"
    )
    assert refund is not None
    repository.refund = AsyncMock(return_value=refund)
    repository.payment = AsyncMock(return_value=payment)
    await service.process(refund.id)
    assert refund.state == "manual_required"
    assert refund.operator_note == "no initiator"

    partial = await service.request(
        payment, amount=Decimal("60"), reason="fulfilment_cancelled", dedupe_key="p"
    )
    assert partial is not None and partial.state == "manual_required"
    assert "Partial refund" in (partial.operator_note or "")

    failed = PaymentRefund(
        id=uuid4(),
        payment_id=payment.id,
        order_id=order.id,
        amount=Decimal("125"),
        currency="KES",
        reason="x",
        state="submitted",
        dedupe_key="f",
    )
    repository.refund_by_provider_ref = AsyncMock(return_value=failed)
    repository.refund = AsyncMock(return_value=failed)
    await service.reversal_result("conversation-2", False, "Insufficient float")
    assert failed.state == "manual_required"

    repository.order = AsyncMock(return_value=order)
    repository.order_refunds = AsyncMock(return_value=[failed])
    done = await service.complete_manually(uuid4(), failed.id, "QWE123", None)
    assert done.state == "completed"
    assert order.status == "refunded"
    assert (await service.complete_manually(uuid4(), failed.id, "QWE123", None)) is failed

    repository.refund = AsyncMock(return_value=None)
    with pytest.raises(ApiError) as missing:
        await service.complete_manually(uuid4(), uuid4(), "QWE123", None)
    assert missing.value.code == "refund_not_found"


@pytest.mark.anyio
async def test_refund_without_receipt_is_manual_at_processing(repository: Any) -> None:
    order = make_order(uuid4(), "cancelled")
    payment = make_payment(order, "succeeded")
    refund = PaymentRefund(
        id=uuid4(),
        payment_id=payment.id,
        order_id=order.id,
        amount=Decimal("125"),
        currency="KES",
        reason="x",
        state="pending",
        dedupe_key="n",
    )
    repository.refund = AsyncMock(return_value=refund)
    repository.payment = AsyncMock(return_value=payment)
    await RefundService(cast(CommerceRepository, repository), settings(), Provider()).process(
        refund.id
    )
    assert refund.state == "manual_required"


@pytest.mark.anyio
async def test_reversal_webhook_checks_token_and_payload(repository: Any) -> None:
    service = PaymentService(cast(CommerceRepository, repository), settings(), Provider())
    with pytest.raises(ApiError) as hidden:
        await service.accept_reversal_result("wrong", {})
    assert hidden.value.code == "webhook_not_found"
    with pytest.raises(ApiError) as malformed:
        await service.accept_reversal_result(TOKEN, {"Result": {}})
    assert malformed.value.code == "malformed_payment_callback"
    repository.refund_by_provider_ref = AsyncMock(return_value=None)
    await service.accept_reversal_result(
        TOKEN, {"Result": {"ConversationID": "AG_1", "ResultCode": 0, "ResultDesc": "ok"}}
    )


def daraja_client(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url="https://sandbox.safaricom.co.ke", transport=httpx.MockTransport(handler)
    )


@pytest.mark.anyio
async def test_daraja_query_never_reads_an_accepted_query_as_payment() -> None:
    answers: list[httpx.Response] = [
        httpx.Response(200, json={"ResponseCode": "0", "ResponseDescription": "Accepted"}),
        httpx.Response(500, json={"errorCode": "500.001.1001", "errorMessage": "Being processed"}),
        httpx.Response(500, json={"errorCode": "500.003.02", "errorMessage": "Spike"}),
        httpx.Response(200, json={"ResponseCode": "0", "ResultCode": "1032"}),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/v1/generate":
            return httpx.Response(200, json={"access_token": "token"})
        return answers.pop(0)

    client = daraja_client(handler)
    provider = DarajaProvider(settings(), client)
    assert (await provider.query_status("checkout-1")).outcome == "pending"
    processing = await provider.query_status("checkout-1")
    assert (processing.outcome, processing.result_code) == ("pending", "500.001.1001")
    with pytest.raises(PaymentProviderError):
        await provider.query_status("checkout-1")
    assert (await provider.query_status("checkout-1")).outcome == "cancelled"
    await client.aclose()

    def broken(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/v1/generate":
            return httpx.Response(200, json={"access_token": "token"})
        return httpx.Response(200, content=b"[]")

    client = daraja_client(broken)
    with pytest.raises(PaymentProviderError):
        await DarajaProvider(settings(), client).query_status("checkout-1")
    await client.aclose()


def test_daraja_callback_keeps_settlement_facts_and_masks_phone() -> None:
    provider = DarajaProvider(settings(), httpx.AsyncClient())
    event = provider.parse_callback(
        {
            "Body": {
                "stkCallback": {
                    "MerchantRequestID": "m-1",
                    "CheckoutRequestID": "checkout-1",
                    "ResultCode": 0,
                    "ResultDesc": "Processed",
                    "CallbackMetadata": {
                        "Item": [
                            {"Name": "Amount", "Value": 125.0},
                            {"Name": "MpesaReceiptNumber", "Value": "NLJ7RT61SV"},
                            {"Name": "Balance"},
                            {"Name": "TransactionDate", "Value": 20260929102115},
                            {"Name": "PhoneNumber", "Value": 254712345678},
                            "junk",
                        ]
                    },
                }
            }
        }
    )
    assert event.amount == Decimal("125.0")
    assert event.transaction_ref == "NLJ7RT61SV"
    assert event.payer_phone_e164 == "+254712345678"
    assert event.redacted_payload["PhoneNumberMasked"] == "+25471***678"
    assert "254712345678" not in str(event.redacted_payload)

    cancelled = provider.parse_callback(
        {"Body": {"stkCallback": {"CheckoutRequestID": "c", "ResultCode": 1032}}}
    )
    assert cancelled.amount is None and cancelled.outcome_hint == "cancelled"
    assert DarajaProvider._callback_metadata({"Item": "x"}) == {}
    assert DarajaProvider._decimal("abc") is None
    assert DarajaProvider._decimal(True) is None
    assert DarajaProvider._mask_phone(None) is None
    assert DarajaProvider._mask_phone("+2547") == "***"


@pytest.mark.anyio
async def test_daraja_reversal_request_and_result() -> None:
    bodies: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/v1/generate":
            return httpx.Response(200, json={"access_token": "token"})
        bodies.append(request.content)
        return httpx.Response(200, json={"ResponseCode": "0", "ConversationID": "AG_1"})

    with pytest.raises(ReversalNotConfiguredError):
        await DarajaProvider(settings(), httpx.AsyncClient()).reverse("RCP", Decimal("1"), "x")

    configured = settings(
        daraja_initiator_name="apiop", daraja_security_credential=SecretStr("encrypted")
    )
    client = daraja_client(handler)
    provider = DarajaProvider(configured, client)
    result = await provider.reverse("RCP1", Decimal("125"), "Mavuno order_cancelled")
    assert result == ReversalResult("AG_1", True)
    assert b'"TransactionID":"RCP1"' in bodies[0].replace(b" ", b"")
    assert b"daraja-reversal" in bodies[0]
    with pytest.raises(PaymentProviderError):
        await provider.reverse("RCP1", Decimal("1.5"), "x")
    await client.aclose()

    client = daraja_client(
        lambda request: (
            httpx.Response(200, json={"access_token": "token"})
            if request.url.path == "/oauth/v1/generate"
            else httpx.Response(200, json={"ResponseCode": "0"})
        )
    )
    with pytest.raises(PaymentProviderError, match="reversal reference"):
        await DarajaProvider(configured, client).reverse("RCP1", Decimal("125"), "x")
    await client.aclose()

    assert DarajaProvider.parse_reversal_result(
        {"Result": {"OriginatorConversationID": "O1", "ResultCode": "2001", "ResultDesc": "No"}}
    ) == ("O1", False, "No")
    with pytest.raises(PaymentProviderError):
        DarajaProvider.parse_reversal_result({})
