from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol

PaymentOutcome = Literal["pending", "succeeded", "failed", "cancelled", "expired", "reversed"]


class PaymentProviderError(Exception):
    """A safe provider error that contains no credentials or raw payload."""


class ReversalNotConfiguredError(PaymentProviderError):
    """Automatic reversal is unavailable; an operator must return the money."""


@dataclass(frozen=True, slots=True)
class InitiationRequest:
    amount: Decimal
    currency: str
    phone_e164: str
    account_reference: str
    description: str


@dataclass(frozen=True, slots=True)
class InitiationResult:
    provider_request_ref: str
    provider_conversation_ref: str | None
    outcome: PaymentOutcome
    response_code: str


@dataclass(frozen=True, slots=True)
class CallbackEvent:
    provider_event_ref: str
    provider_request_ref: str
    outcome_hint: PaymentOutcome
    authenticated: bool
    redacted_payload: dict[str, object]
    # Settlement details a successful STK callback carries. The status query that confirms the
    # payment does not return them, so reconciliation reads them from the callback.
    amount: Decimal | None = None
    transaction_ref: str | None = None
    payer_phone_e164: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderStatus:
    provider_request_ref: str
    outcome: PaymentOutcome
    amount: Decimal | None
    currency: str
    payer_phone_e164: str | None
    merchant_account: str | None
    transaction_ref: str | None
    result_code: str
    result_description: str


@dataclass(frozen=True, slots=True)
class ReversalResult:
    provider_ref: str
    accepted: bool


class PaymentProvider(Protocol):
    name: str

    async def initiate(self, request: InitiationRequest) -> InitiationResult: ...

    def parse_callback(self, payload: dict[str, object]) -> CallbackEvent: ...

    async def query_status(self, provider_request_ref: str) -> ProviderStatus: ...

    async def reverse(
        self, transaction_ref: str, amount: Decimal, reason: str
    ) -> ReversalResult: ...
