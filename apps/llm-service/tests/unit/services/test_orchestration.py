"""Unit tests for unverified candidate extraction orchestration."""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from pathlib import Path

import pytest

from app.parsing.candidates import CandidateFormatError, CandidateRequestMismatchError
from app.providers.errors import (
    ProviderConfigurationError,
    ProviderFailureError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.providers.models import ProviderResult, ProviderUsage
from app.schemas.request import ExtractionRequest
from app.services.preflight import ExtractionPreflight, UnsupportedExtractionCapabilityError
from app.services.orchestration import CandidateExtractionOrchestrator
from fakes.provider import FakeProvider


REQUEST_FIXTURE = (
    Path(__file__).parents[2] / "fixtures" / "requests" / "summary_actions_request.json"
)


def make_request(
    modules: tuple[str, ...] = ("meeting_summary", "action_items"),
    *,
    request_id: str = "req-orchestration-01",
    transcript_segments: list[dict[str, object]] | None = None,
) -> ExtractionRequest:
    payload = json.loads(REQUEST_FIXTURE.read_text(encoding="utf-8"))
    payload["request_id"] = request_id
    payload["extraction"]["requested_modules"] = list(modules)
    if transcript_segments is not None:
        payload["transcript"]["segments"] = transcript_segments
    return ExtractionRequest.model_validate(payload)


def summary_candidate(
    *, overview: str = "Cuộc họp rà soát tiến độ.", source_ids: list[str] | None = None
) -> dict[str, object]:
    return {
        "overview": overview,
        "key_topics": [],
        "source_segment_ids": source_ids or ["seg-a2"],
    }


def action_item(
    *,
    task: str = "Gửi bản ghi chú",
    owner: str | None = "Alex",
    deadline: str | None = "thứ Sáu này",
    priority: str | None = None,
    source_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "task": task,
        "owner": owner,
        "raw_due_expression": deadline,
        "priority": priority,
        "context": None,
        "source_segment_ids": source_ids or ["seg-a1"],
    }


def candidate_payload(
    *,
    summary: dict[str, object] | None = None,
    actions: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {"meeting_summary": summary, "action_items": actions}


def encoded(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def provider_result(
    payload: dict[str, object] | str,
    *,
    model_id: str = "offline-model",
    usage: ProviderUsage | None = None,
) -> ProviderResult:
    content = payload if isinstance(payload, str) else encoded(payload)
    return ProviderResult(
        content=content,
        model_id=model_id,
        finish_reason="stop",
        usage=usage,
    )


def make_orchestrator(provider: object) -> CandidateExtractionOrchestrator:
    return CandidateExtractionOrchestrator(
        provider=provider,
        preflight=ExtractionPreflight(),
        provider_name="offline-test-provider",
    )


def test_summary_only_run_returns_parsed_unverified_candidate() -> None:
    request = make_request(("meeting_summary",))
    provider = FakeProvider(
        result=provider_result(
            candidate_payload(summary=summary_candidate(), actions=None)
        )
    )

    result = asyncio.run(make_orchestrator(provider).run(request))

    assert result.request is request
    assert result.candidate.meeting_summary is not None
    assert result.candidate.meeting_summary.overview == "Cuộc họp rà soát tiến độ."
    assert result.candidate.action_items is None
    assert len(provider.requests) == 1


def test_actions_only_run_preserves_nullable_fields_and_raw_deadline() -> None:
    request = make_request(("action_items",))
    provider = FakeProvider(
        result=provider_result(
            candidate_payload(
                summary=None,
                actions=[action_item(owner=None, deadline="thứ Sáu này")],
            )
        )
    )

    result = asyncio.run(make_orchestrator(provider).run(request))

    assert result.candidate.meeting_summary is None
    assert result.candidate.action_items is not None
    parsed_action = result.candidate.action_items[0]
    assert parsed_action.raw_due_expression == "thứ Sáu này"
    assert parsed_action.source_segment_ids == ["seg-a1"]
    assert parsed_action.owner is None
    assert parsed_action.priority is None
    assert len(provider.requests) == 1


def test_summary_and_actions_run_once_and_preserve_both_modules() -> None:
    class CountingPreflight(ExtractionPreflight):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def prepare(self, request: ExtractionRequest):
            self.calls += 1
            return super().prepare(request)

    request = make_request()
    preflight = CountingPreflight()
    provider = FakeProvider(
        result=provider_result(
            candidate_payload(
                summary=summary_candidate(source_ids=["seg-a1", "seg-a2"]),
                actions=[action_item()],
            )
        )
    )
    orchestrator = CandidateExtractionOrchestrator(
        provider=provider,
        preflight=preflight,
        provider_name="offline-test-provider",
    )

    result = asyncio.run(orchestrator.run(request))

    assert preflight.calls == 1
    assert len(provider.requests) == 1
    assert result.request is request
    assert result.candidate.meeting_summary is not None
    assert result.candidate.meeting_summary.source_segment_ids == ["seg-a1", "seg-a2"]
    assert result.candidate.action_items is not None
    assert result.candidate.action_items[0].source_segment_ids == ["seg-a1"]


def test_empty_requested_actions_is_preserved_as_empty_list() -> None:
    request = make_request(("action_items",))
    provider = FakeProvider(
        result=provider_result(candidate_payload(summary=None, actions=[]))
    )

    result = asyncio.run(make_orchestrator(provider).run(request))

    assert result.candidate.meeting_summary is None
    assert result.candidate.action_items == []
    assert len(provider.requests) == 1


@pytest.mark.parametrize(
    "modules",
    [("decision_log",), ("action_items", "open_issues")],
    ids=["unsupported-only", "mixed-supported-and-unsupported"],
)
def test_unsupported_modules_fail_before_provider_call(
    modules: tuple[str, ...],
) -> None:
    provider = FakeProvider(result=provider_result("{}"))

    with pytest.raises(UnsupportedExtractionCapabilityError):
        asyncio.run(make_orchestrator(provider).run(make_request(modules)))

    assert provider.requests == []


@pytest.mark.parametrize(
    "provider_error",
    [
        ProviderTimeoutError(),
        ProviderRateLimitError(retry_after_seconds=12.0),
        ProviderConfigurationError(),
        ProviderFailureError(),
        ProviderUnavailableError(),
    ],
    ids=["timeout", "rate-limit", "configuration", "failure", "unavailable"],
)
def test_provider_errors_propagate_unchanged_without_retry(
    provider_error: Exception,
) -> None:
    provider = FakeProvider(error=provider_error)

    with pytest.raises(type(provider_error)) as exc_info:
        asyncio.run(make_orchestrator(provider).run(make_request(("action_items",))))

    assert exc_info.value is provider_error
    assert len(provider.requests) == 1
    if isinstance(provider_error, ProviderRateLimitError):
        assert exc_info.value.retry_after_seconds == 12.0


def test_malformed_candidate_json_propagates_format_error_without_retry() -> None:
    provider = FakeProvider(result=provider_result("{ malformed json"))

    with pytest.raises(CandidateFormatError):
        asyncio.run(make_orchestrator(provider).run(make_request(("action_items",))))

    assert len(provider.requests) == 1


def test_candidate_schema_failure_propagates_without_repair() -> None:
    invalid_candidate = {"meeting_summary": None, "action_items": [{"task": "Thiếu field"}]}
    provider = FakeProvider(result=provider_result(invalid_candidate))

    with pytest.raises(CandidateFormatError):
        asyncio.run(make_orchestrator(provider).run(make_request(("action_items",))))

    assert len(provider.requests) == 1


@pytest.mark.parametrize(
    ("modules", "candidate"),
    [
        (("meeting_summary",), candidate_payload(summary=None, actions=None)),
        (("action_items",), candidate_payload(summary=None, actions=None)),
        (
            ("action_items",),
            candidate_payload(summary=summary_candidate(), actions=None),
        ),
    ],
    ids=["missing-summary", "missing-actions", "unrequested-summary"],
)
def test_candidate_module_mismatches_propagate_without_partial_result(
    modules: tuple[str, ...], candidate: dict[str, object]
) -> None:
    provider = FakeProvider(result=provider_result(candidate))

    with pytest.raises(CandidateRequestMismatchError):
        asyncio.run(make_orchestrator(provider).run(make_request(modules)))

    assert len(provider.requests) == 1


def test_success_populates_actual_processing_metadata_in_utc() -> None:
    request = make_request(("meeting_summary",))
    usage = ProviderUsage(input_tokens=123, output_tokens=45)
    generation = provider_result(
        candidate_payload(summary=summary_candidate(), actions=None),
        model_id="vendor/model-7",
        usage=usage,
    )
    provider = FakeProvider(result=generation)
    orchestrator = make_orchestrator(provider)

    result = asyncio.run(orchestrator.run(request))

    assert result.prompt_version == "extract-v1.0"
    assert result.candidate_schema_version == "candidate-v1"
    assert result.model_id == generation.model_id
    assert result.provider == "offline-test-provider"
    assert result.token_usage is generation.usage
    assert result.started_at is not None
    assert result.completed_at is not None
    assert result.started_at.tzinfo is not None
    assert result.completed_at.tzinfo is not None
    assert result.started_at.utcoffset() == timedelta(0)
    assert result.completed_at.utcoffset() == timedelta(0)
    assert result.started_at <= result.completed_at


def test_missing_provider_usage_remains_none() -> None:
    provider = FakeProvider(
        result=provider_result(
            candidate_payload(summary=None, actions=[action_item()]),
            usage=None,
        )
    )

    result = asyncio.run(make_orchestrator(provider).run(make_request(("action_items",))))

    assert result.model_id == "offline-model"
    assert result.token_usage is None
    assert result.started_at is not None
    assert result.completed_at is not None


def test_cancellation_propagates_without_retry_or_completed_result() -> None:
    class BlockingProvider:
        def __init__(self) -> None:
            self.calls = 0
            self.entered = asyncio.Event()

        async def generate(self, provider_request):
            self.calls += 1
            self.entered.set()
            await asyncio.Event().wait()

    async def cancel_during_generation() -> None:
        provider = BlockingProvider()
        task = asyncio.create_task(
            make_orchestrator(provider).run(make_request(("action_items",)))
        )
        await provider.entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert provider.calls == 1

    asyncio.run(cancel_during_generation())
