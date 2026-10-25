import json
from pathlib import Path

import pytest
from pydantic import ValidationError


FIXTURES = Path(__file__).parents[1] / "fixtures"


def _request_model():
    try:
        from app.schemas.request import ExtractionRequest
    except ImportError as error:
        pytest.fail(f"ExtractionRequest is not implemented yet: {error}")
    return ExtractionRequest


def test_full_request_fixture_validates():
    request = json.loads(
        (FIXTURES / "requests" / "full_valid_request.json").read_text()
    )

    validated = _request_model().model_validate(request)

    assert validated.meeting.anchor_date.isoformat() == "2026-10-05"
    assert validated.transcript.segments[0].start == 852.0
    assert validated.extraction.requested_modules == [
        "meeting_summary",
        "action_items",
        "decision_log",
        "open_issues",
        "follow_up_items",
        "timeline_events",
    ]


def _full_request():
    return json.loads(
        (FIXTURES / "requests" / "full_valid_request.json").read_text()
    )


def test_invalid_request_fixtures_are_rejected():
    model = _request_model()
    invalid_dir = FIXTURES / "invalid_requests"

    for fixture in invalid_dir.glob("*.json"):
        with pytest.raises(ValidationError):
            model.model_validate(json.loads(fixture.read_text()))


def test_unsupported_contract_version_has_a_dedicated_error_type():
    request = json.loads(
        (FIXTURES / "invalid_requests" / "unsupported_contract_version.json").read_text()
    )

    with pytest.raises(ValidationError) as error:
        _request_model().model_validate(request)

    assert any(
        detail["type"] == "unsupported_contract_version"
        for detail in error.value.errors()
    )


@pytest.mark.parametrize(
    ("path", "field"),
    [
        ((), "undocumented"),
        (("meeting",), "undocumented"),
        (("transcript", "segments", 0), "undocumented"),
    ],
)
def test_unknown_fields_are_rejected_at_every_nesting_level(path, field):
    request = _full_request()
    target = request
    for part in path:
        target = target[part]
    target[field] = "unexpected"

    with pytest.raises(ValidationError):
        _request_model().model_validate(request)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("meeting", "duration_seconds"), "1900.5"),
        (("meeting", "duration_seconds"), True),
        (("transcript", "segments", 0, "start"), "852.0"),
        (("transcript", "segments", 0, "start"), False),
    ],
)
def test_json_numbers_reject_strings_and_booleans(path, value):
    request = _full_request()
    target = request
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value

    with pytest.raises(ValidationError):
        _request_model().model_validate(request)


@pytest.mark.parametrize("anchor_date", ["2026-02-30", "2026-10-05T00:00:00Z", "20261005"])
def test_anchor_date_requires_valid_date_only_iso_string(anchor_date):
    request = _full_request()
    request["meeting"]["anchor_date"] = anchor_date

    with pytest.raises(ValidationError):
        _request_model().model_validate(request)


def test_invalid_iana_timezone_is_rejected():
    request = _full_request()
    request["meeting"]["timezone"] = "UTC+7"

    with pytest.raises(ValidationError):
        _request_model().model_validate(request)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda request: request["transcript"]["segments"][0].update(start=-0.1),
        lambda request: request["transcript"]["segments"][0].update(end=852.0),
        lambda request: request["transcript"]["segments"][0].update(end=1901.0),
        lambda request: request["transcript"]["segments"].reverse(),
    ],
)
def test_invalid_segment_time_bounds_and_order_are_rejected(mutate):
    request = _full_request()
    mutate(request)

    with pytest.raises(ValidationError):
        _request_model().model_validate(request)


def test_duplicate_segment_ids_are_rejected():
    request = _full_request()
    request["transcript"]["segments"][1]["id"] = request["transcript"]["segments"][0]["id"]

    with pytest.raises(ValidationError):
        _request_model().model_validate(request)


def test_overlapping_segments_unknown_speaker_and_null_speaker_are_allowed():
    request = _full_request()
    request["transcript"]["segments"][1]["start"] = 857.0
    request["transcript"]["segments"][0]["speaker_id"] = "speaker-unmapped"
    request["transcript"]["segments"][1]["speaker_id"] = None

    validated = _request_model().model_validate(request)

    assert validated.transcript.segments[0].speaker_id == "speaker-unmapped"
    assert validated.transcript.segments[1].speaker_id is None


def test_duplicate_participant_ids_are_rejected():
    request = _full_request()
    request["meeting"]["participants"][1]["id"] = request["meeting"]["participants"][0]["id"]

    with pytest.raises(ValidationError):
        _request_model().model_validate(request)


def test_speaker_cannot_map_to_two_participants():
    request = _full_request()
    request["meeting"]["participants"][1]["speaker_ids"] = ["speaker_1"]

    with pytest.raises(ValidationError):
        _request_model().model_validate(request)


@pytest.mark.parametrize(
    "requested_modules",
    [
        [],
        ["meeting_summary", "meeting_summary"],
        ["meeting_summary", "unknown_module"],
    ],
)
def test_requested_modules_must_be_nonempty_unique_and_supported(requested_modules):
    request = _full_request()
    request["extraction"]["requested_modules"] = requested_modules

    with pytest.raises(ValidationError):
        _request_model().model_validate(request)


@pytest.mark.parametrize("segments", [[], [{"id": "seg-empty", "start": 0.0, "end": 1.0, "speaker_id": None, "text": "  \t"}]])
def test_transcript_without_speech_has_dedicated_validation_code(segments):
    request = _full_request()
    request["transcript"]["segments"] = segments

    with pytest.raises(ValidationError) as error:
        _request_model().model_validate(request)

    assert any(detail["type"] == "empty_transcript" for detail in error.value.errors())


def test_malformed_segment_is_not_misreported_as_empty_transcript():
    request = _full_request()
    request["transcript"]["segments"] = [
        {
            "id": "seg-missing-text",
            "start": 0.0,
            "end": 1.0,
            "speaker_id": None,
        }
    ]

    with pytest.raises(ValidationError) as error:
        _request_model().model_validate(request)

    assert all(detail["type"] != "empty_transcript" for detail in error.value.errors())


def test_speech_segment_text_cannot_be_blank():
    request = _full_request()
    request["transcript"]["segments"][0]["text"] = "  \t"

    with pytest.raises(ValidationError):
        _request_model().model_validate(request)
