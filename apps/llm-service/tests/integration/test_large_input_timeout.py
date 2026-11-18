"""N18: a large valid request reaches extraction and follows request timeout."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.core.config import Settings
from app.main import create_app
from app.schemas.errors import ErrorEnvelope
from app.schemas.request import ExtractionRequest
from app.services.notification import CompletionEvent


SERVICE_ROOT = Path(__file__).parents[2]
REQUEST_FIXTURE = SERVICE_ROOT / "tests/fixtures/requests/full_valid_request.json"
TEST_TOKEN = "vt058-n18-test-token-do-not-log"
OUTER_WATCHDOG_SECONDS = 5.0


class BlockingExtractionService:
    """Signal entry, then wait until the HTTP request timeout cancels us."""

    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.release = asyncio.Event()
        self.request_ids: list[str] = []

    async def extract(self, request: ExtractionRequest) -> Any:
        self.request_ids.append(request.request_id)
        self.entered.set()
        try:
            await self.release.wait()
        finally:
            self.cancelled.set()


class RecordingNotifier:
    def __init__(self) -> None:
        self.attempts: list[dict[str, str]] = []

    async def dispatch(self, event: CompletionEvent) -> None:
        self.attempts.append(dict(event))


def compact_json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def make_near_limit_body(max_request_bytes: int) -> tuple[dict[str, Any], bytes]:
    payload = json.loads(REQUEST_FIXTURE.read_text(encoding="utf-8"))
    payload["request_id"] = "vt058-n18-large-timeout-request"
    payload["meeting"]["id"] = "vt058-n18-large-timeout-meeting"
    target_bytes = max_request_bytes - 512
    body = compact_json_bytes(payload)
    padding_bytes = target_bytes - len(body)
    assert padding_bytes > 0
    payload["transcript"]["segments"][0]["text"] += "x" * padding_bytes
    body = compact_json_bytes(payload)

    assert len(body) == target_bytes
    assert payload["transcript"]["segments"]
    ExtractionRequest.model_validate(payload)
    return payload, body


def test_large_valid_request_reaches_extractor_then_returns_request_timeout() -> None:
    max_request_bytes = 1024 * 1024
    payload, body = make_near_limit_body(max_request_bytes)
    service = BlockingExtractionService()
    notifier = RecordingNotifier()
    settings = Settings(
        llm_service_token=SecretStr(TEST_TOKEN),
        llm_service_max_request_bytes=max_request_bytes,
        llm_service_request_timeout_seconds=0.1,
        llm_service_notification_timeout_seconds=1.0,
    )
    app = create_app(
        settings=settings,
        extraction_service=service,
        completion_notifier=notifier,
    )

    async def send_request():
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://vt058-n18-test",
            ) as client:
                return await asyncio.wait_for(
                    client.post(
                        "/v1/extractions",
                        content=body,
                        headers={
                            "Authorization": f"Bearer {TEST_TOKEN}",
                            "Content-Type": "application/json",
                        },
                    ),
                    timeout=OUTER_WATCHDOG_SECONDS,
                )

    started_ns = time.perf_counter_ns()
    try:
        response = asyncio.run(send_request())
    except TimeoutError:
        pytest.fail("N18 request exceeded the independent outer watchdog")
    elapsed_seconds = (time.perf_counter_ns() - started_ns) / 1_000_000_000

    assert len(body) == max_request_bytes - 512
    assert len(body) < max_request_bytes
    assert ExtractionRequest.model_validate_json(body).request_id == payload["request_id"]
    assert response.status_code != 413
    assert response.status_code == 504
    envelope = ErrorEnvelope.model_validate(response.json())
    assert envelope.statusCode == 504
    assert envelope.code == "REQUEST_TIMEOUT"
    assert envelope.request_id == payload["request_id"]
    assert service.request_ids == [payload["request_id"]]
    assert service.entered.is_set()
    assert service.cancelled.is_set()
    assert notifier.attempts == []
    assert elapsed_seconds < OUTER_WATCHDOG_SECONDS

