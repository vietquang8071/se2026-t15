"""Offline N17 and large-input experiments for VT-058 Phase 07.

Run from apps/llm-service with its existing virtualenv Python:
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python \
      tests/manual/vt058_phase07_benchmark.py --mode n17
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python \
      tests/manual/vt058_phase07_benchmark.py --mode large-input
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import platform
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

try:
    import resource
except ImportError:  # pragma: no cover - Windows has no resource module
    resource = None

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.core.config import Settings
from app.main import create_app
from app.providers.models import ProviderRequest, ProviderResult, ProviderUsage
from app.schemas.errors import ErrorEnvelope
from app.schemas.request import ExtractionRequest
from app.schemas.response import ExtractionResponse
from app.services.factory import create_verified_extraction_service
from app.services.notification import CompletionEvent


SERVICE_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = SERVICE_ROOT / "tests" / "fixtures"
REQUEST_FIXTURE = FIXTURES / "requests" / "summary_actions_request.json"
RESOURCE_REQUEST_FIXTURE = FIXTURES / "requests" / "full_valid_request.json"
RESOURCE_RESPONSE_FIXTURE = FIXTURES / "responses" / "full_valid_response.json"
SERVICE_TOKEN = "vt058-phase07-offline-token-do-not-log"
MAX_REQUEST_BYTES = 1024 * 1024
OUTER_WATCHDOG_SECONDS = 90.0
GATE_WATCHDOG_SECONDS = 30.0
ALLOWED_EVENT_KEYS = {"event_type", "request_id", "meeting_id", "status"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def compact_json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def percentile_nearest_rank(values: list[float], percentile: float) -> float | None:
    """Nearest rank: sorted_values[ceil(p * n) - 1], with p in [0, 1]."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def latency_summary(values: list[float]) -> dict[str, float | None]:
    return {
        "p50_ms": percentile_nearest_rank(values, 0.50),
        "p95_ms": percentile_nearest_rank(values, 0.95),
        "p99_ms": percentile_nearest_rank(values, 0.99),
        "max_ms": max(values) if values else None,
    }


def sized_valid_request(
    *,
    fixture: Path,
    request_id: str,
    meeting_id: str,
    target_bytes: int | None = None,
) -> tuple[dict[str, Any], bytes]:
    payload = load_json(fixture)
    payload["request_id"] = request_id
    payload["meeting"]["id"] = meeting_id
    body = compact_json_bytes(payload)
    if target_bytes is not None:
        padding_bytes = target_bytes - len(body)
        if padding_bytes < 0:
            raise ValueError(
                f"Base request is {len(body)} bytes, above target {target_bytes}."
            )
        payload["transcript"]["segments"][0]["text"] += "x" * padding_bytes
        body = compact_json_bytes(payload)
        if len(body) != target_bytes:
            raise AssertionError(
                f"Expected {target_bytes} UTF-8 bytes, serialized {len(body)}."
            )
    ExtractionRequest.model_validate(payload)
    return payload, body


class DeterministicFakeProvider:
    """Choose output from each prompt; no shared queue or call-order assumption."""

    def __init__(self) -> None:
        self.requests: list[ProviderRequest] = []
        self.candidate_calls = 0
        self.verifier_calls = 0
        self._lock = asyncio.Lock()

    async def generate(self, request: ProviderRequest) -> ProviderResult:
        prompt = request.messages[-1].content
        verifier_marker = "Claims to check:\n"
        async with self._lock:
            self.requests.append(request)
            is_verifier = verifier_marker in prompt
            if is_verifier:
                self.verifier_calls += 1
            else:
                self.candidate_calls += 1

        if is_verifier:
            claims = json.loads(prompt.split(verifier_marker, maxsplit=1)[1])
            content = json.dumps(
                {
                    "checks": [
                        {"claim_id": claim["claim_id"], "status": "supported"}
                        for claim in claims
                    ]
                }
            )
        else:
            # This is the deterministic candidate shape used by the verified
            # extraction integration tests, for the fixture's seg-a1 segment.
            content = json.dumps(
                {
                    "meeting_summary": {
                        "overview": "Nhóm rà soát tiến độ và ghi nhận cam kết gửi ghi chú.",
                        "key_topics": [],
                        "source_segment_ids": ["seg-a1"],
                    },
                    "action_items": [
                        {
                            "task": "Gửi bản ghi chú",
                            "owner": "Alex",
                            "raw_due_expression": None,
                            "priority": None,
                            "context": None,
                            "source_segment_ids": ["seg-a1"],
                        }
                    ],
                },
                ensure_ascii=False,
            )
        return ProviderResult(
            content=content,
            model_id="vt058-offline-deterministic-model",
            finish_reason="stop",
            usage=ProviderUsage(input_tokens=20, output_tokens=10),
        )


