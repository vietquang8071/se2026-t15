"""Failure-isolation tests for extraction completion notification dispatch."""

from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path
from typing import Any

import pytest
from fastapi import BackgroundTasks
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.main import create_app
from app.schemas.request import ExtractionRequest
from app.schemas.response import ExtractionResponse


SERVICE_ROOT = Path(__file__).parents[2]
FIXTURES = SERVICE_ROOT / "tests" / "fixtures"
TEST_TOKEN = "notification-integration-token-canary"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def make_app(
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
    notifier: Any,
    *,
    token: str = TEST_TOKEN,
    settings: Settings | None = None,
):
    request_model = ExtractionRequest.model_validate(request_payload)
    response_model = ExtractionResponse.model_validate(response_payload)

    class FixedExtractionService:
        def __init__(self) -> None:
            self.calls = 0

        async def extract(self, request: ExtractionRequest) -> ExtractionResponse:
            self.calls += 1
            assert request.request_id == request_model.request_id
            return response_model

    service = FixedExtractionService()
    app = create_app(
        settings=settings or Settings(llm_service_token=SecretStr(token)),
        extraction_service=service,
        completion_notifier=notifier,
    )
    return app, service, request_model


def send_asgi_request(
    app,
    request_payload: dict[str, Any],
    *,
    token: str = TEST_TOKEN,
    watchdog_seconds: float = 2.0,
) -> tuple[int, bytes, bool]:
    body = json.dumps(request_payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/extractions",
        "raw_path": b"/v1/extractions",
        "query_string": b"",
        "headers": [
            (b"authorization", f"Bearer {token}".encode()),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "root_path": "",
    }
    received = False
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    async def invoke() -> bool:
        try:
            await asyncio.wait_for(
                app(scope, receive, send),
                timeout=watchdog_seconds,
            )
        except TimeoutError:
            return False
        return True

    completed = asyncio.run(invoke())
    status = next(
        message["status"]
        for message in sent
        if message["type"] == "http.response.start"
    )
    response_body = b"".join(
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body"
    )
    return status, response_body, completed


class RecordingNotifier:
    def __init__(self) -> None:
        self.dispatch_attempts: list[dict[str, str]] = []
        self.completed = False

    async def dispatch(self, event: dict[str, str]) -> None:
        self.dispatch_attempts.append(dict(event))
        self.completed = True


class ShortNotificationTimeoutSettings(Settings):
    llm_service_notification_timeout_seconds: float = 0.03


def test_notifier_exception_preserves_response_and_safe_diagnostics(
    caplog: pytest.LogCaptureFixture,
) -> None:
    request_payload = load_json(FIXTURES / "requests" / "full_valid_request.json")
    response_payload = load_json(FIXTURES / "responses" / "full_valid_response.json")
    transcript_canary = "TRANSCRIPT-PRIVACY-CANARY-58"
    token_canary = "BEARER-PRIVACY-CANARY-58"
    provider_canary = "PROVIDER-RESPONSE-PRIVACY-CANARY-58"
    exception_canary = "EXCEPTION-DETAIL-PRIVACY-CANARY-58"
    request_payload["transcript"]["segments"][0]["text"] = transcript_canary

    class RaisingNotifier(RecordingNotifier):
        async def dispatch(self, event: dict[str, str]) -> None:
            self.dispatch_attempts.append(dict(event))
            raise RuntimeError(
                f"{transcript_canary} {token_canary} {provider_canary} {exception_canary}"
            )

    control_notifier = RecordingNotifier()
    failing_notifier = RaisingNotifier()
    control_app, control_service, request_model = make_app(
        request_payload,
        response_payload,
        control_notifier,
        token=token_canary,
    )
    failing_app, failing_service, _ = make_app(
        request_payload,
        response_payload,
        failing_notifier,
        token=token_canary,
    )

    with caplog.at_level("WARNING"):
        control_status, control_body, control_completed = send_asgi_request(
            control_app,
            request_payload,
            token=token_canary,
        )
        failing_status, failing_body, failing_completed = send_asgi_request(
            failing_app,
            request_payload,
            token=token_canary,
        )

    expected_event = {
        "event_type": "extraction.completed",
        "request_id": request_model.request_id,
        "meeting_id": request_model.meeting.id,
        "status": "completed",
    }
    assert control_status == failing_status == 200
    assert control_body == failing_body
    assert control_completed is True
    assert failing_completed is True
    assert control_service.calls == failing_service.calls == 1
    assert control_notifier.dispatch_attempts == [expected_event]
    assert failing_notifier.dispatch_attempts == [expected_event]
    assert control_notifier.completed is True
    assert failing_notifier.completed is False
    assert any(
        record.getMessage() == "Completion notification dispatch failed."
        for record in caplog.records
    )
    assert all(
        canary not in caplog.text
        for canary in (
            transcript_canary,
            token_canary,
            provider_canary,
            exception_canary,
        )
    )


def test_notification_timeout_setting_defaults_to_one_second() -> None:
    assert (
        getattr(Settings(), "llm_service_notification_timeout_seconds", None)
        == 1.0
    )


@pytest.mark.parametrize(
    "timeout_seconds",
    [0.0, -0.1, math.nan, math.inf, -math.inf],
)
def test_notification_timeout_setting_rejects_invalid_values(
    timeout_seconds: float,
) -> None:
    with pytest.raises(ValidationError):
        Settings(llm_service_notification_timeout_seconds=timeout_seconds)


def test_notifier_timeout_is_bounded_and_cancels_dispatch(
    caplog: pytest.LogCaptureFixture,
) -> None:
    request_payload = load_json(FIXTURES / "requests" / "full_valid_request.json")
    response_payload = load_json(FIXTURES / "responses" / "full_valid_response.json")

    class WaitingNotifier(RecordingNotifier):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()
            self.cancellation_observed = asyncio.Event()

        async def dispatch(self, event: dict[str, str]) -> None:
            self.dispatch_attempts.append(dict(event))
            self.started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancellation_observed.set()
                raise
            self.completed = True

    settings = ShortNotificationTimeoutSettings(
        llm_service_token=SecretStr(TEST_TOKEN),
        llm_service_request_timeout_seconds=5.0,
        llm_service_notification_timeout_seconds=0.03,
    )
    control_notifier = RecordingNotifier()
    waiting_notifier = WaitingNotifier()
    control_app, _, request_model = make_app(
        request_payload,
        response_payload,
        control_notifier,
        settings=settings,
    )
    waiting_app, _, _ = make_app(
        request_payload,
        response_payload,
        waiting_notifier,
        settings=settings,
    )

    with caplog.at_level("WARNING"):
        control_status, control_body, control_completed = send_asgi_request(
            control_app,
            request_payload,
            watchdog_seconds=1.0,
        )
        timeout_status, timeout_body, timeout_completed = send_asgi_request(
            waiting_app,
            request_payload,
            watchdog_seconds=1.0,
        )

    expected_event = {
        "event_type": "extraction.completed",
        "request_id": request_model.request_id,
        "meeting_id": request_model.meeting.id,
        "status": "completed",
    }
    assert control_status == timeout_status == 200
    assert control_body == timeout_body
    assert control_completed is True
    assert waiting_notifier.started.is_set()
    assert waiting_notifier.dispatch_attempts == [expected_event]
    assert waiting_notifier.completed is False
    assert waiting_notifier.cancellation_observed.is_set()
    assert timeout_completed is True, "notification work exceeded the outer safety watchdog"
    assert any(
        record.getMessage() == "Completion notification timed out."
        for record in caplog.records
    )
    assert settings.llm_service_request_timeout_seconds == 5.0


def test_task_scheduling_failure_preserves_response_and_safe_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    request_payload = load_json(FIXTURES / "requests" / "full_valid_request.json")
    response_payload = load_json(FIXTURES / "responses" / "full_valid_response.json")
    control_notifier = RecordingNotifier()
    control_app, control_service, control_request_model = make_app(
        request_payload,
        response_payload,
        control_notifier,
    )

    with caplog.at_level("WARNING"):
        control_status, control_body, control_completed = send_asgi_request(
            control_app,
            request_payload,
        )

    scheduler_canary = "SCHEDULER-EXCEPTION-PRIVACY-CANARY-58"
    registration_attempts = 0

    def fail_add_task(
        background_tasks: BackgroundTasks,
        function: Any,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        nonlocal registration_attempts
        registration_attempts += 1
        raise RuntimeError(scheduler_canary)

    monkeypatch.setattr(BackgroundTasks, "add_task", fail_add_task)
    failing_notifier = RecordingNotifier()
    failing_app, failing_service, _ = make_app(
        request_payload,
        response_payload,
        failing_notifier,
    )

    with caplog.at_level("WARNING"):
        failing_status, failing_body, failing_completed = send_asgi_request(
            failing_app,
            request_payload,
        )

    assert control_status == 200
    assert failing_status == control_status
    assert failing_body == control_body
    assert control_completed is True
    assert failing_completed is True
    assert control_service.calls == failing_service.calls == 1
    assert control_notifier.dispatch_attempts == [
        {
            "event_type": "extraction.completed",
            "request_id": control_request_model.request_id,
            "meeting_id": control_request_model.meeting.id,
            "status": "completed",
        }
    ]
    assert registration_attempts == 1
    assert failing_notifier.dispatch_attempts == []
    assert any(
        record.getMessage() == "Completion notification scheduling failed."
        for record in caplog.records
    )
    assert scheduler_canary not in caplog.text
