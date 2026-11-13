"""Integration checks for the internal pipeline and public response boundary."""

from __future__ import annotations

import asyncio
import json
from datetime import timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
from app.main import create_app
from app.prompts.registry import PromptRegistry
from app.providers.models import ProviderResult, ProviderUsage
from app.schemas.errors import ErrorEnvelope
from app.schemas.request import ExtractionRequest
from app.schemas.response import ExtractionResponse
from app.services.models import PreparedExtraction
from app.services.orchestration import CandidateExtractionOrchestrator
from app.services.preflight import ExtractionPreflight, PromptPreparationError
from app.services.projection import ExtractionProjector, ProjectedExtraction
from fakes.provider import FakeProvider


SERVICE_ROOT = Path(__file__).parents[2]
REQUEST_FIXTURE = SERVICE_ROOT / "tests" / "fixtures" / "requests" / "summary_actions_request.json"
TEST_TOKEN = "group-d-integration-token-do-not-log"


def make_request(
    *,
    request_id: str,
    segment_id: str,
    transcript_text: str,
) -> ExtractionRequest:
    payload: dict[str, Any] = json.loads(
        REQUEST_FIXTURE.read_text(encoding="utf-8")
    )
    payload["request_id"] = request_id
    payload["extraction"]["requested_modules"] = ["meeting_summary", "action_items"]
    payload["transcript"]["segments"] = [
        {
            "id": segment_id,
            "start": 1.0,
            "end": 2.0,
            "speaker_id": None,
            "text": transcript_text,
        }
    ]
    return ExtractionRequest.model_validate(payload)


