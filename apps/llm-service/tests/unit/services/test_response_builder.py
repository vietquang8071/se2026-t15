"""Verified-only public response construction tests."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.providers.models import ProviderUsage
from app.schemas.candidates import SummaryActionsCandidate
from app.schemas.request import ExtractionRequest
from app.services.models import PreparedExtraction
from app.services.orchestration import CandidateExtractionOrchestrator
from app.services.preflight import (
    ExtractionPreflight,
    SummaryDurationNotRepresentableError,
)
from app.services.projection import ExtractionProjector
from app.services.response_builder import ResponseBuilder
from app.services.source_validation import SourceValidator
from app.services.temporal_safeguards import TemporalReviewProcessor
from app.services.validation_models import (
    EvidenceVerifiedExtraction,
    ResponseConstructionFailure,
    VerificationMetadata,
    VerificationStatus,
    VerificationVerdict,
)
from fakes.provider import FakeProvider
from app.providers.models import ProviderResult


REQUEST_FIXTURE = Path(__file__).parents[2] / "fixtures/requests/summary_actions_request.json"


def make_request(modules: tuple[str, ...] = ("meeting_summary", "action_items"), *, short: bool = False):
    payload = json.loads(REQUEST_FIXTURE.read_text(encoding="utf-8"))
    payload["extraction"]["requested_modules"] = list(modules)
    if short:
        payload["meeting"]["duration_seconds"] = 0.1
        payload["transcript"]["segments"] = [
            {"id": "seg-short", "start": 0.0, "end": 0.05, "speaker_id": None, "text": "Gửi ghi chú."}
        ]
    return ExtractionRequest.model_validate(payload)


def summary_candidate():
    return {
        "overview": "Nhóm rà soát tiến độ và ghi nhận cam kết gửi ghi chú.",
        "key_topics": [
            {
                "topic": "Tiến độ",
                "brief_discussion": "Nhóm rà soát tiến độ hiện tại.",
                "source_segment_ids": ["seg-a2"],
            }
        ],
        "source_segment_ids": ["seg-a2", "seg-a1"],
    }


def action_candidate(task: str, source_id: str):
    return {
        "task": task,
        "owner": "Alex",
        "raw_due_expression": None,
        "priority": None,
        "context": None,
        "source_segment_ids": [source_id],
    }


def make_validated(
    modules: tuple[str, ...] = ("meeting_summary", "action_items"),
    *,
    actions: list[dict[str, object]] | None = None,
    extraction_usage: ProviderUsage | None = ProviderUsage(input_tokens=10, output_tokens=5),
    evidence_usage: ProviderUsage | None = ProviderUsage(input_tokens=7, output_tokens=3),
    evidence_prompt_version: str = "evidence-v1.0",
    short: bool = False,
):
    request = make_request(modules, short=short)
    candidate = SummaryActionsCandidate.model_validate(
        {
            "meeting_summary": summary_candidate() if "meeting_summary" in modules else None,
            "action_items": (actions or []) if "action_items" in modules else None,
        }
    )
    started = datetime.now(timezone.utc) - timedelta(seconds=2)
    prepared = PreparedExtraction(
        request=request,
        candidate=candidate,
        prompt_version="extract-v1.0",
        candidate_schema_version="candidate-v1",
        model_id="response-test-model",
        provider="response-test-provider",
        token_usage=extraction_usage,
        started_at=started,
        completed_at=started + timedelta(milliseconds=20),
    )
    projected = ExtractionProjector().project(prepared)
    source = SourceValidator().validate(projected)
    verdicts = tuple(
        VerificationVerdict(
            request_id=claim.request_id,
            transcript_revision_id=claim.transcript_revision_id,
            claim_id=claim.claim_id,
            status=VerificationStatus.SUPPORTED,
        )
        for claim in source.claims
    )
    evidence = EvidenceVerifiedExtraction(
        source_validated=source,
        verdicts=verdicts,
        metadata=VerificationMetadata(
            provider="response-test-provider",
            model_id="response-test-model",
            prompt_version=evidence_prompt_version,
            token_usage=evidence_usage,
            started_at=started + timedelta(milliseconds=30),
            completed_at=started + timedelta(milliseconds=50),
        ),
    )
    return request, TemporalReviewProcessor().process(evidence)


@pytest.mark.parametrize(
    "modules",
    [
        ("meeting_summary",),
        ("action_items",),
        ("meeting_summary", "action_items"),
    ],
    ids=["summary-only", "actions-only", "summary-and-actions"],
)
def test_response_preserves_requested_and_unrequested_module_states(modules):
    request, validated = make_validated(modules)

    response = ResponseBuilder().build(validated)

    assert response.requested_modules == list(modules)
    assert response.modules.meeting_summary is not None if "meeting_summary" in modules else response.modules.meeting_summary is None
    assert response.modules.action_items is not None if "action_items" in modules else response.modules.action_items is None
    assert response.modules.decision_log is None
    assert response.modules.open_issues is None
    assert response.modules.follow_up_items is None
    assert response.modules.timeline_events is None
    assert response.request_id == request.request_id


def test_verified_empty_actions_remain_an_empty_list():
    _, validated = make_validated(("action_items",), actions=[])

    response = ResponseBuilder().build(validated)

    assert response.modules.action_items == []


def test_action_items_sort_by_source_time_then_receive_response_local_ids():
    _, validated = make_validated(
        ("action_items",),
        actions=[action_candidate("Later task", "seg-a2"), action_candidate("Earlier task", "seg-a1")],
    )

    items = ResponseBuilder().build(validated).modules.action_items

    assert [(item.id, item.task, item.source_timestamp) for item in items] == [
        ("ACT-001", "Earlier task", "00:00:12.500"),
        ("ACT-002", "Later task", "00:00:18.300"),
    ]


def test_summary_metadata_is_request_derived_and_processing_usage_is_aggregated():
    request, validated = make_validated(("meeting_summary", "action_items"))

    response = ResponseBuilder().build(validated)

    assert response.modules.meeting_summary.title == request.meeting.title
    assert response.modules.meeting_summary.date == request.meeting.anchor_date
    assert response.modules.meeting_summary.participants == ["Alex"]
    assert response.modules.meeting_summary.duration_minutes == 0.5
    assert response.processing.provider == "response-test-provider"
    assert response.processing.model_id == "response-test-model"
    assert response.processing.prompt_version == "extract-v1.0"
    assert response.processing.evidence_prompt_version == "evidence-v1.0"
    assert response.processing.token_usage.input_tokens == 17
    assert response.processing.token_usage.output_tokens == 8
    assert response.processing.started_at.tzinfo == timezone.utc
    assert response.processing.completed_at >= response.processing.started_at


@pytest.mark.parametrize(
    "usage_pair",
    [(None, ProviderUsage(input_tokens=1, output_tokens=1)), (ProviderUsage(input_tokens=1, output_tokens=1), None)],
)
def test_partial_token_usage_is_not_fabricated(usage_pair):
    _, validated = make_validated(
        ("action_items",),
        extraction_usage=usage_pair[0],
        evidence_usage=usage_pair[1],
    )

    assert ResponseBuilder().build(validated).processing.token_usage is None


def test_missing_evidence_prompt_metadata_fails_closed():
    _, validated = make_validated(("action_items",), evidence_prompt_version="")

    with pytest.raises(ResponseConstructionFailure):
        ResponseBuilder().build(validated)


def test_too_short_summary_is_rejected_before_provider_call_but_actions_are_allowed():
    summary_request = make_request(("meeting_summary",), short=True)
    provider = FakeProvider(
        result=ProviderResult(
            content='{"meeting_summary":null,"action_items":null}',
            model_id="unused",
            finish_reason="stop",
            usage=None,
        )
    )
    orchestrator = CandidateExtractionOrchestrator(
        provider=provider,
        preflight=ExtractionPreflight(),
        provider_name="fake-provider",
    )

    with pytest.raises(SummaryDurationNotRepresentableError):
        asyncio.run(orchestrator.run(summary_request))
    assert provider.requests == []

    assert ExtractionPreflight().prepare(make_request(("action_items",), short=True))


def test_builder_rejects_non_validated_input():
    _, validated = make_validated(("action_items",))
    with pytest.raises(ResponseConstructionFailure):
        ResponseBuilder().build(
            validated.evidence_verified.source_validated.projected  # type: ignore[arg-type]
        )


def test_source_validated_state_rejects_corrupted_meeting_metadata():
    _, validated = make_validated(("meeting_summary",))
    evidence = validated.evidence_verified
    source = evidence.source_validated
    projected = replace(
        source.projected,
        meeting_summary=replace(source.projected.meeting_summary, title="Wrong meeting"),
    )

    with pytest.raises(ValueError, match="metadata does not match"):
        replace(source, projected=projected)


def test_builder_rejects_source_id_outside_originating_transcript():
    _, validated = make_validated(("action_items",), actions=[action_candidate("Task", "seg-a1")])
    validated.action_items[0].source_segment_ids[0] = "not-in-transcript"

    with pytest.raises(ResponseConstructionFailure):
        ResponseBuilder().build(validated)


def test_validated_state_rejects_unverified_optional_field_retention():
    action = action_candidate("Task", "seg-a1")
    action["priority"] = "High"
    _, validated = make_validated(("action_items",), actions=[action])
    evidence = validated.evidence_verified
    bad_verdicts = tuple(
        replace(verdict, status=VerificationStatus.UNSUPPORTED)
        if verdict.claim_id == "actions[0].priority"
        else verdict
        for verdict in evidence.verdicts
    )
    unsupported_evidence = EvidenceVerifiedExtraction(
        source_validated=evidence.source_validated,
        verdicts=bad_verdicts,
        metadata=evidence.metadata,
    )

    with pytest.raises(ValueError, match="unverified field"):
        replace(validated, evidence_verified=unsupported_evidence)


def test_validated_state_rejects_review_reasons_that_conflict_with_owner_state():
    _, validated = make_validated(("action_items",), actions=[action_candidate("Task", "seg-a1")])

    with pytest.raises(ValueError, match="Owner review state"):
        replace(validated, action_review_reasons=(("owner_unconfirmed",),))


def test_validated_state_rejects_temporal_sources_outside_action_sources():
    action = action_candidate("Task", "seg-a1")
    action["raw_due_expression"] = "2026-12-15"
    _, validated = make_validated(("action_items",), actions=[action])
    invalid_resolution = validated.action_due_resolutions[0].model_copy(
        update={"source_segment_ids": ["seg-a2"]}
    )

    with pytest.raises(ValueError, match="Temporal sources are outside"):
        replace(validated, action_due_resolutions=(invalid_resolution,))
