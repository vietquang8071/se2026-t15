"""Structured error response models for the LLM Service contract."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StrictStr, model_validator

from app.schemas.common import ContractModel, JsonNumber, NonBlankString, OpaqueId

ErrorCode = Literal[
    "VALIDATION_ERROR",
    "UNSUPPORTED_CONTRACT_VERSION",
    "AUTHENTICATION_REQUIRED",
    "SERVICE_FORBIDDEN",
    "PAYLOAD_TOO_LARGE",
    "TRANSCRIPT_TOO_LONG",
    "EMPTY_TRANSCRIPT",
    "CAPACITY_LIMIT",
    "PROVIDER_FAILURE",
    "INVALID_STRUCTURED_OUTPUT",
    "UNVERIFIED_EVIDENCE",
    "PROVIDER_RATE_LIMIT",
    "PROVIDER_CONFIGURATION_ERROR",
    "PROVIDER_TIMEOUT",
    "REQUEST_TIMEOUT",
    "INTERNAL_ERROR",
]
HttpStatus = Literal[400, 401, 403, 413, 422, 429, 500, 502, 503, 504]
PositiveRetryDelay = Annotated[JsonNumber, Field(gt=0)]

HTTP_STATUS_BY_ERROR: dict[ErrorCode, int] = {
    "VALIDATION_ERROR": 400,
    "UNSUPPORTED_CONTRACT_VERSION": 400,
    "AUTHENTICATION_REQUIRED": 401,
    "SERVICE_FORBIDDEN": 403,
    "PAYLOAD_TOO_LARGE": 413,
    "TRANSCRIPT_TOO_LONG": 413,
    "EMPTY_TRANSCRIPT": 422,
    "CAPACITY_LIMIT": 429,
    "PROVIDER_FAILURE": 502,
    "INVALID_STRUCTURED_OUTPUT": 502,
    "UNVERIFIED_EVIDENCE": 502,
    "PROVIDER_RATE_LIMIT": 503,
    "PROVIDER_CONFIGURATION_ERROR": 503,
    "PROVIDER_TIMEOUT": 504,
    "REQUEST_TIMEOUT": 504,
    "INTERNAL_ERROR": 500,
}
NON_RETRYABLE_ERRORS: frozenset[ErrorCode] = frozenset(
    {
        "VALIDATION_ERROR",
        "UNSUPPORTED_CONTRACT_VERSION",
        "AUTHENTICATION_REQUIRED",
        "SERVICE_FORBIDDEN",
        "PAYLOAD_TOO_LARGE",
        "TRANSCRIPT_TOO_LONG",
        "EMPTY_TRANSCRIPT",
        "INVALID_STRUCTURED_OUTPUT",
        "UNVERIFIED_EVIDENCE",
        "PROVIDER_CONFIGURATION_ERROR",
    }
)


class ErrorDetail(ContractModel):
    path: NonBlankString
    code: Annotated[StrictStr, Field(min_length=1, max_length=128)]
    message: NonBlankString


class ErrorEnvelope(ContractModel):
    statusCode: HttpStatus
    code: ErrorCode
    message: NonBlankString
    request_id: OpaqueId | None
    retryable: bool
    retry_after_seconds: PositiveRetryDelay | None
    errors: list[ErrorDetail]

    @model_validator(mode="after")
    def status_and_retry_policy_match_code(self) -> ErrorEnvelope:
        expected_status = HTTP_STATUS_BY_ERROR[self.code]
        if self.statusCode != expected_status:
            raise ValueError(
                f"Error code {self.code} requires HTTP status {expected_status}."
            )
        if self.code in NON_RETRYABLE_ERRORS and self.retryable:
            raise ValueError(f"Error code {self.code} must not be marked retryable.")
        if self.retry_after_seconds is not None and not self.retryable:
            raise ValueError("retry_after_seconds requires retryable=true.")
        return self
