import asyncio
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.providers.errors import (
    ProviderConfigurationError, ProviderEmptyContentError, ProviderFailureError,
    ProviderMalformedResponseError, ProviderRateLimitError, ProviderTimeoutError,
    ProviderTruncatedResponseError, ProviderUnavailableError,
)
from app.providers.models import ProviderMessage, ProviderRequest
from app.providers.openrouter import OpenRouterAdapter


def request(**options):
    return ProviderRequest(messages=[ProviderMessage(role="user", content="synthetic-private-input")], **options)


def settings(monkeypatch, **options):
    monkeypatch.setenv("OPENROUTER_API_KEY", secrets.token_hex(24))
    return Settings(_env_file=None, **options)


def envelope(content='{"ok":true}', **overrides):
    data = {"model": "returned/model", "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}]}
    data.update(overrides)
    return data


def invoke(config, handler, provider_request=None):
    return asyncio.run(
        OpenRouterAdapter(config, transport_factory=lambda: httpx.MockTransport(handler))
        .generate(provider_request or request())
    )


def test_success_request_normalization_and_configuration(monkeypatch):
    config = settings(monkeypatch, openrouter_model="custom/model", openrouter_max_output_tokens=300, openrouter_temperature=0.4)
    attempts = []

    def handler(upstream):
        attempts.append(upstream)
        body = json.loads(upstream.content)
        assert upstream.url.path == "/api/v1/chat/completions"
        assert upstream.headers["Authorization"] == "Bearer " + config.openrouter_api_key.get_secret_value()
        assert body["model"] == "custom/model"
        assert body["messages"] == [{"role": "user", "content": "synthetic-private-input"}]
        assert body["max_tokens"] == 300
        assert body["temperature"] == 0.4
        assert body["response_format"] == {"type": "json_object"}
        assert body["provider"] == {"require_parameters": True, "allow_fallbacks": False}
        assert "models" not in body
        return httpx.Response(200, json=envelope(usage={"prompt_tokens": 12, "completion_tokens": 4}))

    result = invoke(config, handler)
    assert (result.model_id, result.finish_reason, result.content) == ("returned/model", "stop", '{"ok":true}')
    assert (result.usage.input_tokens, result.usage.output_tokens) == (12, 4)
    assert len(attempts) == 1


def test_request_values_override_defaults_and_text_mode(monkeypatch):
    config = settings(monkeypatch, openrouter_require_parameters=False)
    def handler(upstream):
        body = json.loads(upstream.content)
        assert "response_format" not in body
        assert body["provider"] == {"require_parameters": False, "allow_fallbacks": False}
        assert body["max_tokens"] == 45
        assert body["temperature"] == 1.0
        return httpx.Response(200, json=envelope("{invalid"))
    result = invoke(config, handler, request(structured_output_mode="text", max_output_tokens=45, temperature=1.0))
    assert result.content == "{invalid"
    assert result.usage is None


@pytest.mark.parametrize("bad", [
    {}, {"choices": []}, {"choices": "invalid"}, {"choices": [None]},
    {"choices": [{"message": {}, "finish_reason": "stop"}]},
    {"choices": [{"message": {"role": "user", "content": "x"}, "finish_reason": "stop"}]},
    {"usage": {"prompt_tokens": 1}},
    {"usage": {"prompt_tokens": True, "completion_tokens": 1}},
    {"model": ""},
])
def test_malformed_envelope_is_rejected(monkeypatch, bad):
    config = settings(monkeypatch)
    data = envelope(**bad)
    if not bad:
        data = {}
    with pytest.raises(ProviderMalformedResponseError):
        invoke(config, lambda _: httpx.Response(200, json=data))


@pytest.mark.parametrize("content", [None, "", "  ", [], {}])
def test_empty_or_unusable_content_is_rejected(monkeypatch, content):
    with pytest.raises(ProviderEmptyContentError):
        invoke(settings(monkeypatch), lambda _: httpx.Response(200, json=envelope(content)))


def test_truncated_content_is_rejected(monkeypatch):
    body = envelope()
    body["choices"][0]["finish_reason"] = "length"
    with pytest.raises(ProviderTruncatedResponseError):
        invoke(settings(monkeypatch), lambda _: httpx.Response(200, json=body))


def test_invalid_response_json_is_rejected(monkeypatch):
    with pytest.raises(ProviderMalformedResponseError):
        invoke(settings(monkeypatch), lambda _: httpx.Response(200, content=b"invalid JSON"))


@pytest.mark.parametrize(("status", "error"), [
    (401, ProviderConfigurationError), (403, ProviderConfigurationError),
    (404, ProviderUnavailableError), (429, ProviderRateLimitError),
    (500, ProviderFailureError), (502, ProviderFailureError), (503, ProviderFailureError),
    (400, ProviderFailureError),
])
def test_http_errors_make_one_attempt_without_leaking_body(monkeypatch, caplog, status, error):
    config = settings(monkeypatch)
    secret = config.openrouter_api_key.get_secret_value()
    attempts = []
    def handler(upstream):
        attempts.append(upstream)
        return httpx.Response(status, text=f"{secret} synthetic-private-input", headers={"Retry-After": "15"})
    with caplog.at_level(logging.DEBUG), pytest.raises(error) as caught:
        invoke(config, handler)
    assert len(attempts) == 1
    assert secret not in str(caught.value) + repr(caught.value) + caplog.text
    assert "synthetic-private-input" not in str(caught.value) + repr(caught.value) + caplog.text
    if status == 429:
        assert caught.value.retry_after_seconds == 15


@pytest.mark.parametrize("header", ["0", "-1", "inf", "NaN", "invalid", "9999999999999999999999999999999999999999999"])
def test_unsafe_retry_after_is_ignored(monkeypatch, header):
    with pytest.raises(ProviderRateLimitError) as caught:
        invoke(settings(monkeypatch), lambda _: httpx.Response(429, headers={"Retry-After": header}))
    assert caught.value.retry_after_seconds is None


def test_provider_timeout(monkeypatch):
    def handler(upstream):
        raise httpx.ReadTimeout("unsafe detail", request=upstream)
    with pytest.raises(ProviderTimeoutError, match="timed out"):
        invoke(settings(monkeypatch), handler)


def test_total_timeout_cancels_slow_transport(monkeypatch):
    async def handler(upstream):
        await asyncio.sleep(0.05)
        return httpx.Response(200, json=envelope())
    with pytest.raises(ProviderTimeoutError):
        invoke(settings(monkeypatch, llm_service_provider_timeout_seconds=0.001), handler)


@pytest.mark.parametrize("key", [None, "", "   "])
def test_missing_credentials_never_send_request(monkeypatch, key):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    config = Settings(_env_file=None, openrouter_api_key=SecretStr(key) if key is not None else None)
    attempts = []
    with pytest.raises(ProviderConfigurationError):
        invoke(config, lambda upstream: attempts.append(upstream))
    assert attempts == []


@pytest.mark.parametrize("name,value", [
    ("openrouter_temperature", -0.1), ("openrouter_temperature", 2.1),
    ("openrouter_temperature", float("nan")), ("openrouter_max_output_tokens", 0),
    ("openrouter_structured_output_mode", "json_schema"),
])
def test_settings_reject_bad_generation_configuration(monkeypatch, name, value):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{name: value})


