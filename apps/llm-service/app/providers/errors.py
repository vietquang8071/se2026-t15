"""Sanitized, provider-independent failures for later HTTP mapping."""

import math


class ProviderError(Exception):
    code = "PROVIDER_FAILURE"
    retryable = False
    message = "Provider generation failed."

    def __init__(self) -> None:
        super().__init__(self.message)


class ProviderConfigurationError(ProviderError):
    code = "PROVIDER_CONFIGURATION_ERROR"
    message = "Provider configuration or authentication is invalid."


class ProviderRateLimitError(ProviderError):
    code = "PROVIDER_RATE_LIMIT"
    retryable = True
    message = "Provider rate limit reached."

    def __init__(self, *, retry_after_seconds: float | None = None) -> None:
        if retry_after_seconds is not None and (
            isinstance(retry_after_seconds, bool)
            or not isinstance(retry_after_seconds, (int, float))
            or not math.isfinite(retry_after_seconds)
            or retry_after_seconds <= 0
        ):
            raise ValueError("Retry delay must be a positive finite number.")
        self.retry_after_seconds = retry_after_seconds
        super().__init__()


class ProviderTimeoutError(ProviderError):
    code = "PROVIDER_TIMEOUT"
    retryable = True
    message = "Provider request timed out."


class ProviderFailureError(ProviderError):
    pass


class ProviderUnavailableError(ProviderFailureError):
    message = "Provider endpoint or model is unavailable."


class ProviderMalformedResponseError(ProviderFailureError):
    message = "Provider response has an invalid envelope."


class ProviderEmptyContentError(ProviderFailureError):
    message = "Provider returned no usable content."


class ProviderTruncatedResponseError(ProviderFailureError):
    message = "Provider response was truncated."
