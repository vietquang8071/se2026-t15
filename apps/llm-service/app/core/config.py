"""Environment-backed settings for the standalone LLM Service."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated process settings; secrets are masked by ``SecretStr``."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=None,
        extra="ignore",
        validate_default=True,
    )

    llm_service_token: SecretStr | None = None
    llm_service_host: str = Field(default="0.0.0.0", min_length=1, max_length=255)
    llm_service_port: int = Field(default=8000, ge=1, le=65535)
    llm_service_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    llm_service_max_request_bytes: int = Field(default=10 * 1024 * 1024, ge=1)
    llm_service_request_timeout_seconds: float = Field(default=180.0, gt=0, allow_inf_nan=False)
    llm_service_provider_timeout_seconds: float = Field(default=60.0, gt=0, allow_inf_nan=False)

    @field_validator("llm_service_token")
    @classmethod
    def token_must_not_be_empty(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().strip():
            raise ValueError("LLM_SERVICE_TOKEN must not be empty.")
        return value

    @field_validator("llm_service_host")
    @classmethod
    def host_must_not_be_whitespace(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("LLM_SERVICE_HOST must be a non-empty trimmed host value.")
        return value

    @field_validator("llm_service_log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> object:
        if isinstance(value, str):
            return value.upper()
        return value
