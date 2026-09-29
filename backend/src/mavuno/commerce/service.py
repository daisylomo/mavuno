from __future__ import annotations

import hmac
from collections.abc import Iterable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import ROUND_FLOOR, Decimal
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from mavuno.api.errors import ApiError
from mavuno.auth.context import AuthenticatedUser
from mavuno.auth.normalization import normalize_phone
from mavuno.commerce import inventory
from mavuno.commerce.refunds import RefundService
from mavuno.commerce.repository import CommerceRepository
from mavuno.commerce.schemas import (
    CartItemResponse,
    CartResponse,
    OrderItemResponse,
    OrderResponse,
    PaymentInitiateRequest,
    RefundResponse,
)
from mavuno.core.config import Settings
from mavuno.core.performance import CatalogCache
from mavuno.db.models import (
    Cart,
    CartItem,
    InventoryMovement,
    Listing,
    Order,
    OrderItem,
    OrderStatusHistory,
    OutboxJob,
    Payment,
    PaymentEvent,
    PaymentReconciliation,
)
from mavuno.payments.bank import UnconfiguredBankProvider
from mavuno.payments.daraja import DarajaProvider
from mavuno.payments.provider import (
    InitiationRequest,
    PaymentProvider,
    PaymentProviderError,
    ProviderStatus,
)

FINAL_PAYMENT_STATES = frozenset({"succeeded", "reversed"})
# Fulfilment states in which a buyer can still call the whole order off.
CANCELLABLE_FULFILMENT_STATES = frozenset({"pending", "scheduled", "cancelled"})


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def payable_total(subtotal: Decimal) -> Decimal:
    """The amount charged for an order.

    M-PESA only accepts whole shillings. Fractional quantities (1.5 kg) or prices can produce a
    fractional subtotal, so the charge is rounded *down*: a buyer never pays more than the
    listed prices, and the difference is under one shilling.
    """
    return subtotal.quantize(Decimal("1"), rounding=ROUND_FLOOR)


class CartService:
    def __init__(self, repository: CommerceRepository) -> None:
        self.repository = repository

    async def get(self, user: AuthenticatedUser) -> CartResponse:
        self._buyer(user)
        cart = await self._cart(user.id)
        return await self._response(cart)

    async def upsert(
        self, user: AuthenticatedUser, listing_id: UUID, quantity: Decimal
    ) -> CartResponse:
        self._buyer(user)
        cart = await self._cart(user.id)
        listing = await self.repository.listing(listing_id)
        if listing is None or listing.status != "active":
            raise ApiError(
                status_code=404, code="listing_not_found", message="Listing was not found"
            )
        if quantity > listing.available_quantity:
            raise ApiError(
                status_code=409,
                code="insufficient_inventory",
                message="Requested quantity is unavailable",
            )
        item = await self.repository.cart_item(cart.id, listing_id)
        if item is None:
            item = CartItem(id=uuid4(), cart_id=cart.id, listing_id=listing_id, quantity=quantity)
            self.repository.add(item)
        else:
            item.quantity = quantity
        await self.repository.commit()
        return await self._response(cart)

    async def remove(self, user: AuthenticatedUser, listing_id: UUID) -> None:
        self._buyer(user)
        cart = await self.repository.active_cart(user.id)
        if cart is None:
            return
        item = await self.repository.cart_item(cart.id, listing_id)
        if item is not None:
            await self.repository.delete_cart_item(item)
            await self.repository.commit()

    async def _cart(self, buyer_id: UUID) -> Cart:
        # Serialize cart creation on the buyer row so concurrent first requests cannot
        # create multiple active carts. Converted carts remain as immutable history.
        await self.repository.lock_user(buyer_id)
        cart = await self.repository.active_cart(buyer_id)
        if cart is None:
            cart = Cart(id=uuid4(), buyer_id=buyer_id, status="active")
            self.repository.add(cart)
            await self.repository.commit()
            await self.repository.refresh(cart)
        return cart

    async def _response(self, cart: Cart) -> CartResponse:
        responses: list[CartItemResponse] = []
        subtotal = Decimal("0")
        for item in await self.repository.cart_items(cart.id):
            listing = await self.repository.listing(item.listing_id)
            if listing is None or listing.status == "archived":
                continue
            line_total = listing.price_amount * item.quantity
            subtotal += line_total
            responses.append(
                CartItemResponse(
                    listing_id=listing.id,
                    title=listing.title,
                    quantity=item.quantity,
                    quantity_unit=listing.quantity_unit,
                    unit_price=listing.price_amount,
                    line_total=line_total,
                    available_quantity=listing.available_quantity,
                )
            )
        return CartResponse(id=cart.id, items=responses, subtotal_amount=subtotal)

    @staticmethod
    def _buyer(user: AuthenticatedUser) -> None:
        if "buyer" not in user.roles:
            raise ApiError(
                status_code=403, code="buyer_role_required", message="The buyer role is required"
            )


