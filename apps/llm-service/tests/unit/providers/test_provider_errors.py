import pytest

from app.providers.errors import (
    ProviderConfigurationError, ProviderFailureError, ProviderRateLimitError,
    ProviderTimeoutError, ProviderUnavailableError, ProviderMalformedResponseError,
    ProviderEmptyContentError, ProviderTruncatedResponseError,
)


@pytest.mark.parametrize(("error", "code", "retryable"), [
    (ProviderConfigurationError(), "PROVIDER_CONFIGURATION_ERROR", False),
    (ProviderUnavailableError(), "PROVIDER_FAILURE", False),
    (ProviderRateLimitError(retry_after_seconds=15), "PROVIDER_RATE_LIMIT", True),
    (ProviderTimeoutError(), "PROVIDER_TIMEOUT", True),
    (ProviderFailureError(), "PROVIDER_FAILURE", False),
    (ProviderMalformedResponseError(), "PROVIDER_FAILURE", False),
    (ProviderEmptyContentError(), "PROVIDER_FAILURE", False),
    (ProviderTruncatedResponseError(), "PROVIDER_FAILURE", False),
])
def test_error_classification(error, code, retryable):
    assert error.code == code
    assert error.retryable is retryable
    assert str(error)


@pytest.mark.parametrize("delay", [-1, 0, float("inf"), float("nan"), True])
def test_invalid_retry_delay_is_rejected(delay):
    with pytest.raises(ValueError):
        ProviderRateLimitError(retry_after_seconds=delay)
