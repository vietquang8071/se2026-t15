"""Offline integration tests for candidate extraction orchestration."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from asgi_client import ASGITestClient as TestClient
from pydantic import SecretStr

from app.core.config import Settings
from app.main import create_app
from app.providers.models import ProviderResult, ProviderUsage
from app.providers.openrouter import OpenRouterAdapter
from app.schemas.errors import ErrorEnvelope
from app.schemas.request import ExtractionRequest
from app.services.models import PreparedExtraction
from app.services.verified_extraction import VerifiedExtractionService
from app.services.factory import create_candidate_orchestrator
from app.services.orchestration import CandidateExtractionOrchestrator
from app.services.preflight import ExtractionPreflight
from fakes.provider import FakeProvider


SERVICE_ROOT = Path(__file__).parents[2]
REQUEST_FIXTURE = SERVICE_ROOT / "tests" / "fixtures" / "requests" / "summary_actions_request.json"
TEST_TOKEN = "group-b-integration-token-do-not-log"


def make_request(
    modules: tuple[str, ...] = ("meeting_summary", "action_items"),
    *,
    request_id: str = "req-group-b-integration",
    segments: list[dict[str, object]] | None = None,
) -> ExtractionRequest:
    payload = json.loads(REQUEST_FIXTURE.read_text(encoding="utf-8"))
    payload["request_id"] = request_id
    payload["extraction"]["requested_modules"] = list(modules)
    if segments is not None:
        payload["transcript"]["segments"] = segments
    return ExtractionRequest.model_validate(payload)


def summary_candidate(*, overview: str, source_id: str) -> dict[str, object]:
    return {
        "overview": overview,
        "key_topics": [],
        "source_segment_ids": [source_id],
    }


def actions_candidate(*, task: str, source_id: str) -> list[dict[str, object]]:
    return [
        {
            "task": task,
            "owner": None,
            "raw_due_expression": None,
            "priority": None,
            "context": None,
            "source_segment_ids": [source_id],
        }
    ]


def result(
    content: dict[str, object], *, model_id: str, usage: ProviderUsage | None
) -> ProviderResult:
    return ProviderResult(
        content=json.dumps(content, ensure_ascii=False),
        model_id=model_id,
        finish_reason="stop",
        usage=usage,
    )


def test_it01_real_preflight_and_parser_run_with_offline_fake_provider() -> None:
    request = make_request()
    provider = FakeProvider(
        result=result(
            {
                "meeting_summary": summary_candidate(
                    overview="Tổng hợp nội bộ của Group B.", source_id="seg-a2"
                ),
                "action_items": actions_candidate(
                    task="Gửi bản ghi chú", source_id="seg-a1"
                ),
            },
            model_id="offline-integration-model",
            usage=ProviderUsage(input_tokens=88, output_tokens=20),
        )
    )
    orchestrator = CandidateExtractionOrchestrator(
        provider=provider,
        preflight=ExtractionPreflight(),
        provider_name="offline-integration-provider",
    )

    extraction = asyncio.run(orchestrator.run(request))

    assert len(provider.requests) == 1
    assert len(provider.requests[0].messages) == 2
    assert provider.requests[0].structured_output_mode == "json_object"
    assert extraction.request is request
    assert extraction.prompt_version == "extract-v1.0"
    assert extraction.candidate_schema_version == "candidate-v1"
    assert extraction.candidate.meeting_summary is not None
    assert extraction.candidate.meeting_summary.overview == "Tổng hợp nội bộ của Group B."
    assert extraction.candidate.action_items is not None
    assert extraction.candidate.action_items[0].task == "Gửi bản ghi chú"
    assert extraction.provider == "offline-integration-provider"
    assert extraction.model_id == "offline-integration-model"


def test_it02_concurrent_requests_keep_candidate_and_metadata_isolated() -> None:
    request_a = make_request(
        ("meeting_summary",),
        request_id="req-concurrent-a",
        segments=[
            {
                "id": "seg-a",
                "start": 1.0,
                "end": 2.0,
                "speaker_id": None,
                "text": "TRANSCRIPT-A-CANARY nội dung riêng A.",
            }
        ],
    )
    request_b = make_request(
        ("action_items",),
        request_id="req-concurrent-b",
        segments=[
            {
                "id": "seg-b",
                "start": 1.0,
                "end": 2.0,
                "speaker_id": None,
                "text": "TRANSCRIPT-B-CANARY nội dung riêng B.",
            }
        ],
    )

    class ConcurrentProvider:
        def __init__(self) -> None:
            self.calls = 0
            self.active = 0
            self.max_active = 0
            self.both_entered = asyncio.Event()
            self.release = asyncio.Event()

        async def generate(self, provider_request):
            self.calls += 1
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            user_content = provider_request.messages[1].content
            try:
                if self.calls == 2:
                    self.both_entered.set()
                await self.release.wait()
                if "TRANSCRIPT-A-CANARY" in user_content:
                    return result(
                        {
                            "meeting_summary": summary_candidate(
                                overview="CANDIDATE-A-CANARY", source_id="seg-a"
                            ),
                            "action_items": None,
                        },
                        model_id="model-a",
                        usage=ProviderUsage(input_tokens=11, output_tokens=3),
                    )
                assert "TRANSCRIPT-B-CANARY" in user_content
                return result(
                    {
                        "meeting_summary": None,
                        "action_items": actions_candidate(
                            task="CANDIDATE-B-CANARY", source_id="seg-b"
                        ),
                    },
                    model_id="model-b",
                    usage=ProviderUsage(input_tokens=22, output_tokens=4),
                )
            finally:
                self.active -= 1

    async def run_overlapping_requests() -> tuple[
        PreparedExtraction,
        PreparedExtraction,
        ConcurrentProvider,
    ]:
        provider = ConcurrentProvider()
        orchestrator = CandidateExtractionOrchestrator(
            provider=provider,
            preflight=ExtractionPreflight(),
            provider_name="offline-concurrent-provider",
        )
        task_a = asyncio.create_task(orchestrator.run(request_a))
        task_b = asyncio.create_task(orchestrator.run(request_b))
        await asyncio.wait_for(provider.both_entered.wait(), timeout=1.0)
        provider.release.set()
        output_a, output_b = await asyncio.gather(task_a, task_b)
        return output_a, output_b, provider

    extraction_a, extraction_b, provider = asyncio.run(run_overlapping_requests())

    assert provider.calls == 2
    assert provider.max_active == 2
    assert extraction_a.request is request_a
    assert extraction_a.candidate.meeting_summary is not None
    assert extraction_a.candidate.meeting_summary.overview == "CANDIDATE-A-CANARY"
    assert extraction_a.candidate.action_items is None
    assert extraction_a.model_id == "model-a"
    assert extraction_a.token_usage == ProviderUsage(input_tokens=11, output_tokens=3)
    assert extraction_b.request is request_b
    assert extraction_b.candidate.meeting_summary is None
    assert extraction_b.candidate.action_items is not None
    assert extraction_b.candidate.action_items[0].task == "CANDIDATE-B-CANARY"
    assert extraction_b.model_id == "model-b"
    assert extraction_b.token_usage == ProviderUsage(input_tokens=22, output_tokens=4)


def test_it03_production_factory_constructs_openrouter_without_credentials_or_network() -> None:
    settings = Settings(openrouter_api_key=None)

    orchestrator = create_candidate_orchestrator(settings)

    assert isinstance(orchestrator, CandidateExtractionOrchestrator)
    assert isinstance(orchestrator._provider, OpenRouterAdapter)
    assert orchestrator._provider_name == "openrouter"


@pytest.mark.parametrize("provider_name", [None, "", "   "])
def test_it03_custom_provider_requires_nonempty_identity(provider_name: str | None) -> None:
    settings = Settings(openrouter_api_key=None)
    provider = FakeProvider(
        result=result(
            {"meeting_summary": None, "action_items": []},
            model_id="fake-model",
            usage=None,
        )
    )

    with pytest.raises(ValueError):
        create_candidate_orchestrator(
            settings,
            provider=provider,
            provider_name=provider_name,
        )


def test_it03_factory_rejects_inconsistent_provider_identity() -> None:
    settings = Settings(openrouter_api_key=None)
    provider = FakeProvider(
        result=result(
            {"meeting_summary": None, "action_items": []},
            model_id="fake-model",
            usage=None,
        )
    )

    with pytest.raises(ValueError):
        create_candidate_orchestrator(settings, provider_name="offline-fake")
    with pytest.raises(ValueError):
        create_candidate_orchestrator(
            settings,
            provider=provider,
            provider_name="openrouter",
        )
    with pytest.raises(ValueError):
        create_candidate_orchestrator(
            settings,
            provider=OpenRouterAdapter(settings),
            provider_name="offline-fake",
        )


def test_it03_factory_accepts_custom_provider_with_explicit_identity() -> None:
    settings = Settings(openrouter_api_key=None)
    provider = FakeProvider(
        result=result(
            {"meeting_summary": None, "action_items": []},
            model_id="fake-model",
            usage=None,
        )
    )

    orchestrator = create_candidate_orchestrator(
        settings,
        provider=provider,
        provider_name="offline-fake",
    )

    assert orchestrator._provider is provider
    assert orchestrator._provider_name == "offline-fake"


def test_it04_fastapi_health_and_extraction_remain_fail_closed() -> None:
    settings = Settings(
        llm_service_token=SecretStr(TEST_TOKEN),
        openrouter_api_key=None,
    )
    app = create_app(settings=settings)
    assert isinstance(app.state.extraction_service, VerifiedExtractionService)
    request_payload = json.loads(REQUEST_FIXTURE.read_text(encoding="utf-8"))

    with TestClient(app) as client:
        health_response = client.get("/health")
        extraction_response = client.post(
            "/v1/extractions",
            json=request_payload,
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )

    assert health_response.status_code == 200
    assert extraction_response.status_code == 503
    error = ErrorEnvelope.model_validate(extraction_response.json())
    assert error.code == "PROVIDER_CONFIGURATION_ERROR"
    assert TEST_TOKEN not in extraction_response.text
