from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