class CheckoutService:
    def __init__(
        self,
        repository: CommerceRepository,
        settings: Settings,
        catalog_cache: CatalogCache | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.catalog_cache = catalog_cache

    async def checkout(
        self, user: AuthenticatedUser, idempotency_key: str, delivery_address_id: UUID | None
    ) -> OrderResponse:
        CartService._buyer(user)
        existing = await self.repository.existing_order(user.id, idempotency_key)
        if existing is not None:
            return await self.response(existing)
        if (
            delivery_address_id is not None
            and await self.repository.address(delivery_address_id, user.id) is None
        ):
            raise ApiError(
                status_code=404,
                code="address_not_found",
                message="Delivery address was not found",
            )
        cart = await self.repository.active_cart(user.id, lock=True)
        if cart is None:
            raise ApiError(status_code=409, code="cart_empty", message="Cart is empty")
        items = await self.repository.cart_items(cart.id)
        if not items:
            raise ApiError(status_code=409, code="cart_empty", message="Cart is empty")

        locked: dict[UUID, Listing] = {}
        for item in sorted(items, key=lambda value: value.listing_id.bytes):
            listing = await self.repository.listing(item.listing_id, lock=True)
            if (
                listing is None
                or listing.status != "active"
                or listing.available_quantity < item.quantity
            ):
                await self.repository.rollback()
                raise ApiError(
                    status_code=409,
                    code="inventory_changed",
                    message="Cart inventory is no longer available",
                )
            locked[item.listing_id] = listing

        expected_subtotal = sum(
            (locked[item.listing_id].price_amount * item.quantity for item in items),
            Decimal("0"),
        )
        if payable_total(expected_subtotal) < 1:
            await self.repository.rollback()
            raise ApiError(
                status_code=409,
                code="order_total_too_small",
                message="M-PESA payments must be at least KES 1",
            )

        order = Order(
            id=uuid4(),
            buyer_id=user.id,
            status="pending_payment",
            currency="KES",
            subtotal_amount=Decimal("0"),
            total_amount=Decimal("0"),
            idempotency_key=idempotency_key,
            delivery_address_id=delivery_address_id,
            reservation_expires_at=_now()
            + timedelta(minutes=self.settings.order_reservation_minutes),
            version=1,
        )
        self.repository.add(order)
        await self.repository.flush()
        subtotal = Decimal("0")
        for cart_item in items:
            listing = locked[cart_item.listing_id]
            product = await self.repository.product(listing.product_id)
            if product is None:
                raise RuntimeError("Listing product is missing")
            line_total = listing.price_amount * cart_item.quantity
            subtotal += line_total
            self.repository.add(
                OrderItem(
                    id=uuid4(),
                    order_id=order.id,
                    listing_id=listing.id,
                    farmer_id=listing.farmer_id,
                    product_name=product.name,
                    listing_title=listing.title,
                    quantity=cart_item.quantity,
                    quantity_unit=listing.quantity_unit,
                    unit_price=listing.price_amount,
                    line_total=line_total,
                )
            )
            listing.available_quantity -= cart_item.quantity
            listing.version += 1
            if listing.available_quantity == 0:
                listing.status = "sold_out"
            self.repository.add(
                InventoryMovement(
                    id=uuid4(),
                    listing_id=listing.id,
                    actor_user_id=user.id,
                    movement_type="reservation",
                    quantity_delta=-cart_item.quantity,
                    resulting_quantity=listing.available_quantity,
                    reason="Checkout reservation",
                    reference_type="order",
                    reference_id=order.id,
                )
            )
        order.subtotal_amount = subtotal
        order.total_amount = payable_total(subtotal)
        self.repository.add(
            OrderStatusHistory(
                id=uuid4(),
                order_id=order.id,
                actor_user_id=user.id,
                previous_status=None,
                new_status="pending_payment",
                reason="Checkout created",
            )
        )
        self.repository.add(self._expiry_job(order, f"order-expire:{order.id}"))
        cart.status = "converted"
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            existing = await self.repository.existing_order(user.id, idempotency_key)
            if existing is not None:
                return await self.response(existing)
            raise ApiError(
                status_code=409, code="checkout_conflict", message="Checkout could not be completed"
            ) from exc
        await self.repository.refresh(order)
        await self._invalidate_listings(locked)
        return await self.response(order)

    async def get(self, user: AuthenticatedUser, order_id: UUID) -> OrderResponse:
        order = await self.repository.order(order_id)
        if order is None or order.buyer_id != user.id:
            raise ApiError(status_code=404, code="order_not_found", message="Order was not found")
        return await self.response(order)

    async def response(self, order: Order) -> OrderResponse:
        items = await self.repository.order_items(order.id)
        refunds = await self.repository.order_refunds(order.id)
        return OrderResponse(
            id=order.id,
            buyer_id=order.buyer_id,
            status=order.status,
            currency=order.currency,
            subtotal_amount=order.subtotal_amount,
            total_amount=order.total_amount,
            reservation_expires_at=order.reservation_expires_at,
            paid_at=order.paid_at,
            created_at=order.created_at,
            items=[
                OrderItemResponse(
                    listing_id=item.listing_id,
                    farmer_id=item.farmer_id,
                    product_name=item.product_name,
                    listing_title=item.listing_title,
                    quantity=item.quantity,
                    quantity_unit=item.quantity_unit,
                    unit_price=item.unit_price,
                    line_total=item.line_total,
                )
                for item in items
            ],
            refunds=[RefundResponse.model_validate(refund) for refund in refunds],
        )

    async def expire(self, order_id: UUID) -> None:
        order = await self.repository.order(order_id, lock=True)
        now = _now()
        if order is None or order.status != "pending_payment" or order.reservation_expires_at > now:
            return
        in_flight = await self.repository.in_flight_payment(
            order.id, since=now - timedelta(seconds=self.settings.payment_inflight_grace_seconds)
        )
        if in_flight is not None:
            # The buyer may be typing their M-PESA PIN right now. Hold the stock a little longer
            # and check the payment, instead of releasing stock that is about to be paid for.
            assert in_flight.created_at is not None
            retry_at = in_flight.created_at + timedelta(
                seconds=self.settings.payment_inflight_grace_seconds
            )
            self.repository.add(
                self._expiry_job(
                    order, f"order-expire:{order.id}:{in_flight.id}", available_at=retry_at
                )
            )
            self.repository.add(
                PaymentService.status_query_job(
                    in_flight.id, f"payment-query:{in_flight.id}:expiry", now, self.settings
                )
            )
            await self.repository.commit()
            return
        items = await self.repository.order_items(order.id)
        changed = await inventory.release(
            self.repository,
            items,
            order_id=order.id,
            actor_user_id=order.buyer_id,
            reason="Payment reservation expired",
        )
        self._set_status(order, "expired", None, "Payment reservation expired")
        await self.repository.commit()
        await self._invalidate_listings(changed)

    async def cancel(self, user: AuthenticatedUser, order_id: UUID, reason: str | None) -> Order:
        """Buyer calls off an order before any farmer has handed anything over."""
        order = await self.repository.order(order_id, lock=True)
        if order is None or (order.buyer_id != user.id and not user.has_role("administrator")):
            raise ApiError(status_code=404, code="order_not_found", message="Order was not found")
        if order.status in {"cancelled", "expired", "refunded"}:
            return order
        now = _now()
        if order.status == "pending_payment":
            if await self.repository.in_flight_payment(
                order.id,
                since=now - timedelta(seconds=self.settings.payment_inflight_grace_seconds),
            ):
                raise ApiError(
                    status_code=409,
                    code="payment_in_progress",
                    message="An M-PESA prompt is still open. Wait for it to finish or expire.",
                )
        elif order.status in {"paid", "fulfilment"}:
            parts = await self.repository.order_fulfilments(order.id, lock=True)
            if any(part.status not in CANCELLABLE_FULFILMENT_STATES for part in parts):
                raise ApiError(
                    status_code=409,
                    code="order_not_cancellable",
                    message="A farmer has already prepared or handed over part of this order",
                )
            for part in parts:
                part.status = "cancelled"
                part.version += 1
        else:
            raise ApiError(
                status_code=409,
                code="order_not_cancellable",
                message="Completed orders cannot be cancelled",
            )
        previous = order.status
        items = await self.repository.order_items(order.id)
        changed = await inventory.release(
            self.repository,
            items,
            order_id=order.id,
            actor_user_id=user.id,
            reason="Order cancelled by buyer",
        )
        self._set_status(order, "cancelled", user.id, reason or "Cancelled by buyer")
        if previous != "pending_payment":
            payment = await self.repository.succeeded_payment(order.id)
            if payment is not None:
                await RefundService(self.repository, self.settings).request(
                    payment,
                    amount=payment.amount,
                    reason="order_cancelled",
                    dedupe_key=f"refund:{order.id}:cancel",
                )
        await self.repository.commit()
        await self.repository.refresh(order)
        await self._invalidate_listings(changed)
        return order

    def _set_status(
        self, order: Order, status: str, actor_user_id: UUID | None, reason: str
    ) -> None:
        previous = order.status
        order.status = status
        order.version += 1
        self.repository.add(
            OrderStatusHistory(
                id=uuid4(),
                order_id=order.id,
                actor_user_id=actor_user_id,
                previous_status=previous,
                new_status=status,
                reason=reason[:255],
            )
        )

    @staticmethod
    def _expiry_job(
        order: Order, dedupe_key: str, available_at: datetime | None = None
    ) -> OutboxJob:
        return OutboxJob(
            id=uuid4(),
            job_type="order_expire",
            dedupe_key=dedupe_key[:160],
            payload={"order_id": str(order.id)},
            status="pending",
            attempts=0,
            max_attempts=3,
            available_at=available_at or order.reservation_expires_at,
        )

    async def _invalidate_listings(self, listing_ids: Iterable[UUID]) -> None:
        if self.catalog_cache is None:
            return
        for listing_id in listing_ids:
            await self.catalog_cache.invalidate_listing(str(listing_id))


class PaymentService:
    def __init__(
        self,
        repository: CommerceRepository,
        settings: Settings,
        provider: PaymentProvider | None = None,
        catalog_cache: CatalogCache | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.provider = provider
        self.catalog_cache = catalog_cache

    def provider_for(self, rail: str) -> PaymentProvider:
        if self.provider is not None:
            return self.provider
        if rail == "mpesa":
            return DarajaProvider(self.settings)
        return UnconfiguredBankProvider()

    @staticmethod
    def status_query_job(
        payment_id: UUID, dedupe_key: str, available_at: datetime, settings: Settings
    ) -> OutboxJob:
        return OutboxJob(
            id=uuid4(),
            job_type="payment_status_query",
            dedupe_key=dedupe_key[:160],
            payload={"payment_id": str(payment_id)},
            status="pending",
            attempts=0,
            max_attempts=max(1, settings.daraja_retry_limit),
            available_at=available_at,
        )

    async def initiate(
        self, user: AuthenticatedUser, payload: PaymentInitiateRequest, idempotency_key: str
    ) -> Payment:
        if not self.settings.payments_enabled:
            raise ApiError(
                status_code=503,
                code="payments_disabled",
                message="Payments are temporarily unavailable",
            )
        order = await self.repository.order(payload.order_id)
        if order is None or order.buyer_id != user.id:
            raise ApiError(status_code=404, code="order_not_found", message="Order was not found")
        if order.status != "pending_payment" or order.reservation_expires_at <= _now():
            raise ApiError(
                status_code=409, code="order_not_payable", message="Order cannot be paid"
            )
        existing = await self.repository.existing_payment(order.id, idempotency_key)
        if existing is not None and existing.provider_request_ref:
            return existing
        phone = None
        if payload.rail == "mpesa":
            if payload.phone_e164 is None:
                raise ApiError(
                    status_code=422,
                    code="phone_required",
                    message="Phone number is required for M-PESA",
                )
            try:
                phone = normalize_phone(payload.phone_e164)
            except ValueError as exc:
                raise ApiError(
                    status_code=422, code="invalid_phone", message="Phone number is invalid"
                ) from exc
        payment = existing or Payment(
            id=uuid4(),
            order_id=order.id,
            rail=payload.rail,
            provider="daraja" if payload.rail == "mpesa" else "bank",
            amount=order.total_amount,
            currency=order.currency,
            state="created",
            idempotency_key=idempotency_key,
            payer_phone_e164=phone,
            account_reference=f"MVN{str(order.id).replace('-', '')[:12]}",
        )
        if existing is None:
            self.repository.add(payment)
            await self.repository.commit()
            await self.repository.refresh(payment)
        provider: PaymentProvider | None = None
        try:
            provider = self.provider_for(payload.rail)
            result = await provider.initiate(request=self._initiation_request(payment))
        except PaymentProviderError as exc:
            payment.state = "failed"
            payment.failure_code = "provider_unavailable"
            payment.failure_message = str(exc)[:255]
            await self.repository.commit()
            raise ApiError(
                status_code=503,
                code="payment_provider_unavailable",
                message="Payment provider is unavailable",
            ) from exc
        finally:
            await self._close_provider(provider)
        payment.provider_request_ref = result.provider_request_ref
        payment.state = "pending_customer"
        payment.failure_code = None
        payment.failure_message = None
        now = _now()
        # Callbacks can be lost, and a sleeping host may miss them, so the payment is also
        # checked on a schedule while the prompt is open.
        for offset in (30, 75, 150):
            self.repository.add(
                self.status_query_job(
                    payment.id,
                    f"payment-query:{payment.id}:{offset}",
                    now + timedelta(seconds=offset),
                    self.settings,
                )
            )
        await self.repository.commit()
        await self.repository.refresh(payment)
        return payment

    async def refresh(self, user: AuthenticatedUser, payment_id: UUID) -> Payment:
        """Buyer-triggered status check, so the app never depends on the worker being awake."""
        payment = await self.repository.payment(payment_id)
        order = None if payment is None else await self.repository.order(payment.order_id)
        if payment is None or order is None or order.buyer_id != user.id:
            raise ApiError(
                status_code=404, code="payment_not_found", message="Payment was not found"
            )
        if (
            self.settings.payments_enabled
            and payment.provider_request_ref is not None
            and payment.state in {"pending_customer", "processing"}
        ):
            try:
                await self.reconcile(payment.id)
            except PaymentProviderError as exc:
                await self.repository.rollback()
                raise ApiError(
                    status_code=503,
                    code="payment_provider_unavailable",
                    message="M-PESA could not be reached. Try again shortly.",
                ) from exc
        refreshed = await self.repository.payment(payment_id)
        assert refreshed is not None
        await self.repository.refresh(refreshed)
        return refreshed

    async def accept_callback(self, token: str, payload: dict[str, object]) -> None:
        self._check_token(token)
        provider: PaymentProvider | None = None
        try:
            provider = self.provider_for("mpesa")
            event = provider.parse_callback(payload)
        except PaymentProviderError as exc:
            raise ApiError(
                status_code=422, code="malformed_payment_callback", message="Callback is malformed"
            ) from exc
        finally:
            await self._close_provider(provider)
        assert provider is not None
        payment = await self.repository.payment_by_request_ref(
            provider.name, event.provider_request_ref
        )
        if payment is None:
            raise ApiError(
                status_code=202,
                code="payment_callback_unmatched",
                message="Callback accepted for reconciliation",
            )
        if (
            payment.state == "succeeded"
            and payment.provider_transaction_ref is None
            and event.transaction_ref is not None
        ):
            # Confirmed earlier by the status query alone; record the receipt now.
            payment.provider_transaction_ref = event.transaction_ref
        self.repository.add(
            PaymentEvent(
                id=uuid4(),
                payment_id=payment.id,
                provider=provider.name,
                provider_event_ref=event.provider_event_ref,
                direction="callback",
                event_type=event.outcome_hint,
                payload_redacted=event.redacted_payload,
                processing_state="queued",
            )
        )
        self.repository.add(
            self.status_query_job(
                payment.id,
                f"payment-callback:{event.provider_event_ref}",
                _now(),
                self.settings,
            )
        )
        try:
            await self.repository.commit()
        except IntegrityError:
            await self.repository.rollback()

    async def accept_reversal_result(self, token: str, payload: dict[str, object]) -> None:
        self._check_token(token)
        try:
            reference, succeeded, description = DarajaProvider.parse_reversal_result(payload)
        except PaymentProviderError as exc:
            raise ApiError(
                status_code=422, code="malformed_payment_callback", message="Callback is malformed"
            ) from exc
        await RefundService(self.repository, self.settings).reversal_result(
            reference, succeeded, description
        )

    async def reconcile(self, payment_id: UUID) -> None:
        payment = await self.repository.payment(payment_id)
        if (
            payment is None
            or payment.provider_request_ref is None
            or payment.state in FINAL_PAYMENT_STATES
        ):
            return
        provider: PaymentProvider | None = None
        try:
            provider = self.provider_for(payment.rail)
            status = await provider.query_status(payment.provider_request_ref)
        finally:
            await self._close_provider(provider)
        payment = await self.repository.payment(payment_id, lock=True)
        if payment is None or payment.state in FINAL_PAYMENT_STATES:
            return
        if status.outcome == "succeeded":
            status = await self._with_callback_evidence(payment, status)
        discrepancy = self._discrepancy(payment, status)
        self.repository.add(
            PaymentReconciliation(
                id=uuid4(),
                payment_id=payment.id,
                expected_amount=payment.amount,
                reported_amount=status.amount,
                currency=status.currency,
                provider_settlement_ref=status.transaction_ref,
                state=self._reconciliation_state(status, discrepancy),
                discrepancy_reason=discrepancy,
            )
        )
        changed: set[UUID] = set()
        if status.outcome == "succeeded" and discrepancy is None:
            payment.state = "succeeded"
            payment.provider_transaction_ref = status.transaction_ref
            payment.failure_code = None
            payment.failure_message = None
            changed = await self._settle(payment)
        elif status.outcome in {"failed", "cancelled", "expired", "reversed"}:
            payment.state = status.outcome
            payment.failure_code = status.result_code
            payment.failure_message = status.result_description
            await self._shorten_reservation(payment)
        elif status.outcome == "succeeded":
            payment.state = "processing"
            payment.failure_code = "reconciliation_discrepancy"
            payment.failure_message = discrepancy
        else:
            payment.state = "processing"
        await self.repository.commit()
        await self._invalidate_listings(changed)

    async def _with_callback_evidence(
        self, payment: Payment, status: ProviderStatus
    ) -> ProviderStatus:
        """Fill in what Daraja's status query leaves out from the STK callback.

        The query confirms that *this* STK request, whose amount the merchant set, completed.
        It does not return the amount or the M-PESA receipt; the success callback does.
        """
        if status.amount is not None and status.transaction_ref is not None:
            return status
        event = await self.repository.success_callback(payment.id)
        payload = event.payload_redacted if event is not None else {}
        amount = status.amount
        if amount is None and payload.get("Amount") not in (None, ""):
            amount = Decimal(str(payload["Amount"]))
        receipt = status.transaction_ref
        if receipt is None and payload.get("MpesaReceiptNumber"):
            receipt = str(payload["MpesaReceiptNumber"])
        return replace(status, amount=amount, transaction_ref=receipt)

    async def _settle(self, payment: Payment) -> set[UUID]:
        order = await self.repository.order(payment.order_id, lock=True)
        if order is None:
            raise RuntimeError("Payment order is missing")
        if order.status == "pending_payment":
            self._mark_paid(order, "pending_payment", "Verified provider status")
            return set()
        refunds = RefundService(self.repository, self.settings)
        if order.status == "expired" and order.paid_at is None:
            # The buyer paid after the reservation lapsed and the stock was released. Only
            # take the order if all of it is still available; otherwise return the money.
            changed = await inventory.reserve_again(
                self.repository,
                await self.repository.order_items(order.id),
                order_id=order.id,
                actor_user_id=order.buyer_id,
                reason="Late payment verified",
            )
            if changed is not None:
                self._mark_paid(order, "expired", "Late payment verified; stock reserved again")
                return changed
            await refunds.request(
                payment,
                amount=payment.amount,
                reason="late_payment_stock_unavailable",
                dedupe_key=f"refund:{payment.id}:late",
            )
            return set()
        reason = "order_cancelled" if order.status == "cancelled" else "duplicate_payment"
        await refunds.request(
            payment,
            amount=payment.amount,
            reason=reason,
            dedupe_key=f"refund:{payment.id}:{reason}",
        )
        return set()

    def _mark_paid(self, order: Order, previous: str, reason: str) -> None:
        order.status = "paid"
        order.paid_at = _now()
        order.version += 1
        self.repository.add(
            OrderStatusHistory(
                id=uuid4(),
                order_id=order.id,
                actor_user_id=None,
                previous_status=previous,
                new_status="paid",
                reason=reason,
            )
        )

    async def _shorten_reservation(self, payment: Payment) -> None:
        """A failed or dismissed prompt should not hold farmers' stock for the full window."""
        order = await self.repository.order(payment.order_id, lock=True)
        if order is None or order.status != "pending_payment":
            return
        now = _now()
        if await self.repository.in_flight_payment(
            order.id,
            since=now - timedelta(seconds=self.settings.payment_inflight_grace_seconds),
            exclude=payment.id,
        ):
            return
        deadline = now + timedelta(minutes=self.settings.payment_retry_grace_minutes)
        if deadline >= order.reservation_expires_at:
            return
        order.reservation_expires_at = deadline
        order.version += 1
        self.repository.add(
            CheckoutService._expiry_job(
                order, f"order-expire:{order.id}:retry:{payment.id}", available_at=deadline
            )
        )

    def _initiation_request(self, payment: Payment) -> InitiationRequest:
        if payment.payer_phone_e164 is None:
            raise PaymentProviderError("Payer phone is missing")
        return InitiationRequest(
            amount=payment.amount,
            currency=payment.currency,
            phone_e164=payment.payer_phone_e164,
            account_reference=payment.account_reference,
            description="Mavuno order",
        )

    def _discrepancy(self, payment: Payment, status: ProviderStatus) -> str | None:
        if status.outcome != "succeeded":
            return None
        if status.currency != payment.currency:
            return "amount_or_currency_mismatch"
        if status.amount is not None and status.amount != payment.amount:
            return "amount_or_currency_mismatch"
        if status.payer_phone_e164 and status.payer_phone_e164 != payment.payer_phone_e164:
            return "payer_phone_mismatch"
        if status.merchant_account and status.merchant_account != self.settings.daraja_shortcode:
            return "merchant_account_mismatch"
        return None

    @staticmethod
    def _reconciliation_state(status: ProviderStatus, discrepancy: str | None) -> str:
        if discrepancy is not None:
            return "discrepancy"
        if status.outcome != "succeeded":
            return "matched"
        if status.transaction_ref is None or status.amount is None:
            # Confirmed by the status query; the receipt arrives with the callback later.
            return "matched_query_only"
        return "matched"

    def _check_token(self, token: str) -> None:
        expected = self.settings.daraja_callback_token
        if expected is None or not hmac.compare_digest(token, expected.get_secret_value()):
            raise ApiError(
                status_code=404, code="webhook_not_found", message="Webhook was not found"
            )

    async def _invalidate_listings(self, listing_ids: Iterable[UUID]) -> None:
        if self.catalog_cache is None:
            return
        for listing_id in listing_ids:
            await self.catalog_cache.invalidate_listing(str(listing_id))

    @staticmethod
    async def _close_provider(provider: PaymentProvider | None) -> None:
        if isinstance(provider, DarajaProvider):
            await provider.aclose()
