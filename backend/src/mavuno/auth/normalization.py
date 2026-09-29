from __future__ import annotations

import phonenumbers
from pydantic import EmailStr, TypeAdapter

_email_adapter = TypeAdapter(EmailStr)


def normalize_email(value: str) -> str:
    return str(_email_adapter.validate_python(value.strip())).lower()


def normalize_phone(value: str) -> str:
    try:
        parsed = phonenumbers.parse(value.strip(), "KE")
    except phonenumbers.NumberParseException as exc:
        raise ValueError("The phone number is invalid") from exc
    if not phonenumbers.is_valid_number(parsed):
        raise ValueError("The phone number is invalid")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def normalize_login_identifier(value: str) -> tuple[str, str]:
    candidate = value.strip()
    if "@" in candidate:
        return "email", normalize_email(candidate)
    return "phone_e164", normalize_phone(candidate)
