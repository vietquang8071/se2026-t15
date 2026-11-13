"""Unit tests for deterministic, unverified extraction projection."""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from datetime import date
from pathlib import Path

import pytest

from app.schemas.candidates import SummaryActionsCandidate
from app.schemas.request import ExtractionRequest
from app.services.models import PreparedExtraction
from app.services.projection import (
    ExtractionProjector,
    ProjectedExtraction,
    ProjectedMeetingSummary,
)


REQUEST_FIXTURE = (
    Path(__file__).parents[2] / "fixtures" / "requests" / "summary_actions_request.json"
)


def make_request(
    modules: tuple[str, ...] = ("meeting_summary", "action_items"),
    *,
    duration_seconds: float | None = None,
) -> ExtractionRequest:
    payload = json.loads(REQUEST_FIXTURE.read_text(encoding="utf-8"))
    payload["extraction"]["requested_modules"] = list(modules)
    if duration_seconds is not None:
        payload["meeting"]["duration_seconds"] = duration_seconds
        if duration_seconds < 22.0:
            payload["transcript"]["segments"] = [
                {
                    "id": "seg-short",
                    "start": 0.0,
                    "end": duration_seconds / 2,
                    "speaker_id": None,
                    "text": "Cuộc họp ngắn.",
                }
            ]
    return ExtractionRequest.model_validate(payload)


def summary_payload(
    *,
    overview: str = "Cuộc họp rà soát tiến độ.",
    source_ids: list[str] | None = None,
    key_topics: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "overview": overview,
        "key_topics": key_topics if key_topics is not None else [],
        "source_segment_ids": source_ids or ["unknown-summary-source"],
    }


def action_payload(
    *,
    task: str = "Hoàn thành báo cáo",
    owner: str | None = "Nam",
    due_expression: str | None = None,
    priority: str | None = "High",
    context: str | None = "Báo cáo tiến độ",
    source_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "task": task,
        "owner": owner,
        "raw_due_expression": due_expression,
        "priority": priority,
        "context": context,
        "source_segment_ids": source_ids or ["unknown-action-source"],
    }


def make_candidate(
    *,
    summary: dict[str, object] | None = None,
    actions: list[dict[str, object]] | None = None,
) -> SummaryActionsCandidate:
    return SummaryActionsCandidate.model_validate(
        {
            "meeting_summary": summary,
            "action_items": actions,
        }
    )


def make_prepared(
    request: ExtractionRequest,
    candidate: SummaryActionsCandidate,
) -> PreparedExtraction:
    return PreparedExtraction(
        request=request,
        candidate=candidate,
        prompt_version="extract-v1.0",
        candidate_schema_version="candidate-v1",
        model_id="projection-test-model",
        provider="projection-test-provider",
    )


def test_summary_only_projects_request_metadata_and_candidate_content() -> None:
    request = make_request(("meeting_summary",))
    candidate = make_candidate(
        summary=summary_payload(overview="Nội dung tóm tắt từ candidate."),
        actions=None,
    )

    projected = ExtractionProjector().project(make_prepared(request, candidate))

    assert projected.meeting_summary is not None
    assert projected.action_items is None
    assert projected.meeting_summary.title == request.meeting.title
    assert projected.meeting_summary.date == request.meeting.anchor_date
    assert projected.meeting_summary.duration_minutes == 0.5
    assert projected.meeting_summary.participants == ("Alex",)
    assert projected.meeting_summary.candidate is candidate.meeting_summary
    assert projected.meeting_summary.candidate.overview == "Nội dung tóm tắt từ candidate."


def test_actions_only_projects_actions_without_creating_summary() -> None:
    request = make_request(("action_items",))
    candidate = make_candidate(summary=None, actions=[action_payload()])

    projected = ExtractionProjector().project(make_prepared(request, candidate))

    assert projected.meeting_summary is None
    assert projected.action_items is not None
    assert len(projected.action_items) == 1
    assert projected.action_items[0].task == "Hoàn thành báo cáo"


def test_combined_modules_preserve_content_and_originating_extraction() -> None:
    request = make_request()
    candidate = make_candidate(
        summary=summary_payload(),
        actions=[action_payload(task="Gửi bản ghi chú")],
    )
    extraction = make_prepared(request, candidate)

    projected = ExtractionProjector().project(extraction)

    assert projected.prepared_extraction is extraction
    assert projected.meeting_summary is not None
    assert projected.action_items is not None
    assert projected.meeting_summary.candidate is candidate.meeting_summary
    assert projected.action_items[0].task == "Gửi bản ghi chú"


