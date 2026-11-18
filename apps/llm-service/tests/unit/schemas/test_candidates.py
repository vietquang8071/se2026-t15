"""Structural validation tests for internal extraction candidates."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.request import ExtractionRequest
from app.schemas.candidates import (
    ActionItemCandidate,
    KeyTopicCandidate,
    MeetingSummaryCandidate,
    SummaryActionsCandidate,
    validate_candidate_for_request,
)


def summary_candidate() -> dict[str, Any]:
    return {
        "overview": "Cuộc họp rà soát tiến độ và ghi nhận cam kết gửi bản ghi chú.",
        "key_topics": [
            {
                "topic": "Rà soát tiến độ",
                "brief_discussion": "Nhóm rà lại tiến độ công việc hiện tại.",
                "source_segment_ids": ["seg-a2"],
            }
        ],
        "source_segment_ids": ["seg-a1", "seg-a2"],
    }


def action_item_candidate() -> dict[str, Any]:
    return {
        "task": "Gửi bản ghi chú",
        "owner": "Alex",
        "raw_due_expression": "thứ Sáu này",
        "priority": None,
        "context": None,
        "source_segment_ids": ["seg-a1"],
    }


def full_candidate() -> dict[str, Any]:
    return {
        "meeting_summary": summary_candidate(),
        "action_items": [action_item_candidate()],
    }


def request_fixture() -> ExtractionRequest:
    fixture_path = Path(__file__).parents[2] / "fixtures/requests/summary_actions_request.json"
    return ExtractionRequest.model_validate_json(fixture_path.read_text(encoding="utf-8"))


def test_valid_full_summary_and_actions_candidate_preserves_vietnamese() -> None:
    candidate = SummaryActionsCandidate.model_validate(full_candidate())

    assert candidate.meeting_summary is not None
    assert candidate.meeting_summary.overview == (
        "Cuộc họp rà soát tiến độ và ghi nhận cam kết gửi bản ghi chú."
    )
    assert candidate.meeting_summary.key_topics[0].brief_discussion == (
        "Nhóm rà lại tiến độ công việc hiện tại."
    )
    assert candidate.action_items is not None
    assert candidate.action_items[0].raw_due_expression == "thứ Sáu này"
    validate_candidate_for_request(candidate, request_fixture())


def test_valid_summary_only_candidate() -> None:
    candidate = SummaryActionsCandidate(
        meeting_summary=summary_candidate(), action_items=None
    )

    request = request_fixture()
    request.extraction.requested_modules = ["meeting_summary"]
    assert validate_candidate_for_request(candidate, request) is candidate


def test_valid_actions_only_candidate() -> None:
    candidate = SummaryActionsCandidate(
        meeting_summary=None, action_items=[action_item_candidate()]
    )

    request = request_fixture()
    request.extraction.requested_modules = ["action_items"]
    assert validate_candidate_for_request(candidate, request) is candidate


def test_requested_actions_may_be_empty() -> None:
    candidate = SummaryActionsCandidate(meeting_summary=None, action_items=[])
    request = request_fixture()
    request.extraction.requested_modules = ["action_items"]

    assert validate_candidate_for_request(candidate, request) is candidate


def test_key_topics_may_be_empty() -> None:
    summary = summary_candidate()
    summary["key_topics"] = []

    assert MeetingSummaryCandidate.model_validate(summary).key_topics == []


def test_action_item_nullable_fields_are_required_but_may_be_null() -> None:
    action = action_item_candidate()
    action.update(
        owner=None,
        raw_due_expression=None,
        priority=None,
        context=None,
    )

    candidate = ActionItemCandidate.model_validate(action)

    assert candidate.owner is None
    assert candidate.raw_due_expression is None
    assert candidate.priority is None
    assert candidate.context is None


def test_owner_sentinel_remains_structurally_valid() -> None:
    action = action_item_candidate()
    action["owner"] = "Unknown"

    assert ActionItemCandidate.model_validate(action).owner == "Unknown"


def test_multiple_source_references_are_preserved() -> None:
    action = action_item_candidate()
    action["source_segment_ids"] = ["seg-a1", "seg-a2"]

    assert ActionItemCandidate.model_validate(action).source_segment_ids == [
        "seg-a1",
        "seg-a2",
    ]


def test_syntactically_valid_source_reference_need_not_exist_in_request() -> None:
    action = action_item_candidate()
    action["source_segment_ids"] = ["not-in-transcript"]
    candidate = SummaryActionsCandidate(meeting_summary=None, action_items=[action])
    request = request_fixture()
    request.extraction.requested_modules = ["action_items"]

    assert validate_candidate_for_request(candidate, request) is candidate


def test_candidate_can_be_parsed_from_json() -> None:
    parsed = SummaryActionsCandidate.model_validate_json(
        json.dumps(full_candidate(), ensure_ascii=False)
    )

    assert parsed.model_dump() == full_candidate()


def test_candidate_json_schema_is_generated_with_required_fields_and_no_extras() -> None:
    schema = SummaryActionsCandidate.model_json_schema()

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"meeting_summary", "action_items"}
    properties = schema["$defs"]["ActionItemCandidate"]["properties"]
    assert set(properties) == {
        "task",
        "owner",
        "raw_due_expression",
        "priority",
        "context",
        "source_segment_ids",
    }
    assert set(schema["$defs"]["ActionItemCandidate"]["required"]) == set(properties)


@pytest.mark.parametrize("missing_field", ["meeting_summary", "action_items"])
def test_missing_root_fields_are_rejected(missing_field: str) -> None:
    data = full_candidate()
    del data[missing_field]

    with pytest.raises(ValidationError):
        SummaryActionsCandidate.model_validate(data)


@pytest.mark.parametrize(
    ("model", "data", "missing_field"),
    [
        (MeetingSummaryCandidate, summary_candidate(), "overview"),
        (MeetingSummaryCandidate, summary_candidate(), "source_segment_ids"),
        (KeyTopicCandidate, summary_candidate()["key_topics"][0], "topic"),
        (KeyTopicCandidate, summary_candidate()["key_topics"][0], "brief_discussion"),
        (KeyTopicCandidate, summary_candidate()["key_topics"][0], "source_segment_ids"),
        (ActionItemCandidate, action_item_candidate(), "task"),
        (ActionItemCandidate, action_item_candidate(), "owner"),
        (ActionItemCandidate, action_item_candidate(), "raw_due_expression"),
        (ActionItemCandidate, action_item_candidate(), "priority"),
        (ActionItemCandidate, action_item_candidate(), "context"),
        (ActionItemCandidate, action_item_candidate(), "source_segment_ids"),
    ],
)
def test_missing_nested_fields_are_rejected(
    model: type[Any], data: dict[str, Any], missing_field: str
) -> None:
    incomplete = deepcopy(data)
    del incomplete[missing_field]

    with pytest.raises(ValidationError):
        model.model_validate(incomplete)


@pytest.mark.parametrize(
    ("field", "value"),
    [("meeting_summary", "not-an-object"), ("action_items", {}), ("action_items", [None])],
)
def test_incorrect_root_types_are_rejected(field: str, value: Any) -> None:
    data = full_candidate()
    data[field] = value

    with pytest.raises(ValidationError):
        SummaryActionsCandidate.model_validate(data)


def test_extra_root_and_nested_fields_are_rejected() -> None:
    data = full_candidate()
    data["unexpected"] = True
    with pytest.raises(ValidationError):
        SummaryActionsCandidate.model_validate(data)

    data = full_candidate()
    data["meeting_summary"]["generated_id"] = "SUM-001"
    with pytest.raises(ValidationError):
        SummaryActionsCandidate.model_validate(data)


@pytest.mark.parametrize(
    ("model", "data", "field"),
    [
        (MeetingSummaryCandidate, summary_candidate(), "overview"),
        (KeyTopicCandidate, summary_candidate()["key_topics"][0], "topic"),
        (KeyTopicCandidate, summary_candidate()["key_topics"][0], "brief_discussion"),
        (ActionItemCandidate, action_item_candidate(), "task"),
    ],
)
def test_blank_candidate_strings_are_rejected(
    model: type[Any], data: dict[str, Any], field: str
) -> None:
    invalid = deepcopy(data)
    invalid[field] = " \t "

    with pytest.raises(ValidationError):
        model.model_validate(invalid)


@pytest.mark.parametrize(
    ("model", "data"),
    [
        (MeetingSummaryCandidate, summary_candidate()),
        (KeyTopicCandidate, summary_candidate()["key_topics"][0]),
        (ActionItemCandidate, action_item_candidate()),
    ],
)
def test_empty_source_references_are_rejected(model: type[Any], data: dict[str, Any]) -> None:
    invalid = deepcopy(data)
    invalid["source_segment_ids"] = []

    with pytest.raises(ValidationError):
        model.model_validate(invalid)


@pytest.mark.parametrize(
    ("model", "data"),
    [
        (MeetingSummaryCandidate, summary_candidate()),
        (KeyTopicCandidate, summary_candidate()["key_topics"][0]),
        (ActionItemCandidate, action_item_candidate()),
    ],
)
def test_duplicate_source_references_are_rejected(model: type[Any], data: dict[str, Any]) -> None:
    invalid = deepcopy(data)
    invalid["source_segment_ids"] = ["seg-a1", "seg-a1"]

    with pytest.raises(ValidationError):
        model.model_validate(invalid)


def test_unsupported_priority_is_rejected() -> None:
    action = action_item_candidate()
    action["priority"] = "Urgent"

    with pytest.raises(ValidationError):
        ActionItemCandidate.model_validate(action)


@pytest.mark.parametrize(
    ("field", "value"),
    [("owner", 7), ("raw_due_expression", 2026), ("source_segment_ids", "seg-a1")],
)
def test_incorrect_action_field_types_are_rejected(field: str, value: Any) -> None:
    action = action_item_candidate()
    action[field] = value

    with pytest.raises(ValidationError):
        ActionItemCandidate.model_validate(action)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", "ACT-001"),
        ("source_timestamp", "00:00:12.500"),
        ("due_date", "2026-10-09"),
        ("due_date_resolution", {}),
        ("needs_review", False),
        ("review_reasons", []),
    ],
)
def test_action_item_rejects_fields_owned_by_later_pipeline_stages(
    field: str, value: Any
) -> None:
    action = action_item_candidate()
    action[field] = value

    with pytest.raises(ValidationError):
        ActionItemCandidate.model_validate(action)


@pytest.mark.parametrize(
    ("module", "candidate"),
    [
        ("meeting_summary", {"meeting_summary": None, "action_items": None}),
        ("action_items", {"meeting_summary": None, "action_items": None}),
    ],
)
def test_requested_module_cannot_be_null(module: str, candidate: dict[str, Any]) -> None:
    request = request_fixture()
    request.extraction.requested_modules = [module]

    with pytest.raises(ValueError, match="must not be null"):
        validate_candidate_for_request(SummaryActionsCandidate.model_validate(candidate), request)


@pytest.mark.parametrize(
    ("module", "candidate"),
    [
        (
            "meeting_summary",
            {"meeting_summary": summary_candidate(), "action_items": []},
        ),
        (
            "action_items",
            {
                "meeting_summary": summary_candidate(),
                "action_items": [action_item_candidate()],
            },
        ),
    ],
)
def test_unrequested_module_must_be_null(module: str, candidate: dict[str, Any]) -> None:
    request = request_fixture()
    request.extraction.requested_modules = [module]

    with pytest.raises(ValueError, match="Unrequested .* must be null"):
        validate_candidate_for_request(SummaryActionsCandidate.model_validate(candidate), request)


def test_unsupported_requested_module_is_rejected() -> None:
    request = request_fixture()
    request.extraction.requested_modules = ["decision_log"]
    candidate = SummaryActionsCandidate(meeting_summary=None, action_items=None)

    with pytest.raises(ValueError, match="Unsupported requested modules"):
        validate_candidate_for_request(candidate, request)


def test_malformed_json_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SummaryActionsCandidate.model_validate_json('{"meeting_summary":')
