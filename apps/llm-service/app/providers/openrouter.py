"""OpenRouter Chat Completions adapter, without business output validation."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.providers.errors import (
    ProviderConfigurationError,
    ProviderEmptyContentError,
    ProviderFailureError,
    ProviderMalformedResponseError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderTruncatedResponseError,
    ProviderUnavailableError,
)
from app.providers.models import ProviderRequest, ProviderResult, ProviderUsage

_MAX_RETRY_AFTER_SECONDS = 86400.0


def _retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        delay = float(value)
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                return None
            delay = (date - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    if not math.isfinite(delay) or not 0 < delay <= _MAX_RETRY_AFTER_SECONDS:
        return None
    return delay


def _endpoint_and_key(settings: Settings) -> tuple[str, str]:
    secret = settings.openrouter_api_key
    key = secret.get_secret_value() if secret is not None else ""
    if not key or any(not 33 <= ord(char) <= 126 for char in key):
        raise ProviderConfigurationError()
    model = settings.openrouter_model
    base = settings.openrouter_base_url
    try:
        parts = urlsplit(base)
        valid_url = (
            parts.scheme == "https"
            and bool(parts.hostname)
            and parts.port != 0
            and not parts.username
            and not parts.password
            and not parts.query
            and not parts.fragment
            and "?" not in base
            and "#" not in base
            and not any(char.isspace() or ord(char) < 32 for char in base)
        )
    except ValueError:
        valid_url = False
    if not valid_url or not model or model != model.strip() or any(c.isspace() for c in model):
        raise ProviderConfigurationError()
    return f"{base.rstrip('/')}/chat/completions", key


def _normalize_response(response: httpx.Response) -> ProviderResult:
    try:
        data = response.json()
    except (ValueError, UnicodeError, RecursionError):
        data = None
    if not isinstance(data, dict):
        raise ProviderMalformedResponseError()
    if data.get("error") is not None:
        raise ProviderFailureError()
    choices = data.get("choices")
    model = data.get("model")
    if (
        not isinstance(model, str)
        or not model.strip()
        or not isinstance(choices, list)
        or not choices
        or not isinstance(choices[0], dict)
    ):
        raise ProviderMalformedResponseError()
    choice = choices[0]
    if choice.get("error") is not None:
        raise ProviderFailureError()
    reason = choice.get("finish_reason")
    if reason == "length":
        raise ProviderTruncatedResponseError()
    if reason != "stop":
        raise ProviderMalformedResponseError()
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise ProviderMalformedResponseError()
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ProviderEmptyContentError()
    usage_data = data.get("usage")
    usage = None
    if usage_data is not None:
        if not isinstance(usage_data, dict):
            raise ProviderMalformedResponseError()
        try:
            usage = ProviderUsage(
                input_tokens=usage_data.get("prompt_tokens"),
                output_tokens=usage_data.get("completion_tokens"),
            )
        except ValidationError:
            usage = None
        if usage is None:
            raise ProviderMalformedResponseError()
    return ProviderResult(content=content, model_id=model, finish_reason=reason, usage=usage)


class OpenRouterAdapter:
    """Make one bounded request per generation; own and close the HTTP client."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport_factory: Callable[[], httpx.AsyncBaseTransport] | None = None,
    ) -> None:
        self._settings = settings
        self._transport_factory = transport_factory

    async def generate(self, request: ProviderRequest) -> ProviderResult:
        endpoint, key = _endpoint_and_key(self._settings)
        mode = request.structured_output_mode or self._settings.openrouter_structured_output_mode
        payload: dict[str, object] = {
            "model": self._settings.openrouter_model,
            "messages": [message.model_dump() for message in request.messages],
            "max_tokens": (
                request.max_output_tokens
                if request.max_output_tokens is not None
                else self._settings.openrouter_max_output_tokens
            ),
            "temperature": (
                request.temperature
                if request.temperature is not None
                else self._settings.openrouter_temperature
            ),
            "stream": False,
            "provider": {
                "require_parameters": self._settings.openrouter_require_parameters,
                "allow_fallbacks": False,
            },
        }
        if mode == "json_object":
            payload["response_format"] = {"type": "json_object"}
        timeout = self._settings.llm_service_provider_timeout_seconds
        failure: ProviderFailureError | ProviderTimeoutError | None = None
        try:
            async with asyncio.timeout(timeout):
                async with httpx.AsyncClient(
                    transport=self._transport_factory() if self._transport_factory else None,
                    timeout=timeout,
                    follow_redirects=False,
                ) as client:
                    response = await client.post(
                        endpoint, json=payload, headers={"Authorization": f"Bearer {key}"}
                    )
        except (TimeoutError, httpx.TimeoutException):
            failure = ProviderTimeoutError()
        except httpx.RequestError:
            failure = ProviderFailureError()

        if failure is not None:
            raise failure

        if response.status_code in (401, 403):
            raise ProviderConfigurationError()
        if response.status_code == 404:
            raise ProviderUnavailableError()
        if response.status_code == 429:
            raise ProviderRateLimitError(
                retry_after_seconds=_retry_after(response.headers.get("Retry-After"))
            )
        if response.status_code != 200:
            raise ProviderFailureError()
        return _normalize_response(response)