def test_transport_is_closed_after_success_and_error(monkeypatch):
    class RecordingTransport(httpx.AsyncBaseTransport):
        def __init__(self, status):
            self.closed = False
            self.status = status
        async def handle_async_request(self, upstream):
            return httpx.Response(self.status, json=envelope())
        async def aclose(self):
            self.closed = True
    for status in (200, 500):
        transport = RecordingTransport(status)
        adapter = OpenRouterAdapter(settings(monkeypatch), transport_factory=lambda: transport)
        if status == 200:
            asyncio.run(adapter.generate(request()))
        else:
            with pytest.raises(ProviderFailureError):
                asyncio.run(adapter.generate(request()))
        assert transport.closed


def test_settings_read_key_from_environment_and_mask_it(monkeypatch):
    key = secrets.token_hex(24)
    monkeypatch.setenv("OPENROUTER_API_KEY", key)
    config = Settings(_env_file=None)
    assert config.openrouter_api_key.get_secret_value() == key
    assert key not in repr(config)
    assert key not in str(config.model_dump())


@pytest.mark.parametrize("base", ["http://openrouter.ai/api/v1", "https://user:pass@openrouter.ai/api/v1", "https://openrouter.ai/api/v1?x=secret", "https://openrouter.ai/api/v1?", "https://openrouter.ai/api/v1#", "https://bad host/api/v1", "https://openrouter.ai:bad/api/v1"])
def test_invalid_base_url_is_configuration_error_without_network(monkeypatch, base):
    config = settings(monkeypatch, openrouter_base_url=base)
    attempts = []
    with pytest.raises(ProviderConfigurationError):
        invoke(config, lambda upstream: attempts.append(upstream))
    assert attempts == []


@pytest.mark.parametrize("key", ["secret\nvalue", "\u00e9"])
def test_non_header_safe_key_is_configuration_error_without_network(monkeypatch, key):
    config = settings(monkeypatch, openrouter_api_key=SecretStr(key))
    attempts = []
    with pytest.raises(ProviderConfigurationError):
        invoke(config, lambda upstream: attempts.append(upstream))
    assert attempts == []


