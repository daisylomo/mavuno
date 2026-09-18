from __future__ import annotations

import base64
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

import httpx2 as httpx

from mavuno.core.config import Settings
from mavuno.payments.provider import (
    CallbackEvent,
    InitiationRequest,
    InitiationResult,
    PaymentOutcome,
    PaymentProviderError,
    ProviderStatus,
)


class DarajaProvider:
    """Safaricom Daraja M-PESA Express adapter.

    STK callbacks are treated as notifications, not proof of funds. The payment service always
    schedules a server-to-server status query before crediting an order.
    """

    name = "daraja"

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        required = (
            settings.daraja_consumer_key,
            settings.daraja_consumer_secret,
            settings.daraja_shortcode,
            settings.daraja_passkey,
            settings.daraja_callback_base_url,
            settings.daraja_callback_token,
        )
        if any(value is None for value in required):
            raise PaymentProviderError("Daraja is not configured")
        base = (
            settings.daraja_sandbox_base_url
            if settings.daraja_environment == "sandbox"
            else settings.daraja_production_base_url
        )
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(
            base_url=str(base).rstrip("/"), timeout=settings.daraja_request_timeout_seconds
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def initiate(self, request: InitiationRequest) -> InitiationResult:
        if request.currency != "KES" or request.amount != request.amount.to_integral_value():
            raise PaymentProviderError("M-PESA requires a whole-number KES amount")
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        shortcode = cast(str, self.settings.daraja_shortcode)
        passkey = self._secret(self.settings.daraja_passkey)
        password = base64.b64encode(f"{shortcode}{passkey}{timestamp}".encode()).decode()
        token = await self._access_token()
        phone = request.phone_e164.removeprefix("+")
        callback_base = str(self.settings.daraja_callback_base_url).rstrip("/")
        callback_token = self._secret(self.settings.daraja_callback_token)
        payload = {
            "BusinessShortCode": shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(request.amount),
            "PartyA": phone,
            "PartyB": shortcode,
            "PhoneNumber": phone,
            "CallBackURL": f"{callback_base}/api/v1/webhooks/payments/daraja/{callback_token}",
            "AccountReference": request.account_reference[:12],
            "TransactionDesc": request.description[:13],
        }
        data = await self._post("/mpesa/stkpush/v1/processrequest", payload, token)
        request_ref = str(data.get("CheckoutRequestID", ""))
        if not request_ref:
            raise PaymentProviderError("Daraja did not return a checkout request reference")
        return InitiationResult(
            provider_request_ref=request_ref,
            provider_conversation_ref=self._optional(data.get("MerchantRequestID")),
            outcome="pending",
            response_code=str(data.get("ResponseCode", "")),
        )

    def parse_callback(self, payload: dict[str, object]) -> CallbackEvent:
        try:
            callback = cast(
                dict[str, object], cast(dict[str, object], payload["Body"])["stkCallback"]
            )
            request_ref = str(callback["CheckoutRequestID"])
            result_code = str(callback["ResultCode"])
        except (KeyError, TypeError) as exc:
            raise PaymentProviderError("Malformed Daraja callback") from exc
        outcome = "succeeded" if result_code == "0" else self._failure_outcome(result_code)
        return CallbackEvent(
            provider_event_ref=f"{request_ref}:{result_code}",
            provider_request_ref=request_ref,
            outcome_hint=outcome,
            authenticated=False,
            redacted_payload={
                "CheckoutRequestID": request_ref,
                "MerchantRequestID": self._optional(callback.get("MerchantRequestID")),
                "ResultCode": result_code,
                "ResultDesc": str(callback.get("ResultDesc", ""))[:255],
            },
        )

    async def query_status(self, provider_request_ref: str) -> ProviderStatus:
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        shortcode = cast(str, self.settings.daraja_shortcode)
        password = base64.b64encode(
            f"{shortcode}{self._secret(self.settings.daraja_passkey)}{timestamp}".encode()
        ).decode()
        token = await self._access_token()
        data = await self._post(
            "/mpesa/stkpushquery/v1/query",
            {
                "BusinessShortCode": shortcode,
                "Password": password,
                "Timestamp": timestamp,
                "CheckoutRequestID": provider_request_ref,
            },
            token,
        )
        code = str(data.get("ResultCode", data.get("ResponseCode", "")))
        outcome = "succeeded" if code == "0" else self._failure_outcome(code)
        amount = data.get("Amount")
        return ProviderStatus(
            provider_request_ref=provider_request_ref,
            outcome=outcome,
            amount=Decimal(str(amount)) if amount is not None else None,
            currency="KES",
            payer_phone_e164=self._normalize_optional_phone(data.get("PhoneNumber")),
            merchant_account=self._optional(data.get("BusinessShortCode")) or shortcode,
            transaction_ref=self._optional(data.get("MpesaReceiptNumber")),
            result_code=code,
            result_description=str(data.get("ResultDesc", data.get("ResponseDescription", "")))[
                :255
            ],
        )

    async def reverse(self, transaction_ref: str, amount: Decimal, reason: str) -> str:
        raise PaymentProviderError("Daraja reversal requires an operator credential integration")

    async def _access_token(self) -> str:
        key = self._secret(self.settings.daraja_consumer_key)
        secret = self._secret(self.settings.daraja_consumer_secret)
        credentials = base64.b64encode(f"{key}:{secret}".encode()).decode()
        try:
            response = await self.client.get(
                "/oauth/v1/generate?grant_type=client_credentials",
                headers={"Authorization": f"Basic {credentials}"},
            )
            response.raise_for_status()
            token = str(response.json().get("access_token", ""))
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            raise PaymentProviderError("Daraja authorization failed") from exc
        if not token:
            raise PaymentProviderError("Daraja authorization returned no token")
        return token

    async def _post(self, path: str, payload: dict[str, object], token: str) -> dict[str, Any]:
        try:
            response = await self.client.post(
                path, json=payload, headers={"Authorization": f"Bearer {token}"}
            )
            response.raise_for_status()
            return cast(dict[str, Any], response.json())
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            raise PaymentProviderError("Daraja request failed") from exc

    @staticmethod
    def _failure_outcome(code: str) -> PaymentOutcome:
        if code in {"1032", "1"}:
            return "cancelled"
        if code in {"1037", "1025"}:
            return "expired"
        return "failed"

    @staticmethod
    def _optional(value: object) -> str | None:
        return str(value) if value is not None and value != "" else None

    @staticmethod
    def _normalize_optional_phone(value: object) -> str | None:
        if value is None or value == "":
            return None
        raw = str(value)
        return f"+{raw}" if not raw.startswith("+") else raw

    @staticmethod
    def _secret(value: object) -> str:
        if value is None or not hasattr(value, "get_secret_value"):
            raise PaymentProviderError("Daraja is not configured")
        return str(value.get_secret_value())
