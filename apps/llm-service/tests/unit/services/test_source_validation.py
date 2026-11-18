"""Deterministic source-reference validation tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.schemas.candidates import SummaryActionsCandidate
from app.schemas.request import ExtractionRequest
from app.services.models import PreparedExtraction
from app.services.projection import ExtractionProjector
from app.services.source_validation import SourceValidator
from app.services.validation_models import SourceValidationFailure


REQUEST_FIXTURE = Path(__file__).parents[2] / "fixtures/requests/summary_actions_request.json"


def make_projected(candidate_data: dict[str, object], *, request_id: str = "req-source"):
    payload = json.loads(REQUEST_FIXTURE.read_text(encoding="utf-8"))
    payload["request_id"] = request_id
    request = ExtractionRequest.model_validate(payload)
    candidate = SummaryActionsCandidate.model_validate(candidate_data)
    prepared = PreparedExtraction(
        request=request,
        candidate=candidate,
        prompt_version="extract-v1.0",
        candidate_schema_version="candidate-v1",
        model_id="test-model",
        provider="test-provider",
    )
    return ExtractionProjector().project(prepared)


def summary(sources: list[str] | None = None, topics: list[dict[str, object]] | None = None):
    return {
        "overview": "Nhóm rà soát tiến độ.",
        "key_topics": topics or [],
        "source_segment_ids": sources or ["seg-a1", "seg-a2"],
    }


def topic(sources: list[str] | None = None):
    return {
        "topic": "Tiến độ",
        "brief_discussion": "Nhóm rà soát tiến độ hiện tại.",
        "source_segment_ids": sources or ["seg-a2"],
    }


def action(sources: list[str] | None = None):
    return {
        "task": "Gửi bản ghi chú",
        "owner": "Alex",
        "raw_due_expression": "thứ Sáu này",
        "priority": None,
        "context": None,
        "source_segment_ids": sources or ["seg-a1"],
    }


def test_valid_references_are_sorted_by_time_and_tie_break_by_original_order():
    projected = make_projected(
        {
            "meeting_summary": summary(["seg-a2", "seg-a1"], [topic(["seg-a2", "seg-a1"])]),
            "action_items": [action(["seg-a2", "seg-a1"])],
        }
    )

    result = SourceValidator().validate(projected)

    assert result.transcript_revision_id == "transcript-r1"
    assert next(claim for claim in result.claims if claim.claim_id == "summary.overview").source_segment_ids == ("seg-a1", "seg-a2")
    assert next(claim for claim in result.claims if claim.claim_id == "summary.key_topics[0]").source_segment_ids == ("seg-a1", "seg-a2")
    assert next(claim for claim in result.claims if claim.claim_id == "actions[0].task").source_segment_ids == ("seg-a1", "seg-a2")


def test_unknown_summary_source_fails_without_repair():
    projected = make_projected(
        {"meeting_summary": summary(["missing" ]), "action_items": []}
    )

    with pytest.raises(SourceValidationFailure):
        SourceValidator().validate(projected)


def test_duplicate_source_ids_are_rejected_even_if_candidate_was_constructed_unsafely():
    projected = make_projected(
        {"meeting_summary": summary(), "action_items": [action()]}
    )
    projected.prepared_extraction.candidate.meeting_summary.source_segment_ids = ["seg-a1", "seg-a1"]

    with pytest.raises(SourceValidationFailure, match="duplicate"):
        SourceValidator().validate(projected)


def test_source_index_uses_transcript_order_for_equal_timestamps():
    projected = make_projected(
        {"meeting_summary": summary(["seg-a2", "seg-a1"]), "action_items": []}
    )
    request = projected.prepared_extraction.request
    payload = request.model_dump(mode="json")
    payload["transcript"]["segments"][1]["start"] = payload["transcript"]["segments"][0]["start"]
    tied_request = ExtractionRequest.model_validate(payload)
    from dataclasses import replace

    tied_projected = replace(
        projected,
        prepared_extraction=replace(projected.prepared_extraction, request=tied_request),
    )

    result = SourceValidator().validate(tied_projected)

    assert result.claims[0].source_segment_ids == ("seg-a1", "seg-a2")


def test_invalid_topic_can_be_discarded_while_valid_summary_survives():
    projected = make_projected(
        {"meeting_summary": summary(topics=[topic(["bad-topic-source"])]), "action_items": []}
    )

    result = SourceValidator().validate(projected)

    assert [claim.claim_id for claim in result.claims] == ["summary.overview", "actions.absence"]


def test_requests_with_overlapping_segment_ids_keep_separate_request_context():
    projected_a = make_projected({"meeting_summary": summary(), "action_items": []}, request_id="request-a")
    projected_b = make_projected({"meeting_summary": summary(), "action_items": []}, request_id="request-b")

    result_a = SourceValidator().validate(projected_a)
    result_b = SourceValidator().validate(projected_b)

    assert result_a.request_id == "request-a"
    assert result_b.request_id == "request-b"
    assert all(claim.request_id == "request-a" for claim in result_a.claims)
    assert all(claim.request_id == "request-b" for claim in result_b.claims)