def test_retry_after_http_date_is_preserved(monkeypatch):
    date = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=60), usegmt=True)
    with pytest.raises(ProviderRateLimitError) as caught:
        invoke(settings(monkeypatch), lambda _: httpx.Response(429, headers={"Retry-After": date}))
    assert 0 < caught.value.retry_after_seconds <= 60


def test_network_failure_is_sanitized(monkeypatch, caplog):
    config = settings(monkeypatch)
    secret = config.openrouter_api_key.get_secret_value()
    def handler(upstream):
        raise httpx.ConnectError(f"{secret} synthetic-private-input", request=upstream)
    with caplog.at_level(logging.DEBUG), pytest.raises(ProviderFailureError) as caught:
        invoke(config, handler)
    assert secret not in str(caught.value) + caplog.text
    assert "synthetic-private-input" not in str(caught.value) + caplog.text


def test_timeout_is_passed_to_transport(monkeypatch):
    def handler(upstream):
        assert all(value == 3.5 for value in upstream.extensions["timeout"].values())
        return httpx.Response(200, json=envelope())
    invoke(settings(monkeypatch, llm_service_provider_timeout_seconds=3.5), handler)


def test_settings_mode_controls_default_request(monkeypatch):
    def handler(upstream):
        assert "response_format" not in json.loads(upstream.content)
        return httpx.Response(200, json=envelope())
    invoke(settings(monkeypatch, openrouter_structured_output_mode="text"), handler)


@pytest.mark.parametrize("reason", [None, "content_filter", "tool_calls"])
def test_incomplete_finish_reasons_are_not_success(monkeypatch, reason):
    body = envelope()
    body["choices"][0]["finish_reason"] = reason
    with pytest.raises(ProviderMalformedResponseError):
        invoke(settings(monkeypatch), lambda _: httpx.Response(200, json=body))


def test_redirect_is_not_followed_with_credentials(monkeypatch):
    requests = []
    def handler(upstream):
        requests.append(upstream)
        return httpx.Response(307, headers={"Location": "https://different.example/path"})
    with pytest.raises(ProviderFailureError):
        invoke(settings(monkeypatch), handler)
    assert len(requests) == 1


def test_deeply_nested_response_is_sanitized_malformed_error(monkeypatch):
    data = b"[" * 2000 + b"]" * 2000
    with pytest.raises(ProviderMalformedResponseError):
        invoke(settings(monkeypatch), lambda _: httpx.Response(200, content=data))


def test_json_decoder_recursion_error_is_sanitized(monkeypatch):
    from app.providers.openrouter import _normalize_response

    def fail_decode(response):
        raise RecursionError("private provider body")
    monkeypatch.setattr(httpx.Response, "json", fail_decode)
    with pytest.raises(ProviderMalformedResponseError) as caught:
        _normalize_response(httpx.Response(200, content=b"[]"))
    assert caught.value.__context__ is None


@pytest.mark.parametrize("location", ["envelope", "choice"])
def test_error_in_success_status_envelope_is_never_accepted(monkeypatch, location):
    config = settings(monkeypatch)
    body = envelope()
    target = body if location == "envelope" else body["choices"][0]
    target["error"] = {"message": "synthetic-private-input"}
    with pytest.raises(ProviderFailureError) as caught:
        invoke(config, lambda _: httpx.Response(200, json=body))
    assert "synthetic-private-input" not in str(caught.value)


@pytest.mark.parametrize("error_type", [httpx.ConnectError, httpx.ReadTimeout])
def test_provider_error_does_not_retain_sensitive_http_exception(monkeypatch, error_type):
    config = settings(monkeypatch)
    def handler(upstream):
        raise error_type("private detail", request=upstream)
    with pytest.raises((ProviderFailureError, ProviderTimeoutError)) as caught:
        invoke(config, handler)
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None


def test_each_generation_gets_its_own_closed_transport(monkeypatch):
    instances = []
    class SingleUseTransport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.closed = False
            instances.append(self)
        async def handle_async_request(self, upstream):
            assert not self.closed
            await asyncio.sleep(0)
            return httpx.Response(200, json=envelope())
        async def aclose(self):
            self.closed = True
    adapter = OpenRouterAdapter(settings(monkeypatch), transport_factory=SingleUseTransport)
    async def run():
        await adapter.generate(request())
        await asyncio.gather(adapter.generate(request()), adapter.generate(request()))
    asyncio.run(run())
    assert len(instances) == 3
    assert all(instance.closed for instance in instances)
