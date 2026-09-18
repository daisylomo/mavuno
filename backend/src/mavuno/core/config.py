from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_V1_PREFIX = "/api/v1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="MAVUNO_",
        extra="ignore",
    )

    app_name: str = "Mavuno API"
    environment: Literal["local", "test", "staging", "production"] = "local"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_config_path: Path = Path("conf/logging.yaml")
    cors_origins: list[AnyHttpUrl] = Field(default_factory=list)
    database_url: SecretStr | None = None
    database_pool_size: int = Field(default=5, ge=1, le=50)
    database_max_overflow: int = Field(default=10, ge=0, le=100)
    database_pool_recycle_seconds: int = Field(default=1800, ge=60)
    auth_issuer: str = "mavuno-api"
    auth_audience: str = "mavuno-mobile"
    auth_active_key_id: str = "local-v1"
    auth_signing_keys: dict[str, SecretStr] = Field(default_factory=dict)
    auth_access_token_minutes: int = Field(default=15, ge=1, le=60)
    auth_refresh_token_days: int = Field(default=30, ge=1, le=90)
    auth_rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    auth_register_rate_limit: int = Field(default=5, ge=1, le=1000)
    auth_login_rate_limit: int = Field(default=10, ge=1, le=1000)
    auth_refresh_rate_limit: int = Field(default=20, ge=1, le=1000)
    auth_rate_limit_max_entries: int = Field(default=10_000, ge=100, le=1_000_000)
    push_token_hash_key: SecretStr | None = Field(default=None, min_length=32)
    push_token_encryption_key: SecretStr | None = None
    order_reservation_minutes: int = Field(default=15, ge=5, le=120)
    payments_enabled: bool = False
    daraja_environment: Literal["sandbox", "production"] = "sandbox"
    daraja_sandbox_base_url: AnyHttpUrl = AnyHttpUrl("https://sandbox.safaricom.co.ke")
    daraja_production_base_url: AnyHttpUrl = AnyHttpUrl("https://api.safaricom.co.ke")
    daraja_consumer_key: SecretStr | None = None
    daraja_consumer_secret: SecretStr | None = None
    daraja_shortcode: str | None = None
    daraja_passkey: SecretStr | None = None
    daraja_callback_base_url: AnyHttpUrl | None = None
    daraja_callback_token: SecretStr | None = Field(default=None, min_length=32)
    daraja_request_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    daraja_retry_limit: int = Field(default=3, ge=0, le=10)
    bank_provider_name: str | None = None
    bank_base_url: AnyHttpUrl | None = None
    bank_client_id: SecretStr | None = None
    bank_client_secret: SecretStr | None = None
    worker_poll_seconds: float = Field(default=2.0, ge=0.1, le=60)
    notification_push_url: AnyHttpUrl | None = None
    notification_push_api_key: SecretStr | None = None
    notification_push_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    outbox_lease_seconds: int = Field(default=60, ge=10, le=600)
    outbox_retry_cap_seconds: int = Field(default=900, ge=30, le=3600)

    @model_validator(mode="after")
    def validate_auth_keys(self) -> Settings:
        if not self.auth_signing_keys:
            if self.environment in {"staging", "production"}:
                raise ValueError("MAVUNO_AUTH_SIGNING_KEYS is required outside local/test")
            self.auth_signing_keys = {
                self.auth_active_key_id: SecretStr("local-only-change-this-32-byte-key")
            }
        if self.auth_active_key_id not in self.auth_signing_keys:
            raise ValueError("MAVUNO_AUTH_ACTIVE_KEY_ID must identify a configured signing key")
        if any(len(secret.get_secret_value()) < 32 for secret in self.auth_signing_keys.values()):
            raise ValueError("Every authentication signing key must be at least 32 characters")
        return self

    @model_validator(mode="after")
    def validate_notification_provider(self) -> Settings:
        if (self.notification_push_url is None) != (self.notification_push_api_key is None):
            raise ValueError("Push provider URL and API key must be configured together")
        return self

    @model_validator(mode="after")
    def validate_push_token_secrets(self) -> Settings:
        from mavuno.profiles.push_tokens import validate_fernet_key

        if self.environment == "production" and (
            self.push_token_hash_key is None or self.push_token_encryption_key is None
        ):
            raise ValueError("Push-token hash and encryption keys are required in production")
        if self.push_token_encryption_key is not None:
            validate_fernet_key(self.push_token_encryption_key.get_secret_value())
        if (
            self.push_token_hash_key is not None
            and self.push_token_encryption_key is not None
            and self.push_token_hash_key.get_secret_value()
            == self.push_token_encryption_key.get_secret_value()
        ):
            raise ValueError("Push-token hash and encryption keys must be distinct")
        return self

    @model_validator(mode="after")
    def validate_payment_settings(self) -> Settings:
        if self.payments_enabled:
            required = (
                self.daraja_consumer_key,
                self.daraja_consumer_secret,
                self.daraja_shortcode,
                self.daraja_passkey,
                self.daraja_callback_base_url,
                self.daraja_callback_token,
            )
            if any(value is None for value in required):
                raise ValueError(
                    "Daraja credentials, shortcode, callback URL, and token are required"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
