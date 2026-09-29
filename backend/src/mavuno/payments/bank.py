from __future__ import annotations

from decimal import Decimal

from mavuno.payments.provider import (
    CallbackEvent,
    InitiationRequest,
    InitiationResult,
    PaymentProviderError,
    ProviderStatus,
)


class UnconfiguredBankProvider:
    """Fail-closed seam until a regulated Kenyan bank/payment partner is selected."""

    name = "bank"

    async def initiate(self, request: InitiationRequest) -> InitiationResult:
        raise PaymentProviderError("Bank payment provider has not been selected")

    def parse_callback(self, payload: dict[str, object]) -> CallbackEvent:
        raise PaymentProviderError("Bank payment provider has not been selected")

    async def query_status(self, provider_request_ref: str) -> ProviderStatus:
        raise PaymentProviderError("Bank payment provider has not been selected")

    async def reverse(self, transaction_ref: str, amount: Decimal, reason: str) -> str:
        raise PaymentProviderError("Bank payment provider has not been selected")
