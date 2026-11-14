"""Executable deterministic pairwise coverage for completion notifications."""

from __future__ import annotations

import asyncio
import itertools
import json
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.core.config import Settings
from app.core.errors import ExtractionServiceError
from app.main import create_app
from app.schemas.errors import ErrorEnvelope
from app.schemas.request import ExtractionRequest
from app.schemas.response import ExtractionResponse
from app.services.notification import CompletionEvent


SERVICE_ROOT = Path(__file__).parents[2]
FIXTURES = SERVICE_ROOT / "tests" / "fixtures"
PAIRWISE_TEST_TOKEN = "pairwise-integration-token-do-not-log"
TRANSCRIPT_CANARY = "PAIRWISE-TRANSCRIPT-CANARY"

FACTORS: dict[str, tuple[object, ...]] = {
    "size": ("small", "exact", "over"),
    "extraction": (
        "success",
        "provider_error",
        "structural_invalid",
        "request_timeout",
        "size_reject",
    ),
    "notification": ("returns", "raises", "times_out", "not_attempted"),
    "concurrency": (1, 2, 8),
}

PAIRWISE_ROWS: tuple[tuple[str, str, str, str, int], ...] = (
    ("PW01", "small", "success", "returns", 1),
    ("PW02", "small", "provider_error", "not_attempted", 2),
    ("PW03", "exact", "success", "raises", 2),
    ("PW04", "exact", "structural_invalid", "not_attempted", 1),
    ("PW05", "over", "size_reject", "not_attempted", 8),
    ("PW06", "small", "success", "times_out", 8),
    ("PW07", "exact", "request_timeout", "not_attempted", 8),
    ("PW08", "small", "success", "raises", 1),
    ("PW09", "small", "structural_invalid", "not_attempted", 2),
    ("PW10", "small", "request_timeout", "not_attempted", 1),
    ("PW11", "exact", "success", "returns", 2),
    ("PW12", "exact", "success", "times_out", 1),
    ("PW13", "exact", "provider_error", "not_attempted", 1),
    ("PW14", "over", "size_reject", "not_attempted", 1),
    ("PW15", "over", "size_reject", "not_attempted", 2),
    ("PW16", "small", "success", "returns", 8),
    ("PW17", "small", "success", "raises", 8),
    ("PW18", "small", "success", "times_out", 2),
    ("PW19", "small", "provider_error", "not_attempted", 8),
    ("PW20", "small", "structural_invalid", "not_attempted", 8),
    ("PW21", "small", "request_timeout", "not_attempted", 2),
)


def _is_feasible(size: str, extraction: str, notification: str) -> bool:
    if (size == "over") != (extraction == "size_reject"):
        return False
    if extraction != "success":
        return notification == "not_attempted"
    return notification in {"returns", "raises", "times_out"}


def _feasible_combinations() -> list[tuple[object, ...]]:
    return [
        combination
        for combination in itertools.product(*FACTORS.values())
        if _is_feasible(
            str(combination[0]),
            str(combination[1]),
            str(combination[2]),
        )
    ]


def _factor_pairs(rows: list[tuple[object, ...]]) -> set[tuple[int, int, object, object]]:
    pairs: set[tuple[int, int, object, object]] = set()
    for row in rows:
        for left, right in itertools.combinations(range(len(FACTORS)), 2):
            pairs.add((left, right, row[left], row[right]))
    return pairs


def test_pairwise_dataset_covers_every_feasible_factor_pair() -> None:
    feasible = _feasible_combinations()
    selected = [row[1:] for row in PAIRWISE_ROWS]
    feasible_pairs = _factor_pairs(feasible)
    selected_pairs = _factor_pairs(selected)
    uncovered_pairs = feasible_pairs - selected_pairs

    assert len(feasible) == 39
    assert len(feasible_pairs) == 61
    assert len(PAIRWISE_ROWS) == 21
    assert len(selected) == len({tuple(row) for row in selected})
    assert all(
        all(
            value in allowed_values
            for value, allowed_values in zip(row, FACTORS.values(), strict=True)
        )
        and _is_feasible(str(row[0]), str(row[1]), str(row[2]))
        for row in selected
    )
    assert uncovered_pairs == set()


