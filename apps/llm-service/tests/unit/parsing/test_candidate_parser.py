import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.parsing.candidates import (
    CandidateFormatError,
    CandidateRequestMismatchError,
    parse_candidate,
)
from app.schemas.candidates import SummaryActionsCandidate
from app.schemas.request import ExtractionRequest


REQUEST_FIXTURE = (
    Path(__file__).parents[2] / "fixtures" / "requests" / "summary_actions_request.json"
)


def candidate_payload(modules: tuple[str, ...] = ("meeting_summary", "action_items")) -> dict[str, Any]:
    return {
        "meeting_summary": (
            {
                "overview": "Cuộc họp rà soát tiến độ.",
                "key_topics": [],
                "source_segment_ids": ["not-in-transcript"],
            }
            if "meeting_summary" in modules
            else None
        ),
        "action_items": (
            [
                {
                    "task": "Gửi bản ghi chú",
                    "owner": None,
                    "raw_due_expression": None,
                    "priority": None,
                    "context": None,
                    "source_segment_ids": ["seg-a1"],
                }
            ]
            if "action_items" in modules
            else None
        ),
    }


def make_request(modules: tuple[str, ...] = ("meeting_summary", "action_items")) -> ExtractionRequest:
    payload = json.loads(REQUEST_FIXTURE.read_text(encoding="utf-8"))
    payload["extraction"]["requested_modules"] = list(modules)
    return ExtractionRequest.model_validate(payload)


def encode(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


@pytest.mark.parametrize(
    "modules",
    [
        ("meeting_summary", "action_items"),
        ("meeting_summary",),
        ("action_items",),
    ],
)
def test_parses_candidate_for_each_supported_module_selection(
    modules: tuple[str, ...],
) -> None:
    result = parse_candidate(encode(candidate_payload(modules)), make_request(modules))

    assert isinstance(result, SummaryActionsCandidate)
    assert (result.meeting_summary is not None) == ("meeting_summary" in modules)
    assert (result.action_items is not None) == ("action_items" in modules)


def test_preserves_vietnamese_nullable_fields_and_empty_candidate_lists() -> None:
    payload = candidate_payload(("action_items",))
    payload["action_items"] = []
    request = make_request(("action_items",))

    parsed = parse_candidate(encode(payload), request)

    assert parsed.action_items == []
    summary = candidate_payload(("meeting_summary",))
    parsed_summary = parse_candidate(encode(summary), make_request(("meeting_summary",)))
    assert parsed_summary.meeting_summary is not None
    assert parsed_summary.meeting_summary.overview == "Cuộc họp rà soát tiến độ."
    assert parsed_summary.meeting_summary.key_topics == []


@pytest.mark.parametrize(
    "content",
    [
        "",
        "   \n",
        "{ malformed json",
        "```json\n{\"meeting_summary\": null, \"action_items\": []}\n```",
        "Kết quả trích xuất:\n{\"meeting_summary\": null, \"action_items\": []}",
        "[]",
    ],
    ids=["empty", "whitespace", "malformed-json", "markdown-fence", "surrounding-prose", "wrong-root"],
)
def test_rejects_empty_malformed_or_non_json_content(content: str) -> None:
    with pytest.raises(CandidateFormatError):
        parse_candidate(content, make_request(("action_items",)))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data.pop("action_items"),
        lambda data: data.update(extra_output="unexpected"),
        lambda data: data.update(action_items={}),
        lambda data: data["action_items"][0].update(task="  "),
        lambda data: data["action_items"][0].update(priority="Urgent"),
        lambda data: data["action_items"][0].update(source_segment_ids=[]),
        lambda data: data["action_items"][0].update(source_segment_ids=["seg-a1", "seg-a1"]),
        lambda data: data["action_items"][0].pop("owner"),
    ],
    ids=[
        "missing-root-field",
        "extra-field",
        "wrong-module-type",
        "blank-task",
        "invalid-priority",
        "empty-source-ids",
        "duplicate-source-ids",
        "missing-required-nullable-field",
    ],
)
def test_rejects_candidate_schema_violations(mutate) -> None:
    payload = deepcopy(candidate_payload(("action_items",)))
    mutate(payload)

    with pytest.raises(CandidateFormatError):
        parse_candidate(encode(payload), make_request(("action_items",)))


@pytest.mark.parametrize(
    ("modules", "payload"),
    [
        (("meeting_summary",), candidate_payload(("action_items",))),
        (("action_items",), candidate_payload(("meeting_summary",))),
        (("meeting_summary", "action_items"), {"meeting_summary": None, "action_items": None}),
        (("decision_log",), {"meeting_summary": None, "action_items": None}),
    ],
    ids=["unrequested-action-output", "unrequested-summary-output", "requested-modules-null", "unsupported-module"],
)
def test_rejects_candidate_request_mismatches(
    modules: tuple[str, ...], payload: dict[str, Any]
) -> None:
    with pytest.raises(CandidateRequestMismatchError):
        parse_candidate(encode(payload), make_request(modules))


def test_candidate_format_error_does_not_expose_raw_provider_content() -> None:
    content = "TRANSCRIPT-CANARY-83: invalid model output"

    with pytest.raises(CandidateFormatError) as exc:
        parse_candidate(content, make_request(("action_items",)))

    assert "TRANSCRIPT-CANARY-83" not in str(exc.value)
    assert content not in str(exc.value)


def test_request_mismatch_error_does_not_expose_candidate_content() -> None:
    payload = {"meeting_summary": None, "action_items": []}
    content = encode(payload)

    with pytest.raises(CandidateRequestMismatchError) as exc:
        parse_candidate(content, make_request(("meeting_summary",)))

    assert content not in str(exc.value)


def test_structurally_valid_candidate_may_reference_unknown_segment_and_owner_sentinel() -> None:
    payload = candidate_payload(("action_items",))
    payload["action_items"][0]["source_segment_ids"] = ["not-in-transcript"]
    payload["action_items"][0]["owner"] = "Unknown"

    parsed = parse_candidate(encode(payload), make_request(("action_items",)))

    assert parsed.action_items is not None
    assert parsed.action_items[0].source_segment_ids == ["not-in-transcript"]
    assert parsed.action_items[0].owner == "Unknown"