@pytest.mark.parametrize(
    ("duration_seconds", "expected_minutes"),
    [(1234.0, 20.57), (0.1, 0.0)],
    ids=["rounded-to-two-decimals", "short-duration-rounds-to-zero"],
)
def test_meeting_metadata_uses_request_order_and_established_duration_rule(
    duration_seconds: float,
    expected_minutes: float,
) -> None:
    request = make_request(("meeting_summary",), duration_seconds=duration_seconds)
    request_payload = request.model_dump(mode="json")
    request_payload["meeting"]["participants"] = [
        {"id": "participant-mia", "display_name": "Mia", "speaker_ids": []},
        {"id": "participant-nam", "display_name": "Nam", "speaker_ids": []},
    ]
    request = ExtractionRequest.model_validate(request_payload)
    candidate = make_candidate(
        summary=summary_payload(overview="Generated content has no metadata fields."),
        actions=None,
    )

    projected = ExtractionProjector().project(make_prepared(request, candidate))

    assert projected.meeting_summary is not None
    assert projected.meeting_summary.title == request.meeting.title
    assert projected.meeting_summary.date == date.fromisoformat("2026-10-05")
    assert projected.meeting_summary.duration_minutes == expected_minutes
    assert projected.meeting_summary.participants == ("Mia", "Nam")


def test_key_topics_and_source_ids_keep_text_and_order() -> None:
    request = make_request(("meeting_summary",))
    topics = [
        {
            "topic": "Chủ đề thứ nhất",
            "brief_discussion": "Thảo luận thứ nhất.",
            "source_segment_ids": ["seg-z", "missing-topic-source"],
        },
        {
            "topic": "Chủ đề thứ hai",
            "brief_discussion": "Thảo luận thứ hai.",
            "source_segment_ids": ["seg-y"],
        },
    ]
    candidate = make_candidate(
        summary=summary_payload(
            source_ids=["missing-summary-source", "seg-z"],
            key_topics=topics,
        ),
        actions=None,
    )

    projected = ExtractionProjector().project(make_prepared(request, candidate))

    assert projected.meeting_summary is not None
    projected_candidate = projected.meeting_summary.candidate
    assert projected_candidate.source_segment_ids == ["missing-summary-source", "seg-z"]
    assert [topic.topic for topic in projected_candidate.key_topics] == [
        "Chủ đề thứ nhất",
        "Chủ đề thứ hai",
    ]
    assert [topic.brief_discussion for topic in projected_candidate.key_topics] == [
        "Thảo luận thứ nhất.",
        "Thảo luận thứ hai.",
    ]
    assert projected_candidate.key_topics[0].source_segment_ids == [
        "seg-z",
        "missing-topic-source",
    ]
    assert projected_candidate.key_topics[1].source_segment_ids == ["seg-y"]


def test_nullable_owner_and_priority_remain_none() -> None:
    request = make_request(("action_items",))
    candidate = make_candidate(
        summary=None,
        actions=[action_payload(owner=None, priority=None)],
    )

    projected = ExtractionProjector().project(make_prepared(request, candidate))

    assert projected.action_items is not None
    assert projected.action_items[0].owner is None
    assert projected.action_items[0].priority is None


def test_raw_relative_deadline_is_preserved_without_resolution() -> None:
    request = make_request(("action_items",))
    candidate = make_candidate(
        summary=None,
        actions=[action_payload(due_expression="thứ Sáu tuần sau")],
    )

    projected = ExtractionProjector().project(make_prepared(request, candidate))

    assert projected.action_items is not None
    action = projected.action_items[0]
    assert action.raw_due_expression == "thứ Sáu tuần sau"
    assert not hasattr(action, "due_date")
    assert not hasattr(action, "due_date_resolution")


def test_requested_empty_action_items_remain_empty_list() -> None:
    request = make_request(("action_items",))
    candidate = make_candidate(summary=None, actions=[])

    projected = ExtractionProjector().project(make_prepared(request, candidate))

    assert projected.action_items == []
    assert projected.action_items is not None


