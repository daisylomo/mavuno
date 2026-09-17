from __future__ import annotations

import hmac
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from mavuno.api.errors import ApiError
from mavuno.auth.context import AuthenticatedUser
from mavuno.auth.normalization import normalize_phone
from mavuno.commerce.repository import CommerceRepository
from mavuno.commerce.schemas import (
    CartItemResponse,
    CartResponse,
    OrderItemResponse,
    OrderResponse,
    PaymentInitiateRequest,
)
from mavuno.core.config import Settings
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


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


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
    def __init__(self, repository: CommerceRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

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
        order.total_amount = subtotal
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
        self.repository.add(
            OutboxJob(
                id=uuid4(),
                job_type="order_expire",
                dedupe_key=f"order-expire:{order.id}",
                payload={"order_id": str(order.id)},
                status="pending",
                attempts=0,
                max_attempts=3,
                available_at=order.reservation_expires_at,
            )
        )
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
        return await self.response(order)

    async def get(self, user: AuthenticatedUser, order_id: UUID) -> OrderResponse:
        order = await self.repository.order(order_id)
        if order is None or order.buyer_id != user.id:
            raise ApiError(status_code=404, code="order_not_found", message="Order was not found")
        return await self.response(order)

    async def response(self, order: Order) -> OrderResponse:
        items = await self.repository.order_items(order.id)
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
        )

    async def expire(self, order_id: UUID) -> None:
        order = await self.repository.order(order_id, lock=True)
        if (
            order is None
            or order.status != "pending_payment"
            or order.reservation_expires_at > _now()
        ):
            return
        items = await self.repository.order_items(order.id)
        for item in sorted(items, key=lambda value: value.listing_id.bytes):
            listing = await self.repository.listing(item.listing_id, lock=True)
            if listing is None:
                raise RuntimeError("Reserved listing is missing")
            listing.available_quantity += item.quantity
            listing.version += 1
            if listing.status == "sold_out":
                listing.status = "active"
            self.repository.add(
                InventoryMovement(
                    id=uuid4(),
                    listing_id=listing.id,
                    actor_user_id=order.buyer_id,
                    movement_type="release",
                    quantity_delta=item.quantity,
                    resulting_quantity=listing.available_quantity,
                    reason="Payment reservation expired",
                    reference_type="order",
                    reference_id=order.id,
                )
            )
        order.status = "expired"
        order.version += 1
        self.repository.add(
            OrderStatusHistory(
                id=uuid4(),
                order_id=order.id,
                actor_user_id=None,
                previous_status="pending_payment",
                new_status="expired",
                reason="Payment reservation expired",
            )
        )
        await self.repository.commit()


class PaymentService:
    def __init__(
        self,
        repository: CommerceRepository,
        settings: Settings,
        provider: PaymentProvider | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.provider = provider

    def provider_for(self, rail: str) -> PaymentProvider:
        if self.provider is not None:
            return self.provider
        if rail == "mpesa":
            return DarajaProvider(self.settings)
        return UnconfiguredBankProvider()

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
        self.repository.add(
            OutboxJob(
                id=uuid4(),
                job_type="payment_status_query",
                dedupe_key=f"payment-query:{payment.id}:0",
                payload={"payment_id": str(payment.id)},
                status="pending",
                attempts=0,
                max_attempts=max(1, self.settings.daraja_retry_limit),
                available_at=_now() + timedelta(seconds=30),
            )
        )
        await self.repository.commit()
        await self.repository.refresh(payment)
        return payment

    async def accept_callback(self, token: str, payload: dict[str, object]) -> None:
        expected = self.settings.daraja_callback_token
        if expected is None or not hmac.compare_digest(token, expected.get_secret_value()):
            raise ApiError(
                status_code=404, code="webhook_not_found", message="Webhook was not found"
            )
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
            OutboxJob(
                id=uuid4(),
                job_type="payment_status_query",
                dedupe_key=f"payment-callback:{event.provider_event_ref}",
                payload={"payment_id": str(payment.id)},
                status="pending",
                attempts=0,
                max_attempts=max(1, self.settings.daraja_retry_limit),
                available_at=_now(),
            )
        )
        try:
            await self.repository.commit()
        except IntegrityError:
            await self.repository.rollback()

    async def reconcile(self, payment_id: UUID) -> None:
        payment = await self.repository.payment(payment_id)
        if (
            payment is None
            or payment.provider_request_ref is None
            or payment.state in {"succeeded", "reversed"}
        ):
            return
        provider: PaymentProvider | None = None
        try:
            provider = self.provider_for(payment.rail)
            status = await provider.query_status(payment.provider_request_ref)
        finally:
            await self._close_provider(provider)
        payment = await self.repository.payment(payment_id, lock=True)
        if payment is None or payment.state in {"succeeded", "reversed"}:
            return
        discrepancy = self._discrepancy(payment, status)
        self.repository.add(
            PaymentReconciliation(
                id=uuid4(),
                payment_id=payment.id,
                expected_amount=payment.amount,
                reported_amount=status.amount,
                currency=status.currency,
                provider_settlement_ref=status.transaction_ref,
                state="matched" if discrepancy is None else "discrepancy",
                discrepancy_reason=discrepancy,
            )
        )
        if status.outcome == "succeeded" and discrepancy is None:
            order = await self.repository.order(payment.order_id, lock=True)
            if order is None:
                raise RuntimeError("Payment order is missing")
            payment.state = "succeeded"
            payment.provider_transaction_ref = status.transaction_ref
            order.status = "paid"
            order.paid_at = _now()
            order.version += 1
            self.repository.add(
                OrderStatusHistory(
                    id=uuid4(),
                    order_id=order.id,
                    actor_user_id=None,
                    previous_status="pending_payment",
                    new_status="paid",
                    reason="Verified provider status",
                )
            )
        elif status.outcome in {"failed", "cancelled", "expired", "reversed"}:
            payment.state = status.outcome
            payment.failure_code = status.result_code
            payment.failure_message = status.result_description
        else:
            payment.state = "processing"
        await self.repository.commit()

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
        if status.amount != payment.amount or status.currency != payment.currency:
            return "amount_or_currency_mismatch"
        if status.payer_phone_e164 and status.payer_phone_e164 != payment.payer_phone_e164:
            return "payer_phone_mismatch"
        if status.merchant_account and status.merchant_account != self.settings.daraja_shortcode:
            return "merchant_account_mismatch"
        if not status.transaction_ref:
            return "transaction_reference_missing"
        return None

    @staticmethod
    async def _close_provider(provider: PaymentProvider | None) -> None:
        if isinstance(provider, DarajaProvider):
            await provider.aclose()
