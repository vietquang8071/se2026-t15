import json


def test_public_models_generate_serializable_json_schema():
    from app.schemas.errors import ErrorEnvelope
    from app.schemas.request import ExtractionRequest
    from app.schemas.response import ExtractionResponse
    from app.schemas.temporal import TemporalResolution

    for model in (ExtractionRequest, ExtractionResponse, TemporalResolution, ErrorEnvelope):
        schema = model.model_json_schema()

        assert schema["type"] == "object"
        json.dumps(schema, allow_nan=False)


def test_response_json_schema_keeps_the_six_modules_typed_and_required():
    from app.schemas.response import ExtractionResponse

    schema = ExtractionResponse.model_json_schema()
    modules = schema["$defs"]["ExtractionModules"]

    assert set(modules["required"]) == {
        "meeting_summary",
        "action_items",
        "decision_log",
        "open_issues",
        "follow_up_items",
        "timeline_events",
    }
    assert modules["additionalProperties"] is False
    assert "$ref" in modules["properties"]["meeting_summary"]["anyOf"][0]