@pytest.mark.parametrize(
    ("modules", "summary", "actions"),
    [
        (("meeting_summary",), summary_payload(), None),
        (("action_items",), None, [action_payload()]),
    ],
    ids=["actions-unrequested", "summary-unrequested"],
)
def test_unrequested_module_remains_none(
    modules: tuple[str, ...],
    summary: dict[str, object] | None,
    actions: list[dict[str, object]] | None,
) -> None:
    request = make_request(modules)
    candidate = make_candidate(summary=summary, actions=actions)

    projected = ExtractionProjector().project(make_prepared(request, candidate))

    assert (projected.meeting_summary is None) == (summary is None)
    assert (projected.action_items is None) == (actions is None)


def test_unknown_source_ids_are_preserved_without_verification() -> None:
    request = make_request()
    candidate = make_candidate(
        summary=summary_payload(source_ids=["not-in-transcript-summary"]),
        actions=[action_payload(source_ids=["not-in-transcript-action"])],
    )

    projected = ExtractionProjector().project(make_prepared(request, candidate))

    assert projected.meeting_summary is not None
    assert projected.meeting_summary.candidate.source_segment_ids == [
        "not-in-transcript-summary"
    ]
    assert projected.action_items is not None
    assert projected.action_items[0].source_segment_ids == [
        "not-in-transcript-action"
    ]


def test_projection_does_not_mutate_request_candidate_or_transcript() -> None:
    request = make_request()
    candidate = make_candidate(
        summary=summary_payload(
            key_topics=[
                {
                    "topic": "Chủ đề",
                    "brief_discussion": "Trao đổi.",
                    "source_segment_ids": ["seg-topic"],
                }
            ]
        ),
        actions=[action_payload(source_ids=["seg-action"])],
    )
    request_before = request.model_dump(mode="json")
    candidate_before = candidate.model_dump(mode="json")
    extraction = make_prepared(request, candidate)

    projected = ExtractionProjector().project(extraction)

    assert request.model_dump(mode="json") == request_before
    assert candidate.model_dump(mode="json") == candidate_before
    assert [segment.id for segment in projected.prepared_extraction.request.transcript.segments] == [
        segment.id for segment in request.transcript.segments
    ]
    assert projected.action_items is not candidate.action_items
    assert projected.action_items is not None
    assert projected.action_items[0] is candidate.action_items[0]


def test_internal_projection_models_do_not_add_verification_or_artifact_fields() -> None:
    request = make_request()
    candidate = make_candidate(
        summary=summary_payload(overview="SUMMARY-CANARY"),
        actions=[action_payload(task="ACTION-CANARY")],
    )
    projected = ExtractionProjector().project(make_prepared(request, candidate))
    fields_by_model = {
        model.__name__: {item.name for item in fields(model)}
        for model in (ProjectedMeetingSummary, ProjectedExtraction)
    }

    assert is_dataclass(projected)
    assert fields_by_model["ProjectedMeetingSummary"] == {
        "title",
        "date",
        "duration_minutes",
        "participants",
        "candidate",
    }
    assert fields_by_model["ProjectedExtraction"] == {
        "prepared_extraction",
        "meeting_summary",
        "action_items",
    }
    assert "id" not in fields_by_model["ProjectedMeetingSummary"]
    assert "source_timestamp" not in fields_by_model["ProjectedExtraction"]
    assert "due_date" not in fields_by_model["ProjectedExtraction"]
    assert "needs_review" not in fields_by_model["ProjectedExtraction"]
    assert "evidence_prompt_version" not in fields_by_model["ProjectedExtraction"]
    assert "SUMMARY-CANARY" not in repr(projected)
    assert "ACTION-CANARY" not in repr(projected)


def test_repeated_projection_is_deterministic_and_preserves_provenance() -> None:
    request = make_request()
    candidate = make_candidate(
        summary=summary_payload(),
        actions=[action_payload(), action_payload(task="Kiểm tra kết quả")],
    )
    extraction = make_prepared(request, candidate)
    projector = ExtractionProjector()

    first = projector.project(extraction)
    second = projector.project(extraction)

    assert first == second
    assert first.prepared_extraction is extraction
    assert first.prepared_extraction.request is request
    assert first.prepared_extraction.candidate is candidate
    assert [item.task for item in first.action_items or []] == [
        "Hoàn thành báo cáo",
        "Kiểm tra kết quả",
    ]

