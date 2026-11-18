from evaluation.validation import validate_response

def test_valid_json_schema_relationship_and_completion_are_separate(first_case, response_payload_factory):
    result = validate_response(first_case.request, response_payload_factory(first_case))
    assert result.json_valid is True
    assert result.schema_valid is True
    assert result.relationship_valid is True
    assert result.completed is True
    assert result.semantic_evaluation_available is True


def test_relationship_mismatch_does_not_become_success(first_case, response_payload_factory):
    payload = response_payload_factory(first_case)
    payload["meeting_id"] = "another-meeting"
    result = validate_response(first_case.request, payload)
    assert result.json_valid is True
    assert result.schema_valid is True
    assert result.relationship_valid is False
    assert result.semantic_evaluation_available is False


def test_invalid_response_schema_is_distinct_from_invalid_json(first_case, response_payload_factory):
    payload = response_payload_factory(first_case)
    payload["modules"]["action_items"] = None
    result = validate_response(first_case.request, payload)
    assert result.json_valid is True
    assert result.schema_valid is False
    assert result.relationship_valid is None


def test_structural_source_ids_are_not_semantic_grounding(first_case, response_payload_factory):
    result = validate_response(first_case.request, response_payload_factory(first_case))
    assert result.structural_grounding_valid is True
    assert result.semantic_grounding_status == "pending_review"


def test_output_timestamp_is_derived_from_cited_source(first_case, response_payload_factory, action_payload_factory):
    action = action_payload_factory("SEG-0002")
    action["source_timestamp"] = "00:00:08.000"
    payload = response_payload_factory(first_case, [action])
    result = validate_response(first_case.request, payload)
    assert result.schema_valid is True
    assert result.relationship_valid is False
    assert any("source_timestamp" in error for error in result.errors)


def test_invalid_json_is_not_confused_with_valid_schema(first_case):
    result = validate_response(first_case.request, "{not json")
    assert result.json_valid is False
    assert result.schema_valid is False
    assert result.relationship_valid is None


def test_unknown_structural_source_reference_fails_contract_relationship(first_case, response_payload_factory):
    payload = response_payload_factory(first_case)
    payload["modules"]["meeting_summary"]["source_segment_ids"] = ["SEG-NOT-IN-REQUEST"]
    result = validate_response(first_case.request, payload)
    assert result.schema_valid is True
    assert result.relationship_valid is False
    assert result.structural_grounding_valid is False


def test_reversed_source_list_fails_relationship_order_check(first_case, response_payload_factory):
    payload = response_payload_factory(first_case)
    payload["modules"]["meeting_summary"]["source_segment_ids"] = ["SEG-0002", "SEG-0001"]
    result = validate_response(first_case.request, payload)
    assert result.schema_valid is True
    assert result.relationship_valid is False


def test_unrequested_non_null_module_fails_response_schema(first_case, response_payload_factory):
    payload = response_payload_factory(first_case)
    payload["modules"]["decision_log"] = []
    result = validate_response(first_case.request, payload)
    assert result.json_valid is True
    assert result.schema_valid is False
