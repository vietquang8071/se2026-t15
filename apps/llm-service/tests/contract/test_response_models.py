import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError


FIXTURES = Path(__file__).parents[1] / "fixtures"


def _response_model():
    try:
        from app.schemas.response import ExtractionResponse
    except ImportError as error:
        pytest.fail(f"ExtractionResponse is not implemented yet: {error}")
    return ExtractionResponse


def _load(path):
    return json.loads((FIXTURES / path).read_text())


def _full_response():
    return _load("responses/full_valid_response.json")


def test_full_six_module_response_fixture_validates():
    validated = _response_model().model_validate(_full_response())

    assert validated.status == "completed"
    assert validated.modules.timeline_events[1].temporal_resolution.status == "date_range"
    assert validated.modules.meeting_summary.key_topics[0].needs_review is True


@pytest.mark.parametrize(
    "fixture",
    [
        "responses/summary_actions_response.json",
        "responses/empty_results_response.json",
    ],
)
def test_subset_and_empty_result_responses_validate(fixture):
    validated = _response_model().model_validate(_load(fixture))

    if fixture.endswith("empty_results_response.json"):
        assert validated.modules.action_items == []
        assert validated.modules.decision_log == []
    else:
        assert validated.modules.decision_log is None


@pytest.mark.parametrize(
    ("module", "value"),
    [
        ("meeting_summary", None),
        ("action_items", None),
        ("decision_log", []),
    ],
)
def test_module_values_must_match_requested_modules(module, value):
    response = _load("responses/summary_actions_response.json")
    response["modules"][module] = value

    with pytest.raises(ValidationError):
        _response_model().model_validate(response)


def test_required_artifact_fields_and_enum_values_are_enforced():
    response = _full_response()
    del response["modules"]["action_items"][0]["task"]

    with pytest.raises(ValidationError):
        _response_model().model_validate(response)

    response = _full_response()
    response["modules"]["action_items"][0]["priority"] = "Urgent"
    with pytest.raises(ValidationError):
        _response_model().model_validate(response)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("modules", "action_items", 0, "source_timestamp"), "not-a-timestamp"),
        (("modules", "action_items", 0, "source_segment_ids"), []),
        (("modules", "decision_log", 0, "review_reasons"), ["invented_reason"]),
        (("modules", "timeline_events", 0, "event_type"), "meeting"),
        (("modules", "open_issues", 0, "status"), "Resolved"),
    ],
)
def test_artifact_field_constraints_are_enforced(path, value):
    response = _full_response()
    target = response
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value

    with pytest.raises(ValidationError):
        _response_model().model_validate(response)


@pytest.mark.parametrize(
    ("needs_review", "review_reasons"),
    [
        (False, ["claim_uncertain"]),
        (True, []),
    ],
)
def test_review_state_must_match_review_reasons(needs_review, review_reasons):
    response = _full_response()
    action = response["modules"]["action_items"][0]
    action["needs_review"] = needs_review
    action["review_reasons"] = review_reasons

    with pytest.raises(ValidationError):
        _response_model().model_validate(response)


def test_temporal_evidence_must_be_a_subset_of_artifact_evidence():
    response = _full_response()
    response["modules"]["action_items"][0]["due_date_resolution"][
        "source_segment_ids"
    ] = ["seg-999"]

    with pytest.raises(ValidationError):
        _response_model().model_validate(response)


def test_follow_up_temporal_resolution_requires_its_raw_target():
    response = _full_response()
    response["modules"]["follow_up_items"][0]["target_trigger_or_date"] = None

    with pytest.raises(ValidationError):
        _response_model().model_validate(response)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["processing"].update(completed_at="2026-10-05T08:59:59Z"),
        lambda value: value["processing"].update(token_usage={"input_tokens": -1, "output_tokens": 2}),
        lambda value: value["processing"].pop("evidence_prompt_version"),
        lambda value: value["processing"].update(started_at="2026-10-05T09:00:00"),
    ],
)
def test_processing_metadata_is_required_and_validated(mutate):
    response = _full_response()
    mutate(response)

    with pytest.raises(ValidationError):
        _response_model().model_validate(response)


def test_response_schema_exposes_typed_six_module_keys():
    schema = _response_model().model_json_schema()

    assert set(schema["$defs"]["ExtractionModules"]["properties"]) == {
        "meeting_summary",
        "action_items",
        "decision_log",
        "open_issues",
        "follow_up_items",
        "timeline_events",
    }
    assert "$defs" in schema


def test_cross_request_validation_checks_ids_metadata_and_evidence():
    try:
        from app.schemas.request import ExtractionRequest
        from app.schemas.response import validate_response_for_request
    except ImportError as error:
        pytest.fail(f"Cross-request validation is not implemented yet: {error}")

    request = ExtractionRequest.model_validate(_load("requests/full_valid_request.json"))
    response = _response_model().model_validate(_full_response())
    checked = validate_response_for_request(request, response)

    assert checked.request_id == request.request_id

    response_data = deepcopy(_full_response())
    response_data["modules"]["decision_log"][0]["source_segment_ids"] = ["seg-missing"]
    invalid_response = _response_model().model_validate(response_data)
    with pytest.raises(ValueError, match="source"):
        validate_response_for_request(request, invalid_response)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda request, response: response.update(request_id="another-request"),
        lambda request, response: response.update(meeting_id="another-meeting"),
        lambda request, response: response.update(transcript_revision_id="another-revision"),
        lambda request, response: request["extraction"].update(
            requested_modules=["meeting_summary", "action_items"]
        ),
    ],
)
def test_cross_request_validation_rejects_identity_or_module_mismatch(mutate):
    from app.schemas.request import ExtractionRequest
    from app.schemas.response import validate_response_for_request

    request_data = _load("requests/full_valid_request.json")
    response_data = _full_response()
    mutate(request_data, response_data)
    request = ExtractionRequest.model_validate(request_data)
    response = _response_model().model_validate(response_data)

    with pytest.raises(ValueError):
        validate_response_for_request(request, response)


def test_cross_request_validation_rejects_unsorted_source_segments():
    from app.schemas.request import ExtractionRequest
    from app.schemas.response import validate_response_for_request

    request = ExtractionRequest.model_validate(_load("requests/full_valid_request.json"))
    response_data = _full_response()
    response_data["modules"]["meeting_summary"]["source_segment_ids"] = [
        "seg-007",
        "seg-002",
    ]
    response = _response_model().model_validate(response_data)

    with pytest.raises(ValueError, match="ordered"):
        validate_response_for_request(request, response)


def test_cross_request_validation_rejects_summary_metadata_mismatch():
    from app.schemas.request import ExtractionRequest
    from app.schemas.response import validate_response_for_request

    request = ExtractionRequest.model_validate(_load("requests/full_valid_request.json"))
    response_data = _full_response()
    response_data["modules"]["meeting_summary"]["title"] = "Different meeting"
    response = _response_model().model_validate(response_data)

    with pytest.raises(ValueError, match="summary metadata"):
        validate_response_for_request(request, response)
