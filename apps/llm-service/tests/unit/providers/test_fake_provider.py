import asyncio

import pytest

from app.providers.errors import ProviderConfigurationError, ProviderFailureError, ProviderRateLimitError, ProviderTimeoutError
from app.providers.models import ProviderMessage, ProviderRequest, ProviderResult
from fakes.provider import FakeProvider


def request():
    return ProviderRequest(messages=[ProviderMessage(role="user", content="Synthetic input")])


@pytest.mark.parametrize("content", ['{"ok": true}', "", "{not JSON"])
def test_fake_returns_exact_preconfigured_candidate_and_records_request(content):
    result = ProviderResult(content=content, model_id="fake", finish_reason="stop")
    provider = FakeProvider(result=result)
    message = request()
    assert asyncio.run(provider.generate(message)) == result
    assert provider.requests == [message]


@pytest.mark.parametrize("error", [ProviderTimeoutError(), ProviderRateLimitError(), ProviderConfigurationError(), ProviderFailureError()])
def test_fake_simulates_provider_errors(error):
    provider = FakeProvider(error=error)
    message = request()
    with pytest.raises(type(error)):
        asyncio.run(provider.generate(message))
    assert provider.requests == [message]
