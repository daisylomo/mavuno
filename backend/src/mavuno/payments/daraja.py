from __future__ import annotations

import base64
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
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
    ReversalNotConfiguredError,
    ReversalResult,
)

# Daraja's STK query answers with an HTTP error and one of these codes while the customer has
# not yet answered the prompt.
PROCESSING_ERROR_CODES = frozenset({"500.001.1001"})


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
            "CallBackURL": f"{callback_base}{request.callback_path}/{callback_token}",
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
        metadata = self._callback_metadata(callback.get("CallbackMetadata"))
        amount = self._decimal(metadata.get("Amount"))
        receipt = self._optional(metadata.get("MpesaReceiptNumber"))
        phone = self._normalize_optional_phone(metadata.get("PhoneNumber"))
        redacted: dict[str, object] = {
            "CheckoutRequestID": request_ref,
            "MerchantRequestID": self._optional(callback.get("MerchantRequestID")),
            "ResultCode": result_code,
            "ResultDesc": str(callback.get("ResultDesc", ""))[:255],
        }
        if outcome == "succeeded":
            # Only settlement facts are kept; the payer's number is masked.
            redacted["Amount"] = str(amount) if amount is not None else None
            redacted["MpesaReceiptNumber"] = receipt
            redacted["PhoneNumberMasked"] = self._mask_phone(phone)
            redacted["TransactionDate"] = self._optional(metadata.get("TransactionDate"))
        return CallbackEvent(
            provider_event_ref=f"{request_ref}:{result_code}",
            provider_request_ref=request_ref,
            outcome_hint=outcome,
            authenticated=False,
            redacted_payload=redacted,
            amount=amount if outcome == "succeeded" else None,
            transaction_ref=receipt if outcome == "succeeded" else None,
            payer_phone_e164=phone if outcome == "succeeded" else None,
        )

    async def query_status(self, provider_request_ref: str) -> ProviderStatus:
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        shortcode = cast(str, self.settings.daraja_shortcode)
        password = base64.b64encode(
            f"{shortcode}{self._secret(self.settings.daraja_passkey)}{timestamp}".encode()
        ).decode()
        token = await self._access_token()
        status_code, data = await self._post_allowing_errors(
            "/mpesa/stkpushquery/v1/query",
            {
                "BusinessShortCode": shortcode,
                "Password": password,
                "Timestamp": timestamp,
                "CheckoutRequestID": provider_request_ref,
            },
            token,
        )
        if status_code >= 400:
            error_code = str(data.get("errorCode", ""))
            if error_code in PROCESSING_ERROR_CODES:
                # Daraja answers an HTTP error while the customer is still on the prompt.
                return self._pending(provider_request_ref, error_code, data)
            raise PaymentProviderError("Daraja request failed")
        # ResponseCode only says the query was accepted; ResultCode is the payment's outcome.
        # A missing ResultCode must never be read as success.
        if "ResultCode" not in data or data.get("ResultCode") in (None, ""):
            return self._pending(provider_request_ref, str(data.get("ResponseCode", "")), data)
        code = str(data["ResultCode"])
        outcome = "succeeded" if code == "0" else self._failure_outcome(code)
        amount = data.get("Amount")
        return ProviderStatus(
            provider_request_ref=provider_request_ref,
            outcome=outcome,
            amount=self._decimal(amount),
            currency="KES",
            payer_phone_e164=self._normalize_optional_phone(data.get("PhoneNumber")),
            merchant_account=self._optional(data.get("BusinessShortCode")) or shortcode,
            transaction_ref=self._optional(data.get("MpesaReceiptNumber")),
            result_code=code,
            result_description=str(data.get("ResultDesc", data.get("ResponseDescription", "")))[
                :255
            ],
        )

    async def reverse(self, transaction_ref: str, amount: Decimal, reason: str) -> ReversalResult:
        initiator = self.settings.daraja_initiator_name
        credential = self.settings.daraja_security_credential
        if not initiator or credential is None:
            raise ReversalNotConfiguredError(
                "Daraja reversal needs MAVUNO_DARAJA_INITIATOR_NAME and "
                "MAVUNO_DARAJA_SECURITY_CREDENTIAL"
            )
        if amount <= 0 or amount != amount.to_integral_value():
            raise PaymentProviderError("M-PESA reversals require a whole-number KES amount")
        token = await self._access_token()
        callback_base = str(self.settings.daraja_callback_base_url).rstrip("/")
        callback_token = self._secret(self.settings.daraja_callback_token)
        result_url = f"{callback_base}/api/v1/webhooks/payments/daraja-reversal/{callback_token}"
        data = await self._post(
            "/mpesa/reversal/v1/request",
            {
                "Initiator": initiator,
                "SecurityCredential": credential.get_secret_value(),
                "CommandID": "TransactionReversal",
                "TransactionID": transaction_ref,
                "Amount": int(amount),
                "ReceiverParty": cast(str, self.settings.daraja_shortcode),
                "RecieverIdentifierType": "11",
                "ResultURL": result_url,
                "QueueTimeOutURL": result_url,
                "Remarks": (reason or "Mavuno refund")[:100],
                "Occasion": "",
            },
            token,
        )
        conversation = self._optional(data.get("ConversationID")) or self._optional(
            data.get("OriginatorConversationID")
        )
        if not conversation:
            raise PaymentProviderError("Daraja did not return a reversal reference")
        return ReversalResult(
            provider_ref=conversation, accepted=str(data.get("ResponseCode", "")) == "0"
        )

    @staticmethod
    def parse_reversal_result(payload: dict[str, object]) -> tuple[str, bool, str]:
        """Return (conversation reference, succeeded, description) from a reversal result."""
        try:
            result = cast(dict[str, object], payload["Result"])
            conversation = str(result.get("ConversationID") or result["OriginatorConversationID"])
            code = str(result["ResultCode"])
        except (KeyError, TypeError) as exc:
            raise PaymentProviderError("Malformed Daraja reversal result") from exc
        return conversation, code == "0", str(result.get("ResultDesc", ""))[:255]

    def _pending(
        self, provider_request_ref: str, code: str, data: dict[str, Any]
    ) -> ProviderStatus:
        return ProviderStatus(
            provider_request_ref=provider_request_ref,
            outcome="pending",
            amount=None,
            currency="KES",
            payer_phone_e164=None,
            merchant_account=cast(str, self.settings.daraja_shortcode),
            transaction_ref=None,
            result_code=code,
            result_description=str(
                data.get("errorMessage", data.get("ResponseDescription", "Processing"))
            )[:255],
        )

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

    async def _post_allowing_errors(
        self, path: str, payload: dict[str, object], token: str
    ) -> tuple[int, dict[str, Any]]:
        try:
            response = await self.client.post(
                path, json=payload, headers={"Authorization": f"Bearer {token}"}
            )
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise PaymentProviderError("Daraja request failed") from exc
        if not isinstance(data, dict):
            raise PaymentProviderError("Daraja request failed")
        return response.status_code, cast(dict[str, Any], data)

    @staticmethod
    def _callback_metadata(value: object) -> dict[str, object]:
        if not isinstance(value, dict):
            return {}
        items = value.get("Item")
        if not isinstance(items, list):
            return {}
        metadata: dict[str, object] = {}
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("Name"), str):
                metadata[item["Name"]] = item.get("Value")
        return metadata

    @staticmethod
    def _decimal(value: object) -> Decimal | None:
        if value is None or value == "" or isinstance(value, bool):
            return None
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None

    @staticmethod
    def _mask_phone(phone: str | None) -> str | None:
        if not phone:
            return None
        return f"{phone[:6]}***{phone[-3:]}" if len(phone) > 9 else "***"

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
