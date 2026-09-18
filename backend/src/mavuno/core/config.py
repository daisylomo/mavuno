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


@lru_cache
def get_settings() -> Settings:
    return Settings()
