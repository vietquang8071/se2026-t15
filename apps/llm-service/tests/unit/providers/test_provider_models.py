import pytest
from pydantic import ValidationError

from app.providers.models import ProviderMessage, ProviderRequest, ProviderResult, ProviderUsage


def test_request_and_result_are_provider_neutral_and_typed():
    request = ProviderRequest(messages=[ProviderMessage(role="user", content="Hello")])
    result = ProviderResult(content="{broken", model_id="example/model", finish_reason="stop")
    assert request.messages[0].role == "user"
    assert result.content == "{broken"
    assert result.usage is None


@pytest.mark.parametrize("values", [
    {"messages": []},
    {"messages": [{"role": "other", "content": "Hello"}]},
    {"messages": [{"role": "user", "content": "Hello"}], "max_output_tokens": 0},
    {"messages": [{"role": "user", "content": "Hello"}], "temperature": float("nan")},
    {"messages": [{"role": "user", "content": "Hello"}], "temperature": 2.1},
])
def test_invalid_request_parameters_are_rejected(values):
    with pytest.raises(ValidationError):
        ProviderRequest.model_validate(values)


@pytest.mark.parametrize("values", [
    {"input_tokens": -1, "output_tokens": 1},
    {"input_tokens": True, "output_tokens": 1},
])
def test_usage_rejects_invalid_counts(values):
    with pytest.raises(ValidationError):
        ProviderUsage.model_validate(values)
