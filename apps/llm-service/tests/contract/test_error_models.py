import json
from pathlib import Path

import pytest
from pydantic import ValidationError


FIXTURES = Path(__file__).parents[1] / "fixtures"


def _error_model():
    try:
        from app.schemas.errors import ErrorEnvelope
    except ImportError as error:
        pytest.fail(f"ErrorEnvelope is not implemented yet: {error}")
    return ErrorEnvelope


def _valid_error():
    return json.loads((FIXTURES / "errors" / "provider_rate_limit.json").read_text())


def test_provider_rate_limit_error_fixture_validates():
    error = _error_model().model_validate(_valid_error())

    assert error.statusCode == 503
    assert error.code == "PROVIDER_RATE_LIMIT"
    assert error.retryable is True
    assert error.retry_after_seconds == 15


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("VALIDATION_ERROR", 400),
        ("UNSUPPORTED_CONTRACT_VERSION", 400),
        ("AUTHENTICATION_REQUIRED", 401),
        ("SERVICE_FORBIDDEN", 403),
        ("PAYLOAD_TOO_LARGE", 413),
        ("TRANSCRIPT_TOO_LONG", 413),
        ("EMPTY_TRANSCRIPT", 422),
        ("CAPACITY_LIMIT", 429),
        ("PROVIDER_FAILURE", 502),
        ("INVALID_STRUCTURED_OUTPUT", 502),
        ("UNVERIFIED_EVIDENCE", 502),
        ("PROVIDER_RATE_LIMIT", 503),
        ("PROVIDER_CONFIGURATION_ERROR", 503),
        ("PROVIDER_TIMEOUT", 504),
        ("REQUEST_TIMEOUT", 504),
        ("INTERNAL_ERROR", 500),
    ],
)
def test_error_codes_are_bound_to_contract_statuses(code, status):
    value = _valid_error()
    value.update(code=code, statusCode=status, retryable=False, retry_after_seconds=None)

    assert _error_model().model_validate(value).code == code


def test_error_code_with_wrong_status_is_rejected():
    value = _valid_error()
    value["statusCode"] = 400

    with pytest.raises(ValidationError):
        _error_model().model_validate(value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("statusCode", "503"),
        ("statusCode", True),
        ("code", "MADE_UP_ERROR"),
        ("retryable", "true"),
        ("retry_after_seconds", 0),
        ("retry_after_seconds", -2),
    ],
)
def test_invalid_error_types_codes_and_retry_metadata_are_rejected(field, value):
    error = _valid_error()
    error[field] = value

    with pytest.raises(ValidationError):
        _error_model().model_validate(error)


@pytest.mark.parametrize(
    "code",
    [
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
    ],
)
def test_nonretryable_errors_cannot_be_marked_retryable(code):
    status_by_code = {
        "VALIDATION_ERROR": 400,
        "UNSUPPORTED_CONTRACT_VERSION": 400,
        "AUTHENTICATION_REQUIRED": 401,
        "SERVICE_FORBIDDEN": 403,
        "PAYLOAD_TOO_LARGE": 413,
        "TRANSCRIPT_TOO_LONG": 413,
        "EMPTY_TRANSCRIPT": 422,
        "INVALID_STRUCTURED_OUTPUT": 502,
        "UNVERIFIED_EVIDENCE": 502,
        "PROVIDER_CONFIGURATION_ERROR": 503,
    }
    value = _valid_error()
    value.update(
        code=code,
        statusCode=status_by_code[code],
        retryable=True,
        retry_after_seconds=1,
    )

    with pytest.raises(ValidationError):
        _error_model().model_validate(value)


def test_retry_after_requires_retryable_error():
    value = _valid_error()
    value["retryable"] = False

    with pytest.raises(ValidationError):
        _error_model().model_validate(value)


def test_error_envelope_requires_all_fields_and_typed_issues():
    value = _valid_error()
    del value["errors"]

    with pytest.raises(ValidationError):
        _error_model().model_validate(value)

    value = _valid_error()
    value["errors"] = [{"path": "meeting.anchor_date", "code": "FIELD_REQUIRED"}]
    with pytest.raises(ValidationError):
        _error_model().model_validate(value)
