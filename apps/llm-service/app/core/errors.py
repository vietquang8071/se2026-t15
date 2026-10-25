"""Safe mapping from runtime failures to the public error envelope."""

from __future__ import annotations

import re
from typing import Any

from fastapi.exceptions import RequestValidationError, ResponseValidationError
from pydantic import ValidationError
from starlette.responses import JSONResponse

from app.schemas.errors import (
    ErrorCode,
    ErrorDetail,
    ErrorEnvelope,
    HTTP_STATUS_BY_ERROR,
)

_SAFE_PATH_PART = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]*|[0-9]+)$")


class ExtractionUnavailableError(RuntimeError):
    """Raised while extraction is intentionally unavailable in LLM-02."""


class AuthenticationRequiredError(RuntimeError):
    """Raised when a service-to-service bearer credential is missing or invalid."""


class ExtractionRequestTimeoutError(RuntimeError):
    """Raised when an extraction use case exceeds its configured budget."""


def valid_request_id(value: object) -> str | None:
    """Return only request IDs that satisfy the contract's opaque ID bounds."""

    if isinstance(value, str) and value.strip() and len(value) <= 128:
        return value
    return None


def request_id_from_body(body: object) -> str | None:
    if isinstance(body, dict):
        return valid_request_id(body.get("request_id"))
    return None


def error_response(
    code: ErrorCode,
    message: str,
    *,
    request_id: str | None = None,
    errors: list[ErrorDetail] | None = None,
    retryable: bool = False,
    retry_after_seconds: float | None = None,
) -> JSONResponse:
    """Serialize errors only through the validated contract model."""

    envelope = ErrorEnvelope(
        statusCode=HTTP_STATUS_BY_ERROR[code],
        code=code,
        message=message,
        request_id=valid_request_id(request_id),
        retryable=retryable,
        retry_after_seconds=retry_after_seconds,
        errors=errors or [],
    )
    return JSONResponse(
        status_code=envelope.statusCode,
        content=envelope.model_dump(mode="json"),
    )


def _safe_path(location: object) -> str:
    if not isinstance(location, (list, tuple)):
        return "body"
    parts = list(location)
    if parts and parts[0] == "body":
        parts = parts[1:]
    safe_parts = [
        str(part) if _SAFE_PATH_PART.fullmatch(str(part)) else "field"
        for part in parts
    ]
    return ".".join(safe_parts) or "body"


def _validation_details(raw_errors: list[dict[str, Any]]) -> list[ErrorDetail]:
    details: list[ErrorDetail] = []
    for item in raw_errors[:50]:
        error_type = item.get("type")
        if error_type == "json_invalid":
            details.append(
                ErrorDetail(
                    path="body",
                    code="INVALID_JSON",
                    message="Nội dung phải là JSON hợp lệ.",
                )
            )
            continue
        is_missing = error_type == "missing"
        details.append(
            ErrorDetail(
                path=_safe_path(item.get("loc")),
                code="FIELD_REQUIRED" if is_missing else "FIELD_INVALID",
                message="Trường này là bắt buộc." if is_missing else "Giá trị không hợp lệ.",
            )
        )
    return details


async def request_validation_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    raw_errors = exc.errors()
    error_types = {item.get("type") for item in raw_errors}
    request_id = request_id_from_body(exc.body)

    if "unsupported_contract_version" in error_types:
        return error_response(
            "UNSUPPORTED_CONTRACT_VERSION",
            "Contract version không được hỗ trợ.",
            request_id=request_id,
            errors=[
                ErrorDetail(
                    path="contract_version",
                    code="UNSUPPORTED_CONTRACT_VERSION",
                    message="Chỉ hỗ trợ contract version 1.0.",
                )
            ],
        )

    if "empty_transcript" in error_types:
        return error_response(
            "EMPTY_TRANSCRIPT",
            "Transcript không có nội dung lời nói hợp lệ.",
            request_id=request_id,
            errors=[
                ErrorDetail(
                    path="transcript.segments",
                    code="EMPTY_TRANSCRIPT",
                    message="Cần ít nhất một segment có nội dung lời nói.",
                )
            ],
        )

    return error_response(
        "VALIDATION_ERROR",
        "Yêu cầu trích xuất không hợp lệ.",
        request_id=request_id,
        errors=_validation_details(raw_errors),
    )


async def extraction_unavailable_handler(
    request: Request,
    exc: ExtractionUnavailableError,
) -> JSONResponse:
    return error_response(
        "PROVIDER_CONFIGURATION_ERROR",
        "Extraction backend chưa sẵn sàng.",
        request_id=valid_request_id(getattr(request.state, "request_id", None)),
    )

async def authentication_required_handler(
    request: Request,
    exc: AuthenticationRequiredError,
) -> JSONResponse:
    return error_response(
        "AUTHENTICATION_REQUIRED",
        "Bearer token không hợp lệ hoặc chưa được cung cấp.",
    )


async def extraction_timeout_handler(
    request: Request,
    exc: ExtractionRequestTimeoutError,
) -> JSONResponse:
    return error_response(
        "REQUEST_TIMEOUT",
        "Yêu cầu trích xuất đã vượt quá thời gian xử lý cho phép.",
        request_id=valid_request_id(getattr(request.state, "request_id", None)),
        retryable=True,
    )


async def response_validation_handler(
    request: Request,
    exc: ResponseValidationError | ValidationError,
) -> JSONResponse:
    return error_response(
        "INVALID_STRUCTURED_OUTPUT",
        "Extraction backend trả về dữ liệu không hợp lệ.",
        request_id=valid_request_id(getattr(request.state, "request_id", None)),
    )