def candidate_result(
    *,
    marker: str,
    segment_id: str,
    model_id: str,
    usage: ProviderUsage,
) -> ProviderResult:
    return ProviderResult(
        content=json.dumps(
            {
                "meeting_summary": {
                    "overview": f"Summary for {marker}",
                    "key_topics": [],
                    "source_segment_ids": [segment_id],
                },
                "action_items": [
                    {
                        "task": f"Action for {marker}",
                        "owner": None,
                        "raw_due_expression": "thứ Sáu tuần sau",
                        "priority": None,
                        "context": None,
                        "source_segment_ids": [segment_id],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        model_id=model_id,
        finish_reason="stop",
        usage=usage,
    )


def test_prompt_preparation_failure_propagates_without_provider_invocation(
    tmp_path: Path,
) -> None:
    provider = FakeProvider(
        result=candidate_result(
            marker="unused",
            segment_id="seg-unused",
            model_id="unused-model",
            usage=ProviderUsage(input_tokens=1, output_tokens=1),
        )
    )
    orchestrator = CandidateExtractionOrchestrator(
        provider=provider,
        preflight=ExtractionPreflight(
            registry=PromptRegistry(template_root=tmp_path)
        ),
        provider_name="offline-test-provider",
    )
    request = make_request(
        request_id="req-prompt-failure",
        segment_id="seg-prompt-failure",
        transcript_text="Nội dung tổng hợp tổng hợp.",
    )

    with pytest.raises(PromptPreparationError):
        asyncio.run(orchestrator.run(request))

    assert provider.requests == []


def test_concurrent_requests_remain_isolated_through_projection() -> None:
    request_a = make_request(
        request_id="req-pipeline-a",
        segment_id="seg-pipeline-a",
        transcript_text="TRANSCRIPT-A-CANARY Nội dung riêng của yêu cầu A.",
    )
    request_b = make_request(
        request_id="req-pipeline-b",
        segment_id="seg-pipeline-b",
        transcript_text="TRANSCRIPT-B-CANARY Nội dung riêng của yêu cầu B.",
    )

    class OverlappingProvider:
        def __init__(self) -> None:
            self.calls = 0
            self.active_calls = 0
            self.max_active_calls = 0
            self.both_entered = asyncio.Event()
            self.release = asyncio.Event()

        async def generate(self, provider_request):
            self.calls += 1
            self.active_calls += 1
            self.max_active_calls = max(self.max_active_calls, self.active_calls)
            user_message = provider_request.messages[1].content
            try:
                if self.calls == 2:
                    self.both_entered.set()
                await self.release.wait()
                if "TRANSCRIPT-A-CANARY" in user_message:
                    return candidate_result(
                        marker="A",
                        segment_id="seg-pipeline-a",
                        model_id="model-pipeline-a",
                        usage=ProviderUsage(input_tokens=31, output_tokens=7),
                    )
                assert "TRANSCRIPT-B-CANARY" in user_message
                return candidate_result(
                    marker="B",
                    segment_id="seg-pipeline-b",
                    model_id="model-pipeline-b",
                    usage=ProviderUsage(input_tokens=47, output_tokens=9),
                )
            finally:
                self.active_calls -= 1

    async def run_overlapping_pipeline() -> tuple[
        tuple[ProjectedExtraction, ProjectedExtraction], OverlappingProvider
    ]:
        provider = OverlappingProvider()
        orchestrator = CandidateExtractionOrchestrator(
            provider=provider,
            preflight=ExtractionPreflight(),
            provider_name="offline-concurrent-provider",
        )
        projector = ExtractionProjector()

        async def run_one(request: ExtractionRequest) -> ProjectedExtraction:
            prepared: PreparedExtraction = await orchestrator.run(request)
            return projector.project(prepared)

        tasks = [
            asyncio.create_task(run_one(request_a)),
            asyncio.create_task(run_one(request_b)),
        ]
        try:
            await asyncio.wait_for(provider.both_entered.wait(), timeout=5.0)
            provider.release.set()
            results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=5.0)
            return (results[0], results[1]), provider
        finally:
            provider.release.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    (projected_a, projected_b), provider = asyncio.run(run_overlapping_pipeline())

    assert provider.calls == 2
    assert provider.max_active_calls == 2
    assert projected_a.prepared_extraction.request is request_a
    assert projected_b.prepared_extraction.request is request_b
    assert projected_a.prepared_extraction.request.transcript.segments[0].text.startswith(
        "TRANSCRIPT-A-CANARY"
    )
    assert projected_b.prepared_extraction.request.transcript.segments[0].text.startswith(
        "TRANSCRIPT-B-CANARY"
    )
    assert projected_a.meeting_summary is not None
    assert projected_a.meeting_summary.candidate.overview == "Summary for A"
    assert projected_a.meeting_summary.candidate.source_segment_ids == [
        "seg-pipeline-a"
    ]
    assert projected_a.action_items is not None
    assert projected_a.action_items[0].task == "Action for A"
    assert projected_a.action_items[0].source_segment_ids == ["seg-pipeline-a"]
    assert projected_a.prepared_extraction.model_id == "model-pipeline-a"
    assert projected_a.prepared_extraction.token_usage == ProviderUsage(
        input_tokens=31, output_tokens=7
    )
    assert projected_a.prepared_extraction.provider == "offline-concurrent-provider"
    assert projected_a.prepared_extraction.prompt_version == "extract-v1.0"
    assert projected_a.prepared_extraction.candidate_schema_version == "candidate-v1"
    assert projected_a.prepared_extraction.started_at is not None
    assert projected_a.prepared_extraction.completed_at is not None
    assert projected_a.prepared_extraction.started_at.tzinfo is timezone.utc
    assert projected_a.prepared_extraction.completed_at.tzinfo is timezone.utc
    assert (
        projected_a.prepared_extraction.started_at
        <= projected_a.prepared_extraction.completed_at
    )
    assert projected_b.meeting_summary is not None
    assert projected_b.meeting_summary.candidate.overview == "Summary for B"
    assert projected_b.meeting_summary.candidate.source_segment_ids == [
        "seg-pipeline-b"
    ]
    assert projected_b.action_items is not None
    assert projected_b.action_items[0].task == "Action for B"
    assert projected_b.action_items[0].source_segment_ids == ["seg-pipeline-b"]
    assert projected_b.prepared_extraction.model_id == "model-pipeline-b"
    assert projected_b.prepared_extraction.token_usage == ProviderUsage(
        input_tokens=47, output_tokens=9
    )
    assert projected_b.prepared_extraction.provider == "offline-concurrent-provider"
    assert projected_b.prepared_extraction.prompt_version == "extract-v1.0"
    assert projected_b.prepared_extraction.candidate_schema_version == "candidate-v1"
    assert projected_b.prepared_extraction.started_at is not None
    assert projected_b.prepared_extraction.completed_at is not None
    assert projected_b.prepared_extraction.started_at.tzinfo is timezone.utc
    assert projected_b.prepared_extraction.completed_at.tzinfo is timezone.utc
    assert (
        projected_b.prepared_extraction.started_at
        <= projected_b.prepared_extraction.completed_at
    )


def test_invalid_injected_extraction_response_maps_to_error_envelope() -> None:
    request_payload: dict[str, Any] = json.loads(
        REQUEST_FIXTURE.read_text(encoding="utf-8")
    )

    class InvalidExtractionService:
        async def extract(self, request: ExtractionRequest) -> ExtractionResponse:
            return {"status": "completed"}  # type: ignore[return-value]

    app = create_app(
        settings=Settings(llm_service_token=SecretStr(TEST_TOKEN)),
        extraction_service=InvalidExtractionService(),
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/extractions",
            json=request_payload,
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )

    assert response.status_code == 502
    envelope = ErrorEnvelope.model_validate(response.json())
    assert envelope.code == "INVALID_STRUCTURED_OUTPUT"
    assert envelope.request_id == request_payload["request_id"]
    assert TEST_TOKEN not in response.text