class RecordingCompletionNotifier:
    def __init__(self) -> None:
        self.attempts: list[dict[str, Any]] = []
        self.completed: list[dict[str, Any]] = []

    async def dispatch(self, event: CompletionEvent) -> None:
        started_ns = time.perf_counter_ns()
        attempt = {"event": dict(event), "started_ns": started_ns}
        self.attempts.append(attempt)
        completed_ns = time.perf_counter_ns()
        attempt["completed_ns"] = completed_ns
        self.completed.append(attempt)


class ResponseBodyRecorder:
    """Capture time after the terminal ASGI response-body send completes."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self.body_end_ns_by_request_id: dict[str, int] = {}
        self.unassociated_terminal_bodies = 0

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        response_body = bytearray()

        async def record_send(message: dict[str, Any]) -> None:
            await send(message)
            if message.get("type") != "http.response.body":
                return
            response_body.extend(message.get("body", b""))
            if message.get("more_body", False):
                return
            ended_ns = time.perf_counter_ns()
            try:
                response = json.loads(response_body)
                request_id = response.get("request_id")
            except (TypeError, ValueError, AttributeError):
                request_id = None
            if isinstance(request_id, str):
                self.body_end_ns_by_request_id[request_id] = ended_ns
            else:
                self.unassociated_terminal_bodies += 1

        await self.app(scope, receive, record_send)


class ConcurrentArrivalGate:
    """Hold ASGI extraction requests until the full batch has arrived."""

    def __init__(self, app: Any, expected_requests: int) -> None:
        self.app = app
        self.expected_requests = expected_requests
        self.arrivals = 0
        self.active = 0
        self.max_active = 0
        self.all_arrived = asyncio.Event()

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if not (
            scope.get("type") == "http"
            and scope.get("method") == "POST"
            and scope.get("path") == "/v1/extractions"
        ):
            await self.app(scope, receive, send)
            return
        self.arrivals += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        if self.arrivals == self.expected_requests:
            self.all_arrived.set()
        try:
            await asyncio.wait_for(
                self.all_arrived.wait(), timeout=GATE_WATCHDOG_SECONDS
            )
            await self.app(scope, receive, send)
        finally:
            self.active -= 1


class ClientStartGate:
    """Ensure every client task is scheduled before any request is invoked."""

    def __init__(self, expected_requests: int) -> None:
        self.expected_requests = expected_requests
        self.scheduled = 0
        self.all_scheduled = asyncio.Event()

    async def wait(self) -> None:
        self.scheduled += 1
        if self.scheduled == self.expected_requests:
            self.all_scheduled.set()
        await asyncio.wait_for(self.all_scheduled.wait(), timeout=GATE_WATCHDOG_SECONDS)


async def send_batch(
    app: Any,
    payloads_and_bodies: list[tuple[dict[str, Any], bytes]],
    *,
    concurrency: int,
) -> dict[str, Any]:
    recorder = ResponseBodyRecorder(app)
    arrival_gate = ConcurrentArrivalGate(recorder, expected_requests=concurrency)
    client_gate = ClientStartGate(expected_requests=concurrency)
    records: list[dict[str, Any]] = [
        {
            "request_id": payload["request_id"],
            "meeting_id": payload["meeting"]["id"],
            "client_started_ns": None,
            "client_returned_ns": None,
            "status": None,
            "response": None,
            "exception_type": None,
        }
        for payload, _ in payloads_and_bodies
    ]

    async with AsyncClient(
        transport=ASGITransport(app=arrival_gate),
        base_url="http://vt058-phase07-offline",
    ) as client:

        async def invoke_one(index: int, body: bytes) -> None:
            record = records[index]
            try:
                await client_gate.wait()
                record["client_started_ns"] = time.perf_counter_ns()
                response = await client.post(
                    "/v1/extractions",
                    content=body,
                    headers={
                        "Authorization": f"Bearer {SERVICE_TOKEN}",
                        "Content-Type": "application/json",
                    },
                )
                record["response"] = response
                record["status"] = response.status_code
            except asyncio.CancelledError:
                raise
            except Exception as error:  # Keep benchmark failures in the result.
                record["exception_type"] = type(error).__name__
            finally:
                if record["client_started_ns"] is not None:
                    record["client_returned_ns"] = time.perf_counter_ns()

        tasks = [
            asyncio.create_task(invoke_one(index, body))
            for index, (_, body) in enumerate(payloads_and_bodies)
        ]
        done, pending = await asyncio.wait(tasks, timeout=OUTER_WATCHDOG_SECONDS)
        timed_out = bool(pending)
        if pending:
            for task in pending:
                task.cancel()
            await asyncio.wait(pending, timeout=2.0)
        task_exceptions = sum(
            1
            for task in done
            if not task.cancelled() and task.exception() is not None
        )

    return {
        "records": records,
        "recorder": recorder,
        "arrival_gate": arrival_gate,
        "client_scheduled": client_gate.scheduled,
        "timed_out": timed_out,
        "task_exceptions": task_exceptions,
    }


def summarize_batch(
    batch_name: str,
    batch: dict[str, Any],
    *,
    expected_mapping: dict[str, str],
    notifier: RecordingCompletionNotifier,
) -> dict[str, Any]:
    records = batch["records"]
    recorder: ResponseBodyRecorder = batch["recorder"]
    request_ids = set(expected_mapping)
    http_records = [record for record in records if record["status"] is not None]
    successful_records = [
        record for record in http_records if 200 <= record["status"] < 300
    ]
    failed_http_records = [record for record in http_records if record["status"] >= 400]
    latencies_ms = [
        (recorder.body_end_ns_by_request_id[record["request_id"]]
         - record["client_started_ns"])
        / 1_000_000
        for record in records
        if record["client_started_ns"] is not None
        and record["request_id"] in recorder.body_end_ns_by_request_id
    ]
    starts = [
        record["client_started_ns"]
        for record in records
        if record["client_started_ns"] is not None
    ]
    body_ends = [
        recorder.body_end_ns_by_request_id[request_id]
        for request_id in request_ids
        if request_id in recorder.body_end_ns_by_request_id
    ]
    if starts and body_ends:
        duration_seconds = (max(body_ends) - min(starts)) / 1_000_000_000
    else:
        duration_seconds = 0.0
    response_count = len(http_records)
    error_rate = len(failed_http_records) / response_count if response_count else None

    valid_responses: dict[str, ExtractionResponse] = {}
    response_contract_failures = 0
    association_failures = 0
    for record in successful_records:
        try:
            parsed = ExtractionResponse.model_validate(record["response"].json())
        except Exception:
            response_contract_failures += 1
            continue
        valid_responses[parsed.request_id] = parsed
        if (
            parsed.request_id != record["request_id"]
            or parsed.meeting_id != expected_mapping.get(parsed.request_id)
        ):
            association_failures += 1

    attempts = [
        item for item in notifier.attempts
        if item["event"].get("request_id") in request_ids
    ]
    completions = [
        item for item in notifier.completed
        if item["event"].get("request_id") in request_ids
    ]
    attempt_counts: dict[str, int] = {}
    event_contract_failures = 0
    for item in attempts:
        event = item["event"]
        request_id = event.get("request_id")
        attempt_counts[request_id] = attempt_counts.get(request_id, 0) + 1
        if (
            set(event) != ALLOWED_EVENT_KEYS
            or event.get("event_type") != "extraction.completed"
            or event.get("status") != "completed"
            or expected_mapping.get(request_id) != event.get("meeting_id")
        ):
            event_contract_failures += 1
    notification_association_failures = sum(
        attempt_counts.get(request_id, 0) != 1
        for request_id in valid_responses
    )
    completed_ids = {
        item["event"].get("request_id") for item in completions
    }
    notification_latency_ms = [
        (item["completed_ns"] - item["started_ns"]) / 1_000_000
        for item in completions
        if "completed_ns" in item
    ]
    notifications_after_body = sum(
        item.get("completed_ns", 0)
        > recorder.body_end_ns_by_request_id.get(item["event"].get("request_id", ""), 0)
        for item in completions
        if item["event"].get("request_id") in recorder.body_end_ns_by_request_id
    )
    post_return_after_body_ms = [
        (record["client_returned_ns"]
         - recorder.body_end_ns_by_request_id[record["request_id"]])
        / 1_000_000
        for record in records
        if record["client_returned_ns"] is not None
        and record["request_id"] in recorder.body_end_ns_by_request_id
    ]

    n_expected = len(records)
    return {
        "run": batch_name,
        "total_requests": n_expected,
        "concurrency": batch["arrival_gate"].expected_requests,
        "client_tasks_scheduled_before_release": batch["client_scheduled"],
        "asgi_requests_arrived": batch["arrival_gate"].arrivals,
        "asgi_max_active_requests": batch["arrival_gate"].max_active,
        "concurrent_start_verified": (
            batch["client_scheduled"] == n_expected
            and batch["arrival_gate"].arrivals == n_expected
            and batch["arrival_gate"].max_active == n_expected
        ),
        "response_body_end_boundary": "perf_counter_ns immediately after terminal http.response.body (more_body=false) send completes",
        "client_invocation_start_boundary": "perf_counter_ns immediately before AsyncClient.post",
        "successful_http_responses": len(successful_records),
        "failed_http_responses": len(failed_http_records),
        "http_error_rate": error_rate,
        "requests_without_http_response": n_expected - response_count,
        "requests_without_terminal_body_frame": n_expected - len(latencies_ms),
        "request_exceptions": sum(record["exception_type"] is not None for record in records),
        "outer_watchdog_timed_out": batch["timed_out"],
        "task_exceptions": batch["task_exceptions"],
        "extraction_service_results": {
            "completed_valid_response_contracts": len(valid_responses),
            "response_contract_failures": response_contract_failures,
            "request_meeting_association_validated": len(valid_responses) - association_failures,
            "request_meeting_association_failures": association_failures,
            "request_id_meeting_id_pattern": "vt058-n17-<run>-request-NNN -> vt058-n17-<run>-meeting-NNN",
        },
        "latency_ms_nearest_rank": latency_summary(latencies_ms),
        "completed_request_latency_count": len(latencies_ms),
        "throughput_responses_per_second": (
            response_count / duration_seconds if duration_seconds > 0 else 0.0
        ),
        "total_run_duration_seconds": duration_seconds,
        "notification_dispatch_attempts": len(attempts),
        "notification_successful_completions": len(completions),
        "notification_event_contract_failures": event_contract_failures,
        "notification_request_association_failures": notification_association_failures,
        "notification_processing_latency_ms_nearest_rank": latency_summary(notification_latency_ms),
        "notification_finished_after_response_body_count": notifications_after_body,
        "all_notifications_finished_after_response_body": (
            notifications_after_body == len(completions) and bool(completions)
        ),
        "httpx_post_return_after_body_ms_nearest_rank": latency_summary(post_return_after_body_ms),
        "unassociated_terminal_response_bodies": recorder.unassociated_terminal_bodies,
        "request_id_meeting_id_associations": {
            "validated": len(valid_responses) - association_failures,
            "expected": len(valid_responses),
            "sample": [
                {"request_id": request_id, "meeting_id": expected_mapping[request_id]}
                for request_id in sorted(valid_responses)[:3]
            ],
        },
        "notification_ids_without_completion": sorted(
            set(valid_responses) - completed_ids
        ),
    }


def n17_settings() -> Settings:
    return Settings(
        llm_service_token=SecretStr(SERVICE_TOKEN),
        llm_service_max_request_bytes=MAX_REQUEST_BYTES,
        llm_service_request_timeout_seconds=30.0,
        llm_service_notification_timeout_seconds=2.0,
        llm_service_provider_timeout_seconds=10.0,
        openrouter_api_key=None,
    )


def small_payloads(run_name: str, count: int) -> list[tuple[dict[str, Any], bytes]]:
    payloads_and_bodies = []
    for index in range(count):
        request_id = f"vt058-n17-{run_name}-request-{index:03d}"
        meeting_id = f"vt058-n17-{run_name}-meeting-{index:03d}"
        payload, body = sized_valid_request(
            fixture=REQUEST_FIXTURE,
            request_id=request_id,
            meeting_id=meeting_id,
        )
        payloads_and_bodies.append((payload, body))
    return payloads_and_bodies


async def run_n17() -> dict[str, Any]:
    settings = n17_settings()
    provider = DeterministicFakeProvider()
    notifier = RecordingCompletionNotifier()
    service = create_verified_extraction_service(
        settings,
        provider=provider,
        provider_name="vt058-offline-fake-provider",
    )
    app = create_app(
        settings=settings,
        extraction_service=service,
        completion_notifier=notifier,
    )
    batches: list[dict[str, Any]] = []
    async with app.router.lifespan_context(app):
        warmup_payloads = small_payloads("warmup", 8)
        warmup_batch = await send_batch(app, warmup_payloads, concurrency=8)
        batches.append(
            summarize_batch(
                "warmup-8",
                warmup_batch,
                expected_mapping={
                    payload["request_id"]: payload["meeting"]["id"]
                    for payload, _ in warmup_payloads
                },
                notifier=notifier,
            )
        )

        for run_index in (1, 2):
            run_name = f"run{run_index}"
            payloads_and_bodies = small_payloads(run_name, 200)
            if len({len(body) for _, body in payloads_and_bodies}) != 1:
                raise AssertionError("N17 requests did not retain identical body sizes.")
            batch = await send_batch(app, payloads_and_bodies, concurrency=200)
            batches.append(
                summarize_batch(
                    run_name,
                    batch,
                    expected_mapping={
                        payload["request_id"]: payload["meeting"]["id"]
                        for payload, _ in payloads_and_bodies
                    },
                    notifier=notifier,
                )
            )

    measured = batches[1:]
    p95s = [
        batch["latency_ms_nearest_rank"]["p95_ms"]
        for batch in measured
        if batch["latency_ms_nearest_rank"]["p95_ms"] is not None
    ]
    worst_p95 = max(p95s) if p95s else None
    all_http_success = all(
        batch["successful_http_responses"] == 200
        and batch["failed_http_responses"] == 0
        and batch["requests_without_http_response"] == 0
        for batch in measured
    )
    return {
        "experiment": "N17-200-concurrent-http-extractions",
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "process_count": 1,
            "event_loop_count": 1,
            "provider": "DeterministicFakeProvider; no outbound provider calls",
            "warmup": "one 8-request concurrent batch; excluded from measured batches",
        },
        "workload": {
            "measured_batches": 2,
            "requests_each": 200,
            "concurrency_each": 200,
            "unique_request_and_meeting_ids": True,
            "small_payload_bytes": len(small_payloads("size-check", 1)[0][1]),
            "payload_fixture": str(REQUEST_FIXTURE.relative_to(SERVICE_ROOT)),
        },
        "percentile_method": "nearest rank: sorted latency[ceil(p*n)-1]",
        "measured_runs": measured,
        "worst_measured_p95_ms": worst_p95,
        "p95_target_ms": 5000.0,
        "p95_target_result": (
            "PASS" if worst_p95 is not None and worst_p95 <= 5000.0 else "FAIL"
        ),
        "both_measured_batches_http_successful": all_http_success,
        "provider_calls": {
            "candidate": provider.candidate_calls,
            "verifier": provider.verifier_calls,
            "total": len(provider.requests),
        },
        "warmup": batches[0],
        "interpretation_limit": "In-process ASGI experiment with deterministic fake LLM provider; not a production deployment or a real OpenRouter performance guarantee.",
    }


def read_rss_high_water() -> dict[str, Any] | None:
    if resource is None:
        return None
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        unit = "bytes"
        bytes_value = int(raw)
    else:
        unit = "KiB"
        bytes_value = int(raw * 1024)
    return {"raw": raw, "unit": unit, "bytes": bytes_value}


class ImmediateExtractionService:
    def __init__(self, response: ExtractionResponse) -> None:
        self.response = response
        self.calls: list[str] = []

    async def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        self.calls.append(request.request_id)
        return self.response.model_copy(
            update={
                "request_id": request.request_id,
                "meeting_id": request.meeting.id,
                "transcript_revision_id": request.transcript.revision_id,
                "requested_modules": request.extraction.requested_modules,
            }
        )


async def run_large_child_async(target_bytes: int, concurrency: int) -> dict[str, Any]:
    settings = Settings(
        llm_service_token=SecretStr(SERVICE_TOKEN),
        llm_service_max_request_bytes=MAX_REQUEST_BYTES,
        llm_service_request_timeout_seconds=30.0,
        llm_service_notification_timeout_seconds=2.0,
    )
    response_template = ExtractionResponse.model_validate(
        load_json(RESOURCE_RESPONSE_FIXTURE)
    )
    extraction_service = ImmediateExtractionService(response_template)
    notifier = RecordingCompletionNotifier()
    app = create_app(
        settings=settings,
        extraction_service=extraction_service,
        completion_notifier=notifier,
    )
    payloads_and_bodies = []
    for index in range(concurrency):
        request_id = f"vt058-resource-{target_bytes}-{concurrency}-request-{index:02d}"
        meeting_id = f"vt058-resource-{target_bytes}-{concurrency}-meeting-{index:02d}"
        payloads_and_bodies.append(
            sized_valid_request(
                fixture=RESOURCE_REQUEST_FIXTURE,
                request_id=request_id,
                meeting_id=meeting_id,
                target_bytes=target_bytes,
            )
        )
    actual_sizes = [len(body) for _, body in payloads_and_bodies]
    if len(set(actual_sizes)) != 1:
        raise AssertionError("Resource scenario request sizes differ.")

    tracemalloc.start()
    tracemalloc.reset_peak()
    traced_before = tracemalloc.get_traced_memory()[0]
    rss_before = read_rss_high_water()
    async with app.router.lifespan_context(app):
        batch = await send_batch(app, payloads_and_bodies, concurrency=concurrency)
    traced_current, traced_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    rss_after = read_rss_high_water()
    result = summarize_batch(
        f"{target_bytes}-bytes-concurrency-{concurrency}",
        batch,
        expected_mapping={
            payload["request_id"]: payload["meeting"]["id"]
            for payload, _ in payloads_and_bodies
        },
        notifier=notifier,
    )
    return {
        "target_payload_bytes": target_bytes,
        "actual_payload_bytes_each": actual_sizes[0],
        "configured_max_request_bytes": MAX_REQUEST_BYTES,
        "concurrency": concurrency,
        "python": sys.version,
        "platform": platform.platform(),
        "http_status_counts": {
            str(status): sum(record["status"] == status for record in batch["records"])
            for status in sorted(
                {record["status"] for record in batch["records"] if record["status"] is not None}
            )
        },
        "latency_ms_nearest_rank": result["latency_ms_nearest_rank"],
        "throughput_responses_per_second": result["throughput_responses_per_second"],
        "total_run_duration_seconds": result["total_run_duration_seconds"],
        "peak_memory": {
            "process_ru_maxrss_before": rss_before,
            "process_ru_maxrss_after": rss_after,
            "process_ru_maxrss_high_water_delta_bytes": (
                max(0, rss_after["bytes"] - rss_before["bytes"])
                if rss_before is not None and rss_after is not None
                else None
            ),
            "ru_maxrss_note": "Process high-water mark; units normalized using platform convention. Each scenario runs in a fresh subprocess.",
            "tracemalloc_peak_bytes_since_request_start": max(0, traced_peak - traced_before),
            "tracemalloc_current_bytes_after_request": traced_current,
            "tracemalloc_note": "Python allocations only; excludes native allocations and process RSS.",
        },
        "successful_http_responses": result["successful_http_responses"],
        "failed_http_responses": result["failed_http_responses"],
        "http_error_rate": result["http_error_rate"],
        "extraction_calls": len(extraction_service.calls),
        "notification_dispatch_attempts": result["notification_dispatch_attempts"],
        "response_contract_failures": result["extraction_service_results"]["response_contract_failures"],
        "outer_watchdog_timed_out": result["outer_watchdog_timed_out"],
        "isolated_subprocess_pid": os.getpid(),
    }


def run_large_child(target_bytes: int, concurrency: int) -> dict[str, Any]:
    return asyncio.run(run_large_child_async(target_bytes, concurrency))


def run_large_input_matrix() -> dict[str, Any]:
    scenarios = []
    target_sizes = (
        int(MAX_REQUEST_BYTES * 0.25),
        int(MAX_REQUEST_BYTES * 0.75),
        MAX_REQUEST_BYTES - 512,
    )
    child_mode = "--large-input-child"
    for target_bytes in target_sizes:
        for concurrency in (1, 2, 4):
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                child_mode,
                str(target_bytes),
                str(concurrency),
            ]
            child_env = {
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPATH": str(SERVICE_ROOT),
            }
            completed = subprocess.run(
                command,
                cwd=SERVICE_ROOT,
                env=child_env,
                capture_output=True,
                text=True,
                timeout=OUTER_WATCHDOG_SECONDS,
                check=False,
            )
            if completed.returncode != 0:
                scenarios.append(
                    {
                        "target_payload_bytes": target_bytes,
                        "concurrency": concurrency,
                        "subprocess_exit_code": completed.returncode,
                        "stderr": completed.stderr[-2000:],
                        "stdout": completed.stdout[-2000:],
                    }
                )
                continue
            scenarios.append(json.loads(completed.stdout))
    return {
        "experiment": "large-input-latency-and-memory-matrix",
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "configured_max_request_bytes": MAX_REQUEST_BYTES,
            "fresh_subprocess_per_scenario": True,
            "process_memory_method": "resource.getrusage(RUSAGE_SELF).ru_maxrss; process high-water mark with platform-normalized units",
        },
        "target_sizes_bytes": list(target_sizes),
        "concurrency_levels": [1, 2, 4],
        "memory_threshold": None,
        "scenarios": scenarios,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("n17", "large-input"))
    parser.add_argument("--large-input-child", nargs=2, metavar=("TARGET_BYTES", "CONCURRENCY"))
    args = parser.parse_args()
    if (args.mode is None) == (args.large_input_child is None):
        parser.error("Choose --mode n17/large-input or the internal child mode.")
    return args


def main() -> None:
    args = parse_args()
    if args.large_input_child is not None:
        target_bytes, concurrency = (int(value) for value in args.large_input_child)
        print(json.dumps(run_large_child(target_bytes, concurrency), indent=2))
        return
    if args.mode == "n17":
        result = asyncio.run(run_n17())
    else:
        result = run_large_input_matrix()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
