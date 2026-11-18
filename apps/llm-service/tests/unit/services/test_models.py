"""Tests for internal extraction data contracts."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, fields, is_dataclass
from pathlib import Path

import pytest

from app.prompts.renderer import RenderedPrompt
from app.providers.models import ProviderMessage, ProviderRequest, ProviderUsage
from app.schemas.candidates import SummaryActionsCandidate
from app.schemas.request import ExtractionRequest
from app.services.models import PreparedExtraction, PreparedRequest


REQUEST_FIXTURE = (
    Path(__file__).parents[2] / "fixtures" / "requests" / "summary_actions_request.json"
)


def make_request() -> ExtractionRequest:
    payload = json.loads(REQUEST_FIXTURE.read_text(encoding="utf-8"))
    return ExtractionRequest.model_validate(payload)


def test_prepared_request_hides_request_and_prompt_and_is_frozen() -> None:
    request = make_request()
    request_marker = request.transcript.segments[0].text
    prompt_marker = "PRIVATE-PROMPT-CANARY"
    rendered = RenderedPrompt(
        provider_request=ProviderRequest(
            messages=[ProviderMessage(role="user", content=prompt_marker)],
            structured_output_mode="json_object",
        ),
        prompt_version="extract-v1.0",
        candidate_schema_version="candidate-v1",
    )
    prepared = PreparedRequest(request=request, rendered_prompt=rendered)

    assert is_dataclass(prepared)
    assert prepared.request is request
    assert prepared.rendered_prompt is rendered
    assert request_marker not in repr(prepared)
    assert prompt_marker not in repr(prepared)
    assert {item.name for item in fields(prepared)} == {"request", "rendered_prompt"}
    with pytest.raises(FrozenInstanceError):
        prepared.request = request  # type: ignore[misc]


def test_prepared_extraction_hides_candidate_and_has_no_verification_state() -> None:
    request = make_request()
    candidate_marker = "PRIVATE-CANDIDATE-CANARY"
    candidate = SummaryActionsCandidate.model_validate(
        {
            "meeting_summary": {
                "overview": candidate_marker,
                "key_topics": [],
                "source_segment_ids": ["seg-a1"],
            },
            "action_items": None,
        }
    )
    usage = ProviderUsage(input_tokens=18, output_tokens=7)
    prepared = PreparedExtraction(
        request=request,
        candidate=candidate,
        prompt_version="extract-v1.0",
        candidate_schema_version="candidate-v1",
        model_id="synthetic-test-model",
        token_usage=usage,
    )

    assert is_dataclass(prepared)
    assert candidate_marker not in repr(prepared)
    assert request.transcript.segments[0].text not in repr(prepared)
    assert not hasattr(prepared, "verified")
    assert not hasattr(prepared, "evidence_prompt_version")
    assert prepared.provider is None
    assert prepared.token_usage is usage
    assert prepared.started_at is None
    assert prepared.completed_at is None
    assert {item.name for item in fields(prepared)} == {
        "request",
        "candidate",
        "prompt_version",
        "candidate_schema_version",
        "model_id",
        "provider",
        "token_usage",
        "started_at",
        "completed_at",
    }
    with pytest.raises(FrozenInstanceError):
        prepared.model_id = "another-model"  # type: ignore[misc]
