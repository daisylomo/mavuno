"""Returning money to buyers.

A refund is always recorded first, in the same transaction as the event that makes it owed
(a cancellation, a late payment for stock that has gone, or a duplicate payment). The worker
then asks M-PESA to reverse the transaction. When automatic reversal is not possible — no
reversal credential is configured, the receipt number is unknown, or only part of the payment
is owed — the refund is marked ``manual_required`` so an operator can send the money and
record the reference.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from mavuno.api.errors import ApiError
from mavuno.commerce.repository import CommerceRepository
from mavuno.core.config import Settings
from mavuno.db.models import Order, OrderStatusHistory, OutboxJob, Payment, PaymentRefund
from mavuno.payments.daraja import DarajaProvider
from mavuno.payments.provider import PaymentProvider, ReversalNotConfiguredError

OPEN_REFUND_STATES = ("pending", "submitted", "manual_required")


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class RefundService:
    def __init__(
        self,
        repository: CommerceRepository,
        settings: Settings,
        provider: PaymentProvider | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.provider = provider

    async def request(
        self,
        payment: Payment,
        *,
        amount: Decimal,
        reason: str,
        dedupe_key: str,
        farmer_id: UUID | None = None,
    ) -> PaymentRefund | None:
        """Record money owed to the buyer and queue its reversal. Does not commit."""
        remaining = payment.amount - await self.repository.refunded_total(payment.id)
        amount = min(amount, remaining)
        if amount <= 0:
            return None
        automatic = (
            payment.rail == "mpesa"
            and payment.provider_transaction_ref is not None
            and amount == payment.amount
        )
        refund = PaymentRefund(
            id=uuid4(),
            payment_id=payment.id,
            order_id=payment.order_id,
            farmer_id=farmer_id,
            amount=amount,
            currency=payment.currency,
            reason=reason[:64],
            state="pending" if automatic else "manual_required",
            dedupe_key=dedupe_key[:160],
            operator_note=None if automatic else self._manual_reason(payment, amount),
        )
        self.repository.add(refund)
        if automatic:
            self.repository.add(
                OutboxJob(
                    id=uuid4(),
                    job_type="payment_refund",
                    dedupe_key=f"payment-refund:{refund.id}",
                    payload={"refund_id": str(refund.id)},
                    status="pending",
                    attempts=0,
                    max_attempts=max(1, self.settings.daraja_retry_limit),
                    available_at=_now(),
                )
            )
        return refund

    async def process(self, refund_id: UUID) -> None:
        """Worker step: ask the provider to reverse a pending refund."""
        refund = await self.repository.refund(refund_id, lock=True)
        if refund is None or refund.state != "pending":
            return
        payment = await self.repository.payment(refund.payment_id)
        if payment is None or payment.provider_transaction_ref is None:
            refund.state = "manual_required"
            refund.operator_note = "The M-PESA receipt number is unknown; refund manually."
            await self.repository.commit()
            return
        provider = self.provider or DarajaProvider(self.settings)
        try:
            result = await provider.reverse(
                payment.provider_transaction_ref, refund.amount, f"Mavuno {refund.reason}"
            )
        except ReversalNotConfiguredError as exc:
            refund.state = "manual_required"
            refund.operator_note = str(exc)[:255]
            await self.repository.commit()
            return
        finally:
            if self.provider is None and isinstance(provider, DarajaProvider):
                await provider.aclose()
        refund.provider_ref = result.provider_ref
        refund.state = "submitted" if result.accepted else "manual_required"
        if not result.accepted:
            refund.operator_note = "M-PESA did not accept the reversal request."
        await self.repository.commit()

    async def reversal_result(self, provider_ref: str, succeeded: bool, description: str) -> None:
        refund = await self.repository.refund_by_provider_ref(provider_ref)
        if refund is None or refund.state in {"completed", "failed"}:
            return
        refund = await self.repository.refund(refund.id, lock=True)
        assert refund is not None
        if succeeded:
            await self._complete(refund, actor_user_id=None, note=description)
        else:
            refund.state = "manual_required"
            refund.operator_note = f"Reversal failed: {description}"[:255]
        await self.repository.commit()

    async def complete_manually(
        self, actor_user_id: UUID, refund_id: UUID, reference: str, note: str | None
    ) -> PaymentRefund:
        refund = await self.repository.refund(refund_id, lock=True)
        if refund is None:
            raise ApiError(status_code=404, code="refund_not_found", message="Refund was not found")
        if refund.state == "completed":
            return refund
        if refund.state not in OPEN_REFUND_STATES and refund.state != "failed":
            raise ApiError(
                status_code=409, code="refund_not_open", message="Refund cannot be completed"
            )
        refund.provider_ref = refund.provider_ref or reference[:128]
        await self._complete(
            refund, actor_user_id=actor_user_id, note=note or f"Sent manually: {reference}"
        )
        await self.repository.commit()
        await self.repository.refresh(refund)
        return refund

    async def _complete(
        self, refund: PaymentRefund, *, actor_user_id: UUID | None, note: str | None
    ) -> None:
        refund.state = "completed"
        refund.completed_at = _now()
        if note:
            refund.operator_note = note[:255]
        payment = await self.repository.payment(refund.payment_id, lock=True)
        if payment is None:
            raise RuntimeError("Refunded payment is missing")
        if await self._fully_refunded(payment, refund):
            payment.state = "reversed"
            order = await self.repository.order(payment.order_id, lock=True)
            if order is not None and order.status == "cancelled":
                self._mark_refunded(order, actor_user_id)

    async def _fully_refunded(self, payment: Payment, refund: PaymentRefund) -> bool:
        completed = sum(
            (
                value.amount
                for value in await self.repository.order_refunds(payment.order_id)
                if value.payment_id == payment.id
                and (value.state == "completed" or value.id == refund.id)
            ),
            Decimal("0"),
        )
        return completed >= payment.amount

    def _mark_refunded(self, order: Order, actor_user_id: UUID | None) -> None:
        previous = order.status
        order.status = "refunded"
        order.version += 1
        self.repository.add(
            OrderStatusHistory(
                id=uuid4(),
                order_id=order.id,
                actor_user_id=actor_user_id,
                previous_status=previous,
                new_status="refunded",
                reason="Payment returned to the buyer",
            )
        )

    @staticmethod
    def _manual_reason(payment: Payment, amount: Decimal) -> str:
        if payment.rail != "mpesa":
            return "Bank refunds are sent by an operator."
        if payment.provider_transaction_ref is None:
            return "The M-PESA receipt number is unknown; refund manually."
        return f"Partial refund of KES {amount:.0f}: send by M-PESA and record the reference."
