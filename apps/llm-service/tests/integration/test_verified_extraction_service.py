"""FastAPI integration tests through real validation and provider composition."""

from __future__ import annotations

import asyncio
import json
from collections import deque
from pathlib import Path
from typing import Any

import pytest
from asgi_client import ASGITestClient as PipelineTestClient
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.core.config import Settings
from app.main import create_app
from app.providers.errors import (
    ProviderConfigurationError,
    ProviderFailureError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from app.providers.models import ProviderRequest, ProviderResult, ProviderUsage
from app.schemas.errors import ErrorEnvelope
from app.schemas.request import ExtractionRequest
from app.services.factory import create_verified_extraction_service


SERVICE_ROOT = Path(__file__).parents[2]
REQUEST_FIXTURE = SERVICE_ROOT / "tests/fixtures/requests/summary_actions_request.json"
TEST_TOKEN = "verified-pipeline-token-do-not-log"


class ScriptedProvider:
    def __init__(self, steps: list[ProviderResult | BaseException]) -> None:
        self.steps = deque(steps)
        self.requests: list[ProviderRequest] = []

    async def generate(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        step = self.steps.popleft()
        if isinstance(step, BaseException):
            raise step
        return step


def result(content: str, *, model: str = "offline-model", usage: ProviderUsage | None = None):
    return ProviderResult(
        content=content,
        model_id=model,
        finish_reason="stop",
        usage=usage,
    )


def candidate_content(
    *,
    modules: tuple[str, ...] = ("meeting_summary", "action_items"),
    source_id: str = "seg-a1",
    task: str = "Gửi bản ghi chú",
    owner: str | None = "Alex",
    due: str | None = None,
    priority: str | None = None,
    context: str | None = None,
    transcript_question: bool = False,
) -> str:
    summary = None
    if "meeting_summary" in modules:
        summary = {
            "overview": "Nhóm rà soát tiến độ và ghi nhận cam kết gửi ghi chú.",
            "key_topics": [],
            "source_segment_ids": [source_id],
        }
    actions = None
    if "action_items" in modules:
        actions = [
            {
                "task": task,
                "owner": owner,
                "raw_due_expression": due,
                "priority": priority,
                "context": context,
                "source_segment_ids": [source_id],
            }
        ]
    return json.dumps(
        {"meeting_summary": summary, "action_items": actions}, ensure_ascii=False
    )


def verifier_content(
    claim_ids: list[str], *, overrides: dict[str, str] | None = None
) -> str:
    statuses = overrides or {}
    return json.dumps(
        {
            "checks": [
                {"claim_id": claim_id, "status": statuses.get(claim_id, "supported")}
                for claim_id in claim_ids
            ]
        }
    )


def make_request(
    *,
    request_id: str = "req-verified-http",
    modules: tuple[str, ...] = ("meeting_summary", "action_items"),
    source_id: str = "seg-a1",
    transcript_text: str = "Tôi sẽ gửi bản ghi chú.",
) -> dict[str, Any]:
    payload = json.loads(REQUEST_FIXTURE.read_text(encoding="utf-8"))
    payload["request_id"] = request_id
    payload["extraction"]["requested_modules"] = list(modules)
    payload["transcript"]["segments"] = [
        {
            "id": source_id,
            "start": 1.25,
            "end": 3.0,
            "speaker_id": "speaker_1",
            "text": transcript_text,
        }
    ]
    return payload


def make_settings(**kwargs: Any) -> Settings:
    return Settings(
        llm_service_token=SecretStr(TEST_TOKEN),
        openrouter_api_key=None,
        **kwargs,
    )


def client_for(
    provider: ScriptedProvider, *, settings: Settings | None = None
) -> PipelineTestClient:
    runtime_settings = settings or make_settings()
    service = create_verified_extraction_service(
        runtime_settings,
        provider=provider,
        provider_name="offline-test-provider",
    )
    return PipelineTestClient(
        create_app(settings=runtime_settings, extraction_service=service)
    )


def supported_provider(
    *, modules: tuple[str, ...] = ("meeting_summary", "action_items"),
    source_id: str = "seg-a1",
    task: str = "Gửi bản ghi chú",
    owner: str | None = "Alex",
    due: str | None = None,
    priority: str | None = None,
    context: str | None = None,
    overrides: dict[str, str] | None = None,
) -> ScriptedProvider:
    ids = []
    if "meeting_summary" in modules:
        ids.append("summary.overview")
    if "action_items" in modules:
        if due is None:
            ids.extend(["actions[0].task"])
        else:
            ids.extend(["actions[0].task", "actions[0].raw_due_expression"])
        if owner is not None:
            ids.append("actions[0].owner")
        if priority is not None:
            ids.append("actions[0].priority")
        if context is not None:
            ids.append("actions[0].context")
    return ScriptedProvider(
        [
            result(
                candidate_content(
                    modules=modules,
                    source_id=source_id,
                    task=task,
                    owner=owner,
                    due=due,
                    priority=priority,
                    context=context,
                ),
                usage=ProviderUsage(input_tokens=20, output_tokens=10),
            ),
            result(verifier_content(ids, overrides=overrides), usage=ProviderUsage(input_tokens=30, output_tokens=8)),
        ]
    )


def post(client: PipelineTestClient, payload: dict[str, Any]):
    return client.post(
        "/v1/extractions",
        json=payload,
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    )


@pytest.mark.parametrize(
    "modules",
    [
        ("meeting_summary",),
        ("action_items",),
        ("meeting_summary", "action_items"),
    ],
    ids=["summary-only", "actions-only", "combined"],
)
def test_verified_pipeline_returns_contract_response_for_requested_modules(modules):
    provider = supported_provider(modules=modules)
    request = make_request(modules=modules)

    with client_for(provider) as client:
        response = post(client, request)

    assert response.status_code == 200
    body = response.json()
    assert body["requested_modules"] == list(modules)
    assert body["modules"]["meeting_summary"] is not None if "meeting_summary" in modules else body["modules"]["meeting_summary"] is None
    assert body["modules"]["action_items"] is not None if "action_items" in modules else body["modules"]["action_items"] is None
    assert body["processing"]["evidence_prompt_version"] == "evidence-v1.3"
    assert len(provider.requests) == 2


@pytest.mark.parametrize(
    "transcript_text",
    [
        "API cần hoàn thành ngày 15 tháng 12 năm 2026.",
        "The API must be ready by December 15, 2026.",
    ],
    ids=["vietnamese-natural-date", "english-natural-date"],
)
def test_supported_natural_language_deadline_resolves_iso_candidate(transcript_text):
    provider = supported_provider(
        modules=("action_items",),
        task="Hoàn thành API",
        due="2026-12-15",
    )

    with client_for(provider) as client:
        response = post(
            client,
            make_request(modules=("action_items",), transcript_text=transcript_text),
        )

    assert response.status_code == 200
    action = response.json()["modules"]["action_items"][0]
    assert action["raw_due_expression"] == "2026-12-15"
    assert action["due_date"] == "2026-12-15"
    assert action["due_date_resolution"]["status"] == "exact_date"
    assert action["needs_review"] is False
    assert len(provider.requests) == 2


@pytest.mark.parametrize("due", ["15 tháng 12", "thứ Sáu tuần sau"])
def test_uncertain_deadline_remains_reviewable_in_contract_response(due):
    provider = supported_provider(
        modules=("action_items",),
        due=due,
        overrides={"actions[0].raw_due_expression": "uncertain"},
    )

    with client_for(provider) as client:
        response = post(client, make_request(modules=("action_items",)))

    assert response.status_code == 200
    action = response.json()["modules"]["action_items"][0]
    assert action["raw_due_expression"] == due
    assert action["due_date"] is None
    assert action["due_date_resolution"]["status"] == "unresolved"
    assert action["due_date_resolution"]["needs_review"] is True
    assert action["needs_review"] is True
    assert "temporal_unresolved" in action["review_reasons"]
    assert "claim_uncertain" in action["review_reasons"]


def test_obsolete_deadline_verdict_clears_candidate_without_replacing_it():
    provider = supported_provider(
        modules=("action_items",),
        task="Hoàn thành API",
        due="2026-12-15",
        overrides={"actions[0].raw_due_expression": "unsupported"},
    )
    request = make_request(
        modules=("action_items",),
        transcript_text="API deadline là 2026-12-15.",
    )
    request["transcript"]["segments"].append(
        {
            "id": "seg-later",
            "start": 4.0,
            "end": 6.0,
            "speaker_id": "speaker_1",
            "text": "Chốt lại, API chuyển sang ngày 20 tháng 12 năm 2026.",
        }
    )

    with client_for(provider) as client:
        response = post(client, request)

    assert response.status_code == 200
    action = response.json()["modules"]["action_items"][0]
    assert action["task"] == "Hoàn thành API"
    assert action["raw_due_expression"] is None
    assert action["due_date"] is None
    assert action["due_date_resolution"] is None
    assert action["needs_review"] is True
    assert "evidence_unverified" in action["review_reasons"]
    assert len(provider.requests) == 2


def test_verified_empty_actions_returns_empty_list_for_discussion_without_commitment():
    """A scripted verdict tests the pipeline policy, not model semantic accuracy."""

    provider = ScriptedProvider(
        [
            result(json.dumps({"meeting_summary": None, "action_items": []}), model="offline-model"),
            result(verifier_content(["actions.absence"]), model="offline-model"),
        ]
    )
    request = make_request(
        modules=("action_items",),
        transcript_text="Hôm nay nhóm trao đổi tình hình chung, chưa chốt việc cần thực hiện.",
    )

    with client_for(provider) as client:
        response = post(client, request)

    assert response.status_code == 200
    assert response.json()["modules"]["action_items"] == []
    assert len(provider.requests) == 2


def test_uncertain_empty_action_absence_fails_closed():
    provider = ScriptedProvider(
        [
            result(json.dumps({"meeting_summary": None, "action_items": []}), model="offline-model"),
            result(
                verifier_content(
                    ["actions.absence"], overrides={"actions.absence": "uncertain"}
                ),
                model="offline-model",
            ),
        ]
    )

    with client_for(provider) as client:
        response = post(
            client,
            make_request(
                modules=("action_items",),
                transcript_text="Có lẽ tôi sẽ làm phần API nếu còn thời gian.",
            ),
        )

    assert response.status_code == 502
    assert ErrorEnvelope.model_validate(response.json()).code == "UNVERIFIED_EVIDENCE"
    assert len(provider.requests) == 2


def test_unknown_source_id_returns_unverified_evidence_error():
    provider = supported_provider(modules=("action_items",), source_id="missing-source")

    with client_for(provider) as client:
        response = post(client, make_request(modules=("action_items",)))

    assert response.status_code == 502
    assert ErrorEnvelope.model_validate(response.json()).code == "UNVERIFIED_EVIDENCE"
    assert len(provider.requests) == 1


def test_unsupported_summary_overview_returns_non_success():
    provider = supported_provider(
        modules=("meeting_summary",), overrides={"summary.overview": "unsupported"}
    )

    with client_for(provider) as client:
        response = post(client, make_request(modules=("meeting_summary",)))

    assert response.status_code == 502
    assert ErrorEnvelope.model_validate(response.json()).code == "UNVERIFIED_EVIDENCE"


def test_question_extracted_as_commitment_is_rejected():
    provider = supported_provider(
        modules=("action_items",),
        task="Hoàn thiện API",
        overrides={"actions[0].task": "unsupported"},
    )
    request = make_request(
        modules=("action_items",),
        transcript_text="Minh có thể hoàn thiện API trước thứ Sáu không?",
    )

    with client_for(provider) as client:
        response = post(client, request)

    assert response.status_code == 502
    assert ErrorEnvelope.model_validate(response.json()).code == "UNVERIFIED_EVIDENCE"


@pytest.mark.parametrize(
    "transcript_text",
    [
        "Nếu cần thì Minh có thể hoàn thiện API vào thứ Sáu.",
        "Đề xuất giao Minh hoàn thiện API đã bị từ chối.",
    ],
    ids=["conditional", "rejected"],
)
def test_conditional_or_rejected_assignment_is_not_published(transcript_text):
    provider = supported_provider(
        modules=("action_items",),
        task="Hoàn thiện API",
        owner="Minh",
        overrides={"actions[0].task": "unsupported", "actions[0].owner": "unsupported"},
    )

    with client_for(provider) as client:
        response = post(
            client,
            make_request(modules=("action_items",), transcript_text=transcript_text),
        )

    assert response.status_code == 502
    assert ErrorEnvelope.model_validate(response.json()).code == "UNVERIFIED_EVIDENCE"


def test_valid_source_id_with_unrelated_text_does_not_pass_semantic_gate():
    provider = supported_provider(
        modules=("action_items",),
        task="Hoàn thiện API",
        overrides={"actions[0].task": "unsupported"},
    )

    with client_for(provider) as client:
        response = post(
            client,
            make_request(
                modules=("action_items",),
                transcript_text="Thời tiết hôm nay rất đẹp.",
            ),
        )

    assert response.status_code == 502
    assert ErrorEnvelope.model_validate(response.json()).code == "UNVERIFIED_EVIDENCE"


def test_first_person_commitment_uses_verified_speaker_mapping():
    provider = supported_provider(
        modules=("action_items",), task="Gửi bản ghi chú", owner="Alex"
    )

    with client_for(provider) as client:
        response = post(
            client,
            make_request(
                modules=("action_items",),
                transcript_text="Tôi sẽ gửi bản ghi chú.",
            ),
        )

    assert response.status_code == 200
    assert response.json()["modules"]["action_items"][0]["owner"] == "Alex"


def test_multiple_supported_assignments_in_one_segment_keep_their_owners():
    candidate = {
        "meeting_summary": None,
        "action_items": [
            {
                "task": "Gửi bản ghi chú",
                "owner": "Minh",
                "raw_due_expression": None,
                "priority": None,
                "context": None,
                "source_segment_ids": ["seg-a1"],
            },
            {
                "task": "Sửa giao diện",
                "owner": "Lan",
                "raw_due_expression": None,
                "priority": None,
                "context": None,
                "source_segment_ids": ["seg-a1"],
            },
        ],
    }
    claims = [
        "actions[0].task",
        "actions[0].owner",
        "actions[1].task",
        "actions[1].owner",
    ]
    provider = ScriptedProvider(
        [result(json.dumps(candidate, ensure_ascii=False)), result(verifier_content(claims))]
    )
    request = make_request(
        modules=("action_items",),
        transcript_text="Tôi sẽ gửi bản ghi chú, Lan sẽ sửa giao diện.",
    )
    request["meeting"]["participants"] = [
        {"id": "participant-minh", "display_name": "Minh", "speaker_ids": ["speaker_1"]},
        {"id": "participant-lan", "display_name": "Lan", "speaker_ids": ["speaker_2"]},
    ]

    with client_for(provider) as client:
        response = post(client, request)

    assert response.status_code == 200
    actions = response.json()["modules"]["action_items"]
    assert [action["owner"] for action in actions] == ["Minh", "Lan"]
    assert [action["needs_review"] for action in actions] == [False, False]
    assert len(provider.requests) == 2


def test_named_owner_remains_valid_when_another_participant_spoke():
    provider = supported_provider(
        modules=("action_items",), task="Hoàn thiện giao diện", owner="Lan"
    )
    request = make_request(
        modules=("action_items",),
        transcript_text="Lan sẽ hoàn thiện giao diện.",
    )
    request["meeting"]["participants"].append(
        {"id": "participant-lan", "display_name": "Lan", "speaker_ids": ["speaker_2"]}
    )

    with client_for(provider) as client:
        response = post(client, request)

    assert response.status_code == 200
    assert response.json()["modules"]["action_items"][0]["owner"] == "Lan"


def test_supported_owner_verdict_survives_missing_speaker_mapping():
    provider = supported_provider(
        modules=("action_items",),
        overrides={"actions[0].owner": "supported"},
    )
    request = make_request(
        modules=("action_items",), transcript_text="Tôi sẽ gửi bản ghi chú."
    )
    request["meeting"]["participants"][0]["speaker_ids"] = []

    with client_for(provider) as client:
        response = post(client, request)

    assert response.status_code == 200
    action = response.json()["modules"]["action_items"][0]
    assert action["owner"] == "Alex"
    assert action["needs_review"] is False
    assert action["review_reasons"] == []


def test_supported_owner_verdict_is_not_overridden_by_first_person_regex():
    provider = supported_provider(
        modules=("action_items",),
        task="Gửi bản ghi chú",
        owner="Minh",
        overrides={"actions[0].owner": "supported"},
    )

    with client_for(provider) as client:
        response = post(
            client,
            make_request(
                modules=("action_items",),
                transcript_text="Tôi sẽ gửi bản ghi chú.",
            ),
        )

    assert response.status_code == 200
    action = response.json()["modules"]["action_items"][0]
    assert action["task"] == "Gửi bản ghi chú"
    assert action["owner"] == "Minh"
    assert action["needs_review"] is False
    assert action["review_reasons"] == []


def test_supported_owner_is_preserved_after_reassignment_across_segments():
    candidate = {
        "meeting_summary": None,
        "action_items": [
            {
                "task": "Sửa giao diện",
                "owner": "Lan",
                "raw_due_expression": None,
                "priority": None,
                "context": None,
                "source_segment_ids": ["seg-a1", "seg-a2"],
            }
        ],
    }
    provider = ScriptedProvider(
        [
            result(json.dumps(candidate, ensure_ascii=False)),
            result(
                verifier_content(["actions[0].task", "actions[0].owner"])
            ),
        ]
    )
    request = make_request(modules=("action_items",))
    request["transcript"]["segments"] = [
        {
            "id": "seg-a1",
            "start": 1.0,
            "end": 2.0,
            "speaker_id": "speaker_1",
            "text": "Tôi sẽ sửa giao diện.",
        },
        {
            "id": "seg-a2",
            "start": 2.1,
            "end": 3.0,
            "speaker_id": "speaker_1",
            "text": "Chốt lại, Lan sẽ sửa giao diện thay tôi.",
        },
    ]
    request["meeting"]["participants"] = [
        {"id": "participant-minh", "display_name": "Minh", "speaker_ids": ["speaker_1"]},
        {"id": "participant-lan", "display_name": "Lan", "speaker_ids": ["speaker_2"]},
    ]

    with client_for(provider) as client:
        response = post(client, request)

    assert response.status_code == 200
    action = response.json()["modules"]["action_items"][0]
    assert action["owner"] == "Lan"
    assert action["needs_review"] is False
    assert len(provider.requests) == 2


@pytest.mark.parametrize(
    ("field_name", "value"),
    [("priority", "High"), ("due", "2026-12-15")],
    ids=["priority", "deadline"],
)
def test_unsupported_optional_claim_is_not_published(field_name, value):
    overrides = {f"actions[0].{field_name if field_name != 'due' else 'raw_due_expression'}": "unsupported"}
    provider = supported_provider(
        modules=("action_items",),
        due=value if field_name == "due" else None,
        priority=value if field_name == "priority" else None,
        overrides=overrides,
    )

    with client_for(provider) as client:
        response = post(client, make_request(modules=("action_items",)))

    assert response.status_code == 200
    action = response.json()["modules"]["action_items"][0]
    assert action[field_name if field_name != "due" else "raw_due_expression"] is None
    if field_name == "due":
        assert action["task"] == "Gửi bản ghi chú"
        assert action["due_date"] is None
        assert action["due_date_resolution"] is None
        assert action["needs_review"] is True
    assert action["review_reasons"] == ["evidence_unverified"]


def test_uncertain_owner_is_null_and_reviewable():
    provider = supported_provider(
        modules=("action_items",), overrides={"actions[0].owner": "uncertain"}
    )

    with client_for(provider) as client:
        response = post(client, make_request(modules=("action_items",)))

    assert response.status_code == 200
    action = response.json()["modules"]["action_items"][0]
    assert action["owner"] is None
    assert action["needs_review"] is True
    assert action["review_reasons"] == ["owner_unconfirmed", "claim_uncertain"]


def test_unsupported_owner_is_cleared_while_supported_task_remains():
    provider = supported_provider(
        modules=("action_items",),
        overrides={"actions[0].owner": "unsupported"},
    )

    with client_for(provider) as client:
        response = post(client, make_request(modules=("action_items",)))

    assert response.status_code == 200
    action = response.json()["modules"]["action_items"][0]
    assert action["task"] == "Gửi bản ghi chú"
    assert action["owner"] is None
    assert action["needs_review"] is True
    assert action["review_reasons"] == ["owner_unconfirmed"]


def test_verifier_schema_failure_returns_invalid_structured_output():
    provider = ScriptedProvider(
        [
            result(candidate_content(modules=("action_items",))),
            result('{"checks":[{"claim_id":"actions[0].task","status":"approved"}]}'),
        ]
    )

    with client_for(provider) as client:
        response = post(client, make_request(modules=("action_items",)))

    assert response.status_code == 502
    assert ErrorEnvelope.model_validate(response.json()).code == "INVALID_STRUCTURED_OUTPUT"


def test_candidate_schema_failure_returns_invalid_structured_output():
    provider = ScriptedProvider([result("not-json")])

    with client_for(provider) as client:
        response = post(client, make_request(modules=("action_items",)))

    assert response.status_code == 502
    assert ErrorEnvelope.model_validate(response.json()).code == "INVALID_STRUCTURED_OUTPUT"
    assert len(provider.requests) == 1


def test_empty_actions_contradicted_by_transcript_commitment_fails_closed():
    provider = ScriptedProvider(
        [
            result(json.dumps({"meeting_summary": None, "action_items": []})),
            result(verifier_content(["actions.absence"], overrides={"actions.absence": "unsupported"})),
        ]
    )

    with client_for(provider) as client:
        response = post(
            client,
            make_request(
                modules=("action_items",),
                transcript_text="Tôi sẽ gửi bản ghi chú trước thứ Sáu.",
            ),
        )

    assert response.status_code == 502
    assert ErrorEnvelope.model_validate(response.json()).code == "UNVERIFIED_EVIDENCE"


def test_summary_duration_rounding_to_zero_fails_before_provider_call():
    provider = supported_provider(modules=("meeting_summary",))
    request = make_request(modules=("meeting_summary",))
    request["meeting"]["duration_seconds"] = 0.1
    request["transcript"]["segments"][0]["start"] = 0.0
    request["transcript"]["segments"][0]["end"] = 0.05
    ExtractionRequest.model_validate(request)

    with client_for(provider) as client:
        response = post(client, request)

    assert response.status_code == 400
    assert ErrorEnvelope.model_validate(response.json()).code == "VALIDATION_ERROR"
    assert provider.requests == []


def test_tiny_positive_duration_is_allowed_for_actions_only():
    provider = supported_provider(modules=("action_items",))
    request = make_request(modules=("action_items",))
    request["meeting"]["duration_seconds"] = 0.1
    request["transcript"]["segments"][0]["start"] = 0.0
    request["transcript"]["segments"][0]["end"] = 0.05
    ExtractionRequest.model_validate(request)

    with client_for(provider) as client:
        response = post(client, request)

    assert response.status_code == 200
    assert response.json()["modules"]["action_items"]
    assert len(provider.requests) == 2


@pytest.mark.parametrize("authorization", [None, "Bearer incorrect-token"])
def test_missing_or_invalid_bearer_token_returns_401_without_provider_call(authorization):
    provider = supported_provider(modules=("action_items",))
    headers = {} if authorization is None else {"Authorization": authorization}

    with client_for(provider) as client:
        response = client.post(
            "/v1/extractions",
            json=make_request(modules=("action_items",)),
            headers=headers,
        )

    assert response.status_code == 401
    assert ErrorEnvelope.model_validate(response.json()).code == "AUTHENTICATION_REQUIRED"
    assert provider.requests == []


@pytest.mark.parametrize(
    ("provider_error", "status", "code", "retryable"),
    [
        (ProviderConfigurationError(), 503, "PROVIDER_CONFIGURATION_ERROR", False),
        (ProviderRateLimitError(retry_after_seconds=12), 503, "PROVIDER_RATE_LIMIT", True),
        (ProviderTimeoutError(), 504, "PROVIDER_TIMEOUT", True),
        (ProviderFailureError(), 502, "PROVIDER_FAILURE", False),
    ],
    ids=["configuration", "rate-limit", "provider-timeout", "provider-failure"],
)
def test_provider_errors_map_without_exposing_provider_details(provider_error, status, code, retryable):
    provider = ScriptedProvider([provider_error])

    with client_for(provider) as client:
        response = post(client, make_request(modules=("action_items",)))

    envelope = ErrorEnvelope.model_validate(response.json())
    assert response.status_code == status
    assert envelope.code == code
    assert envelope.retryable is retryable
    if code == "PROVIDER_RATE_LIMIT":
        assert envelope.retry_after_seconds == 12
    assert "transcript" not in response.text.lower()


def test_provider_timeout_setting_bounds_each_call():
    class SlowProvider:
        async def generate(self, request: ProviderRequest) -> ProviderResult:
            await asyncio.sleep(0.05)
            return result(candidate_content(modules=("action_items",)))

    provider = SlowProvider()
    settings = make_settings(llm_service_provider_timeout_seconds=0.005)
    service = create_verified_extraction_service(
        settings, provider=provider, provider_name="slow-provider"
    )

    with PipelineTestClient(create_app(settings=settings, extraction_service=service)) as client:
        response = post(client, make_request(modules=("action_items",)))

    assert response.status_code == 504
    assert ErrorEnvelope.model_validate(response.json()).code == "PROVIDER_TIMEOUT"


def test_request_timeout_maps_separately_from_provider_timeout():
    class SlowProvider:
        async def generate(self, request: ProviderRequest) -> ProviderResult:
            await asyncio.sleep(0.05)
            return result(candidate_content(modules=("action_items",)))

    settings = make_settings(
        llm_service_provider_timeout_seconds=1,
        llm_service_request_timeout_seconds=0.005,
    )
    service = create_verified_extraction_service(
        settings, provider=SlowProvider(), provider_name="slow-provider"
    )

    with PipelineTestClient(create_app(settings=settings, extraction_service=service)) as client:
        response = post(client, make_request(modules=("action_items",)))

    assert response.status_code == 504
    assert ErrorEnvelope.model_validate(response.json()).code == "REQUEST_TIMEOUT"


def test_client_cancellation_propagates_to_active_provider_call():
    class WaitingProvider:
        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.cancelled = False

        async def generate(self, request: ProviderRequest) -> ProviderResult:
            self.started.set()
            try:
                await asyncio.Event().wait()
            finally:
                self.cancelled = True

    provider = WaitingProvider()
    settings = make_settings()
    service = create_verified_extraction_service(
        settings, provider=provider, provider_name="cancellable-provider"
    )
    app = create_app(settings=settings, extraction_service=service)

    async def cancel_active_request() -> bool:
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                request_task = asyncio.create_task(
                    client.post(
                        "/v1/extractions",
                        json=make_request(modules=("action_items",)),
                        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
                    )
                )
                await asyncio.wait_for(provider.started.wait(), timeout=1)
                request_task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await request_task
                return provider.cancelled

    assert asyncio.run(cancel_active_request()) is True


def test_full_pipeline_remains_request_isolated_under_concurrency():
    class ConcurrentProvider:
        async def generate(self, provider_request: ProviderRequest) -> ProviderResult:
            user_message = provider_request.messages[1].content
            if "Claims to check:" in user_message:
                claims_text = user_message.split("Claims to check:\n", maxsplit=1)[1]
                claims = json.loads(claims_text)
                content = verifier_content([claim["claim_id"] for claim in claims])
            else:
                content = candidate_content()
            await asyncio.sleep(0.005)
            return result(content, usage=ProviderUsage(input_tokens=1, output_tokens=1))

    provider = ConcurrentProvider()
    settings = make_settings()
    service = create_verified_extraction_service(
        settings, provider=provider, provider_name="concurrent-provider"
    )
    app = create_app(settings=settings, extraction_service=service)

    async def run_concurrently():
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                headers = {"Authorization": f"Bearer {TEST_TOKEN}"}
                response_a, response_b = await asyncio.gather(
                    client.post(
                        "/v1/extractions",
                        json=make_request(request_id="request-a"),
                        headers=headers,
                    ),
                    client.post(
                        "/v1/extractions",
                        json=make_request(request_id="request-b"),
                        headers=headers,
                    ),
                )
                return response_a, response_b

    response_a, response_b = asyncio.run(run_concurrently())

    assert response_a.status_code == response_b.status_code == 200
    assert response_a.json()["request_id"] == "request-a"
    assert response_b.json()["request_id"] == "request-b"
    assert response_a.json()["processing"]["provider"] == "concurrent-provider"
    assert response_b.json()["processing"]["provider"] == "concurrent-provider"


def test_production_default_fails_closed_without_provider_configuration():
    settings = make_settings()
    app = create_app(settings=settings)

    with PipelineTestClient(app) as client:
        health = client.get("/health")
        response = post(client, make_request(modules=("action_items",)))

    assert health.status_code == 200
    assert response.status_code == 503
    assert ErrorEnvelope.model_validate(response.json()).code == "PROVIDER_CONFIGURATION_ERROR"


def test_production_default_fails_closed_with_exported_provider_key(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-exported-provider-key")
    settings = make_settings()
    app = create_app(settings=settings)

    with PipelineTestClient(app) as client:
        health = client.get("/health")
        response = post(client, make_request(modules=("action_items",)))

    assert settings.openrouter_api_key is None
    assert health.status_code == 200
    assert response.status_code == 503
    assert ErrorEnvelope.model_validate(response.json()).code == "PROVIDER_CONFIGURATION_ERROR"
    assert "test-only-exported-provider-key" not in response.text


def test_unexpected_provider_exception_is_sanitized():
    secret = "RAW-EXCEPTION-SECRET transcript-content-marker"
    provider = ScriptedProvider([RuntimeError(secret)])

    with client_for(provider) as client:
        response = post(client, make_request(modules=("action_items",)))

    assert response.status_code == 500
    assert ErrorEnvelope.model_validate(response.json()).code == "INTERNAL_ERROR"
    assert secret not in response.text
    assert "transcript-content-marker" not in response.text
