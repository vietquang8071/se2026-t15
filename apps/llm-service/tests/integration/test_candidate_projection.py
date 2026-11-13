"""Offline end-to-end tests from provider candidate through projection."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
from app.main import create_app
from app.providers.models import ProviderResult, ProviderUsage
from app.schemas.errors import ErrorEnvelope
from app.schemas.request import ExtractionRequest
from app.services.extraction import UnconfiguredExtractionService
from app.services.models import PreparedExtraction
from app.services.orchestration import CandidateExtractionOrchestrator
from app.services.preflight import ExtractionPreflight
from app.services.projection import ExtractionProjector, ProjectedExtraction
from fakes.provider import FakeProvider


SERVICE_ROOT = Path(__file__).parents[2]
REQUEST_FIXTURE = SERVICE_ROOT / "tests" / "fixtures" / "requests" / "summary_actions_request.json"
TEST_TOKEN = "group-c-integration-token-do-not-log"


def make_request(modules: tuple[str, ...]) -> ExtractionRequest:
    payload = json.loads(REQUEST_FIXTURE.read_text(encoding="utf-8"))
    payload["extraction"]["requested_modules"] = list(modules)
    return ExtractionRequest.model_validate(payload)


def summary_candidate() -> dict[str, object]:
    return {
        "overview": "Tổng hợp từ candidate.",
        "key_topics": [
            {
                "topic": "Tiến độ",
                "brief_discussion": "Nhóm rà soát tiến độ.",
                "source_segment_ids": ["unknown-topic-source"],
            }
        ],
        "source_segment_ids": ["unknown-summary-source"],
    }


def action_candidate(*, task: str = "Gửi bản ghi chú") -> dict[str, object]:
    return {
        "task": task,
        "owner": None,
        "raw_due_expression": "thứ Sáu tuần sau",
        "priority": None,
        "context": None,
        "source_segment_ids": ["unknown-action-source"],
    }


def provider_result(
    *,
    summary: dict[str, object] | None,
    actions: list[dict[str, object]] | None,
) -> ProviderResult:
    return ProviderResult(
        content=json.dumps(
            {"meeting_summary": summary, "action_items": actions},
            ensure_ascii=False,
        ),
        model_id="offline-projection-model",
        finish_reason="stop",
        usage=ProviderUsage(input_tokens=75, output_tokens=21),
    )


def run_pipeline(
    modules: tuple[str, ...],
    *,
    summary: dict[str, object] | None,
    actions: list[dict[str, object]] | None,
) -> tuple[ProjectedExtraction, FakeProvider]:
    request = make_request(modules)
    provider = FakeProvider(result=provider_result(summary=summary, actions=actions))
    orchestrator = CandidateExtractionOrchestrator(
        provider=provider,
        preflight=ExtractionPreflight(),
        provider_name="offline-projection-provider",
    )
    prepared = asyncio.run(orchestrator.run(request))
    projected = ExtractionProjector().project(prepared)
    return projected, provider


@pytest.mark.parametrize(
    ("modules", "summary", "actions", "expected_summary", "expected_actions"),
    [
        (("meeting_summary",), summary_candidate(), None, True, None),
        (("action_items",), None, [action_candidate()], False, 1),
        (
            ("meeting_summary", "action_items"),
            summary_candidate(),
            [action_candidate()],
            True,
            1,
        ),
        (("action_items",), None, [], False, 0),
    ],
    ids=["summary-only", "actions-only", "combined", "empty-actions"],
)
def test_full_offline_pipeline_projects_requested_module_variants(
    modules: tuple[str, ...],
    summary: dict[str, object] | None,
    actions: list[dict[str, object]] | None,
    expected_summary: bool,
    expected_actions: int | None,
) -> None:
    projected, provider = run_pipeline(modules, summary=summary, actions=actions)

    assert isinstance(projected, ProjectedExtraction)
    assert (projected.meeting_summary is not None) is expected_summary
    if expected_actions is None:
        assert projected.action_items is None
    else:
        assert projected.action_items is not None
        assert len(projected.action_items) == expected_actions
    assert len(provider.requests) == 1
    assert provider.requests[0].structured_output_mode == "json_object"


def test_projection_preserves_request_candidate_provider_metadata_and_unknown_sources() -> None:
    projected, provider = run_pipeline(
        ("meeting_summary", "action_items"),
        summary=summary_candidate(),
        actions=[action_candidate()],
    )
    extraction: PreparedExtraction = projected.prepared_extraction

    assert extraction.request.meeting.title == "Planning"
    assert extraction.prompt_version == "extract-v1.0"
    assert extraction.candidate_schema_version == "candidate-v1"
    assert extraction.provider == "offline-projection-provider"
    assert extraction.model_id == "offline-projection-model"
    assert extraction.token_usage == ProviderUsage(input_tokens=75, output_tokens=21)
    assert projected.meeting_summary is not None
    assert projected.meeting_summary.candidate.source_segment_ids == [
        "unknown-summary-source"
    ]
    assert projected.meeting_summary.candidate.key_topics[0].source_segment_ids == [
        "unknown-topic-source"
    ]
    assert projected.action_items is not None
    action = projected.action_items[0]
    assert action.source_segment_ids == ["unknown-action-source"]
    assert action.raw_due_expression == "thứ Sáu tuần sau"
    assert action.owner is None
    assert action.priority is None
    assert not hasattr(action, "source_timestamp")
    assert len(provider.requests) == 1


def test_projection_does_not_call_provider_or_mark_candidate_verified() -> None:
    projected, provider = run_pipeline(
        ("action_items",),
        summary=None,
        actions=[action_candidate()],
    )
    requests_before_projection_repeat = len(provider.requests)

    repeated = ExtractionProjector().project(projected.prepared_extraction)

    assert len(provider.requests) == requests_before_projection_repeat == 1
    assert not hasattr(repeated, "verified")
    assert not hasattr(repeated, "evidence_prompt_version")
    assert repeated.prepared_extraction is projected.prepared_extraction


def test_fastapi_remains_fail_closed_without_projection_wiring() -> None:
    settings = Settings(
        llm_service_token=SecretStr(TEST_TOKEN),
        openrouter_api_key=None,
    )
    app = create_app(settings=settings)
    assert isinstance(app.state.extraction_service, UnconfiguredExtractionService)
    request_payload = json.loads(REQUEST_FIXTURE.read_text(encoding="utf-8"))

    with TestClient(app) as client:
        health_response = client.get("/health")
        extraction_response = client.post(
            "/v1/extractions",
            json=request_payload,
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )

    assert health_response.status_code == 200
    assert extraction_response.status_code == 503
    error = ErrorEnvelope.model_validate(extraction_response.json())
    assert error.code == "PROVIDER_CONFIGURATION_ERROR"
    assert TEST_TOKEN not in extraction_response.text