class ConcurrentRequestGate:
    """Hold requests at the ASGI edge until every row request has arrived."""

    def __init__(self, app: Any, expected_requests: int) -> None:
        self.app = app
        self.expected_requests = expected_requests
        self.arrivals = 0
        self.active = 0
        self.max_active = 0
        self.all_arrived = asyncio.Event()

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        self.arrivals += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        if self.arrivals == self.expected_requests:
            self.all_arrived.set()
        try:
            await asyncio.wait_for(self.all_arrived.wait(), timeout=2)
            await self.app(scope, receive, send)
        finally:
            self.active -= 1


class PairwiseExtractionService:
    def __init__(
        self,
        *,
        outcome: str,
        expected_calls: int,
        response_template: ExtractionResponse,
    ) -> None:
        self.outcome = outcome
        self.expected_calls = expected_calls
        self.response_template = response_template
        self.requests: list[str] = []
        self.cancelled_requests: list[str] = []
        self.all_entered = asyncio.Event()

    async def extract(self, request: ExtractionRequest) -> Any:
        self.requests.append(request.request_id)
        if len(self.requests) == self.expected_calls:
            self.all_entered.set()
        await asyncio.wait_for(self.all_entered.wait(), timeout=1)

        if self.outcome == "provider_error":
            raise ExtractionServiceError(code="PROVIDER_FAILURE")
        if self.outcome == "structural_invalid":
            return {"status": "completed"}
        if self.outcome == "request_timeout":
            try:
                await asyncio.Event().wait()
            finally:
                self.cancelled_requests.append(request.request_id)
        return self.response_template.model_copy(
            update={"request_id": request.request_id, "meeting_id": request.meeting.id}
        )


class PairwiseNotifier:
    def __init__(self, outcome: str) -> None:
        self.outcome = outcome
        self.attempts: list[dict[str, str]] = []
        self.completed: list[dict[str, str]] = []
        self.cancelled_requests: list[str] = []

    async def dispatch(self, event: CompletionEvent) -> None:
        recorded = dict(event)
        self.attempts.append(recorded)
        if self.outcome == "raises":
            raise RuntimeError("PAIRWISE-NOTIFIER-DETAIL-CANARY")
        if self.outcome == "times_out":
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled_requests.append(event["request_id"])
                raise
        self.completed.append(recorded)


def _compact_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _request_payload(index: int) -> dict[str, Any]:
    payload = json.loads(
        (FIXTURES / "requests" / "full_valid_request.json").read_text(encoding="utf-8")
    )
    payload["request_id"] = f"pairwise-request-{index:02d}"
    payload["meeting"]["id"] = f"pairwise-meeting-{index:02d}"
    payload["transcript"]["segments"][0]["text"] = TRANSCRIPT_CANARY
    return payload


@pytest.mark.parametrize("row", PAIRWISE_ROWS, ids=[row[0] for row in PAIRWISE_ROWS])
def test_pairwise_completion_notification_scenario(
    row: tuple[str, str, str, str, int],
    caplog: pytest.LogCaptureFixture,
) -> None:
    row_id, size, extraction, notification, concurrency = row
    payloads = [_request_payload(index) for index in range(concurrency)]
    valid_bodies = [_compact_bytes(payload) for payload in payloads]
    assert len({len(body) for body in valid_bodies}) == 1
    for body in valid_bodies:
        ExtractionRequest.model_validate_json(body)

    if size == "over":
        request_bodies = [body + b" " for body in valid_bodies]
        max_request_bytes = len(valid_bodies[0])
        assert all(len(body) == max_request_bytes + 1 for body in request_bodies)
    else:
        request_bodies = valid_bodies
        max_request_bytes = len(valid_bodies[0]) if size == "exact" else len(valid_bodies[0]) + 32
        if size == "exact":
            assert all(len(body) == max_request_bytes for body in request_bodies)
        else:
            assert all(len(body) < max_request_bytes for body in request_bodies)
    for body in request_bodies:
        ExtractionRequest.model_validate_json(body)

    response_template = ExtractionResponse.model_validate(
        json.loads(
            (FIXTURES / "responses" / "full_valid_response.json").read_text(encoding="utf-8")
        )
    )
    extraction_service = PairwiseExtractionService(
        outcome=extraction,
        expected_calls=concurrency,
        response_template=response_template,
    )
    notifier = PairwiseNotifier(notification)
    settings = Settings(
        llm_service_token=SecretStr(PAIRWISE_TEST_TOKEN),
        llm_service_max_request_bytes=max_request_bytes,
        llm_service_request_timeout_seconds=0.05,
        llm_service_notification_timeout_seconds=0.02,
    )
    app = create_app(
        settings=settings,
        extraction_service=extraction_service,
        completion_notifier=notifier,
    )
    request_gate = ConcurrentRequestGate(app, concurrency)

    async def invoke_row() -> list[Any]:
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=request_gate),
                base_url="http://pairwise-test",
            ) as client:
                headers = {
                    "Authorization": f"Bearer {PAIRWISE_TEST_TOKEN}",
                    "Content-Type": "application/json",
                }
                responses = await asyncio.wait_for(
                    asyncio.gather(
                        *(
                            client.post(
                                "/v1/extractions",
                                content=body,
                                headers={
                                    **headers,
                                    "Content-Length": str(len(body)),
                                },
                            )
                            for body in request_bodies
                        )
                    ),
                    timeout=4,
                )
                return list(responses)

    responses = asyncio.run(invoke_row())
    request_ids = {payload["request_id"] for payload in payloads}
    expected_meetings = {
        payload["request_id"]: payload["meeting"]["id"] for payload in payloads
    }

    assert len(responses) == concurrency, row_id
    assert request_gate.arrivals == concurrency
    assert request_gate.max_active == concurrency
    assert len(extraction_service.requests) == (0 if extraction == "size_reject" else concurrency)
    assert set(extraction_service.requests) == (
        set() if extraction == "size_reject" else request_ids
    )

    expected_status_and_code = {
        "provider_error": (502, "PROVIDER_FAILURE"),
        "structural_invalid": (502, "INVALID_STRUCTURED_OUTPUT"),
        "request_timeout": (504, "REQUEST_TIMEOUT"),
        "size_reject": (413, "PAYLOAD_TOO_LARGE"),
    }
    if extraction == "success":
        assert all(response.status_code == 200 for response in responses)
        successful_responses = [
            ExtractionResponse.model_validate(response.json()) for response in responses
        ]
        assert {
            response.request_id: response.meeting_id for response in successful_responses
        } == expected_meetings
        assert all(response.status == "completed" for response in successful_responses)
    else:
        expected_status, expected_code = expected_status_and_code[extraction]
        for payload, response in zip(payloads, responses, strict=True):
            envelope = ErrorEnvelope.model_validate(response.json())
            assert response.status_code == expected_status
            assert envelope.statusCode == expected_status
            assert envelope.code == expected_code
            expected_request_id = None if extraction == "size_reject" else payload["request_id"]
            assert envelope.request_id == expected_request_id
        assert notifier.attempts == []

    if extraction == "request_timeout":
        assert set(extraction_service.cancelled_requests) == request_ids
    else:
        assert extraction_service.cancelled_requests == []

    if extraction == "success":
        assert len(notifier.attempts) == concurrency
        assert {
            event["request_id"]: event["meeting_id"] for event in notifier.attempts
        } == expected_meetings
        assert all(
            set(event) == {"event_type", "request_id", "meeting_id", "status"}
            and event["event_type"] == "extraction.completed"
            and event["status"] == "completed"
            for event in notifier.attempts
        )
        if notification == "returns":
            assert notifier.completed == notifier.attempts
            assert notifier.cancelled_requests == []
        elif notification == "raises":
            assert notifier.completed == []
            assert notifier.cancelled_requests == []
            assert caplog.text.count("Completion notification dispatch failed.") == concurrency
        else:
            assert notifier.completed == []
            assert set(notifier.cancelled_requests) == request_ids
            assert caplog.text.count("Completion notification timed out.") == concurrency
    else:
        assert notifier.attempts == []
        assert notifier.completed == []
        assert notifier.cancelled_requests == []

    assert PAIRWISE_TEST_TOKEN not in caplog.text
    assert TRANSCRIPT_CANARY not in caplog.text
    assert "PAIRWISE-NOTIFIER-DETAIL-CANARY" not in caplog.text
