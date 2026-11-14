"""HTTP boundary tests for the standalone LLM Service runtime."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr, ValidationError
from asgi_client import ASGITestClient as TestClient

from app.core.config import Settings
from app.main import create_app
from app.schemas.errors import ErrorEnvelope
from app.schemas.request import ExtractionRequest
from app.schemas.response import ExtractionResponse
from app.api.dependencies import get_extraction_service


SERVICE_ROOT = Path(__file__).parents[2]
FIXTURES = SERVICE_ROOT / "tests" / "fixtures"
TEST_TOKEN = "integration-test-token-do-not-log"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_settings_reject_invalid_limits_and_empty_token() -> None:
    with pytest.raises(ValidationError):
        Settings(
            llm_service_token=SecretStr(" "),
            llm_service_max_request_bytes=0,
        )

    with pytest.raises(ValidationError):
        Settings(
            llm_service_token=SecretStr(TEST_TOKEN),
            llm_service_port=65_536,
        )


def test_settings_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_SERVICE_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("LLM_SERVICE_PORT", "8123")
    monkeypatch.setenv("LLM_SERVICE_MAX_REQUEST_BYTES", "4096")

    settings = Settings(_env_file=None)

    assert settings.llm_service_token.get_secret_value() == TEST_TOKEN
    assert settings.llm_service_port == 8123
    assert settings.llm_service_max_request_bytes == 4096


def make_settings(*, max_request_bytes: int = 16_384) -> Settings:
    return Settings(
        llm_service_token=SecretStr(TEST_TOKEN),
        llm_service_max_request_bytes=max_request_bytes,
    )


def create_test_app(
    *,
    max_request_bytes: int = 16_384,
    extraction_service: Any | None = None,
    completion_notifier: Any | None = None,
):
    return create_app(
        settings=make_settings(max_request_bytes=max_request_bytes),
        extraction_service=extraction_service,
        completion_notifier=completion_notifier,
    )


@pytest.fixture
def full_request() -> dict[str, Any]:
    return load_json(FIXTURES / "requests" / "full_valid_request.json")


@pytest.fixture
def full_response() -> dict[str, Any]:
    return load_json(FIXTURES / "responses" / "full_valid_response.json")


def assert_error(response, *, status: int, code: str) -> ErrorEnvelope:
    assert response.status_code == status
    envelope = ErrorEnvelope.model_validate(response.json())
    assert envelope.statusCode == status
    assert envelope.code == code
    return envelope


def compact_json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class RecordingCompletionNotifier:
    def __init__(self) -> None:
        self.dispatch_attempts: list[dict[str, str]] = []

    async def dispatch(self, event: dict[str, str]) -> None:
        self.dispatch_attempts.append(dict(event))


class NeverCalledExtractionService:
    def __init__(self) -> None:
        self.calls = 0

    async def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        self.calls += 1
        raise AssertionError("extraction must not be reached for this request")

class CountingExtractionService:
    def __init__(self, response: ExtractionResponse) -> None:
        self.response = response
        self.requests: list[str] = []

    async def extract(
        self, request: ExtractionRequest
    ) -> ExtractionResponse:
        self.requests.append(request.request_id)
        return self.response

def run_raw_asgi_request(
    app: Any,
    body: bytes,
    *,
    content_length: int | None,
    chunks: list[bytes] | None = None,
) -> tuple[int, bytes]:
    headers = [
        (b"authorization", f"Bearer {TEST_TOKEN}".encode()),
        (b"content-type", b"application/json"),
    ]
    if content_length is not None:
        headers.append((b"content-length", str(content_length).encode()))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/extractions",
        "raw_path": b"/v1/extractions",
        "query_string": b"",
        "headers": headers,
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "root_path": "",
    }
    request_chunks = chunks if chunks is not None else [body]
    received = 0
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        nonlocal received
        if received == len(request_chunks):
            return {"type": "http.disconnect"}
        chunk = request_chunks[received]
        received += 1
        return {
            "type": "http.request",
            "body": chunk,
            "more_body": received < len(request_chunks),
        }

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    async def invoke() -> None:
        async with app.router.lifespan_context(app):
            await app(scope, receive, send)

    asyncio.run(invoke())
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
    return status, response_body


def test_health_is_public_and_does_not_expose_settings() -> None:
    app = create_test_app()

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "llm-service",
        "contract_version": "1.0",
    }
    assert TEST_TOKEN not in response.text


@pytest.mark.parametrize(
    "authorization",
    [None, "Bearer wrong-token", "Basic integration-test-token-do-not-log", "Bearer "],
)
def test_extraction_rejects_missing_or_invalid_bearer_token(
    authorization: str | None, full_request: dict[str, Any]
) -> None:
    notifier = RecordingCompletionNotifier()
    extraction_service = NeverCalledExtractionService()
    app = create_test_app(
        extraction_service=extraction_service,
        completion_notifier=notifier,
    )
    headers = {} if authorization is None else {"Authorization": authorization}

    with TestClient(app) as client:
        response = client.post("/v1/extractions", json=full_request, headers=headers)

    envelope = assert_error(
        response,
        status=401,
        code="AUTHENTICATION_REQUIRED",
    )
    assert envelope.retryable is False
    assert TEST_TOKEN not in response.text
    assert extraction_service.calls == 0
    assert notifier.dispatch_attempts == []


def test_default_verified_service_fails_closed_without_provider_configuration(
    full_request: dict[str, Any],
) -> None:
    app = create_test_app()
    supported_request = {
        **full_request,
        "extraction": {
            **full_request["extraction"],
            "requested_modules": ["action_items"],
        },
    }

    with TestClient(app) as client:
        response = client.post(
            "/v1/extractions",
            json=supported_request,
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )

    envelope = assert_error(
        response,
        status=503,
        code="PROVIDER_CONFIGURATION_ERROR",
    )
    assert envelope.retryable is False
    assert "transcript" not in response.text.lower()
    assert "stack" not in response.text.lower()


def test_extraction_validates_request_before_calling_service(
    full_request: dict[str, Any],
) -> None:
    invalid_request = {
        **full_request,
        "meeting": {**full_request["meeting"], "timezone": "Mars/Olympus"},
        "private_note": "validation-payload-must-not-leak",
    }
    notifier = RecordingCompletionNotifier()
    extraction_service = NeverCalledExtractionService()
    app = create_test_app(
        extraction_service=extraction_service,
        completion_notifier=notifier,
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/extractions",
            json=invalid_request,
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )

    envelope = assert_error(response, status=400, code="VALIDATION_ERROR")
    assert envelope.request_id == full_request["request_id"]
    assert response.headers["content-type"].startswith("application/json")
    assert "validation-payload-must-not-leak" not in response.text
    assert extraction_service.calls == 0
    assert notifier.dispatch_attempts == []


def test_unsupported_contract_version_maps_to_dedicated_error(
    full_request: dict[str, Any],
) -> None:
    invalid_request = {**full_request, "contract_version": "2.0"}
    app = create_test_app()

    with TestClient(app) as client:
        response = client.post(
            "/v1/extractions",
            json=invalid_request,
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )

    envelope = assert_error(
        response,
        status=400,
        code="UNSUPPORTED_CONTRACT_VERSION",
    )
    assert envelope.request_id == full_request["request_id"]


def test_empty_transcript_maps_to_422(full_request: dict[str, Any]) -> None:
    empty_request = {
        **full_request,
        "transcript": {**full_request["transcript"], "segments": []},
    }
    app = create_test_app()

    with TestClient(app) as client:
        response = client.post(
            "/v1/extractions",
            json=empty_request,
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )

    envelope = assert_error(response, status=422, code="EMPTY_TRANSCRIPT")
    assert envelope.request_id == full_request["request_id"]


def test_malformed_json_uses_contract_error_envelope() -> None:
    app = create_test_app()

    with TestClient(app) as client:
        response = client.post(
            "/v1/extractions",
            content=b"{not-json",
            headers={
                "Authorization": f"Bearer {TEST_TOKEN}",
                "Content-Type": "application/json",
            },
        )

    envelope = assert_error(response, status=400, code="VALIDATION_ERROR")
    assert envelope.request_id is None
    assert "not-json" not in response.text


def test_non_json_content_type_uses_consistent_contract_error() -> None:
    app = create_test_app()

    with TestClient(app) as client:
        response = client.post(
            "/v1/extractions",
            content=b"{}",
            headers={
                "Authorization": f"Bearer {TEST_TOKEN}",
                "Content-Type": "text/plain",
            },
        )

    assert_error(response, status=400, code="VALIDATION_ERROR")


def test_missing_content_type_uses_consistent_contract_error() -> None:
    app = create_test_app()

    with TestClient(app) as client:
        response = client.post(
            "/v1/extractions",
            content=b"{}",
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )

    assert_error(response, status=400, code="VALIDATION_ERROR")


def test_declared_content_length_over_limit_is_rejected(full_request: dict[str, Any]) -> None:
    app = create_test_app(max_request_bytes=128)

    with TestClient(app) as client:
        response = client.post(
            "/v1/extractions",
            json=full_request,
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )

    assert_error(response, status=413, code="PAYLOAD_TOO_LARGE")


@pytest.mark.parametrize("content_length", [None, "1"])
def test_streaming_body_limit_rejects_oversized_body_without_trusting_header(
    content_length: str | None,
) -> None:
    app = create_test_app(max_request_bytes=128)
    body = b'{"padding":"' + (b"x" * 256) + b'"}'
    headers = [
        (b"authorization", f"Bearer {TEST_TOKEN}".encode()),
        (b"content-type", b"application/json"),
    ]
    if content_length is not None:
        headers.append((b"content-length", content_length.encode()))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/extractions",
        "raw_path": b"/v1/extractions",
        "query_string": b"",
        "headers": headers,
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

    asyncio.run(app(scope, receive, send))

    status = next(message["status"] for message in sent if message["type"] == "http.response.start")
    response_body = next(message["body"] for message in sent if message["type"] == "http.response.body")
    envelope = ErrorEnvelope.model_validate_json(response_body)
    assert status == 413
    assert envelope.code == "PAYLOAD_TOO_LARGE"
    assert envelope.request_id is None


def test_n12_declared_content_length_accepts_exact_utf8_limit(
    full_request: dict[str, Any], full_response: dict[str, Any]
) -> None:
    request_model = ExtractionRequest.model_validate(full_request)
    response_model = ExtractionResponse.model_validate(full_response)
    body = compact_json_bytes(full_request)
    limit = len(body)
    assert "Tôi".encode("utf-8") in body

    extraction_service = CountingExtractionService(response_model)
    app = create_test_app(
        max_request_bytes=limit,
        extraction_service=extraction_service,
    )
    status, response_body = run_raw_asgi_request(
        app,
        body,
        content_length=limit,
    )

    assert status == 200
    assert ExtractionResponse.model_validate_json(response_body) == response_model
    assert extraction_service.requests == [request_model.request_id]


def test_n13_streamed_body_accepts_exact_utf8_limit(
    full_request: dict[str, Any], full_response: dict[str, Any]
) -> None:
    request_model = ExtractionRequest.model_validate(full_request)
    response_model = ExtractionResponse.model_validate(full_response)
    body = compact_json_bytes(full_request)
    limit = len(body)
    assert "Tôi".encode("utf-8") in body
    split_at = limit // 2
    assert 0 < split_at < limit

    extraction_service = CountingExtractionService(response_model)
    app = create_test_app(
        max_request_bytes=limit,
        extraction_service=extraction_service,
    )
    status, response_body = run_raw_asgi_request(
        app,
        body,
        content_length=None,
        chunks=[body[:split_at], body[split_at:]],
    )

    assert status == 200
    assert ExtractionResponse.model_validate_json(response_body) == response_model
    assert extraction_service.requests == [request_model.request_id]


@pytest.mark.parametrize("delivery", ["declared", "streamed"], ids=["content-length", "streamed-body"])
def test_n14_valid_json_one_byte_over_limit_is_rejected_without_dispatch(
    full_request: dict[str, Any], delivery: str
) -> None:
    valid_body = compact_json_bytes(full_request)
    limit = len(valid_body)
    oversized_body = valid_body + b" "
    assert len(oversized_body) == limit + 1
    ExtractionRequest.model_validate_json(oversized_body)

    notifier = RecordingCompletionNotifier()
    extraction_service = NeverCalledExtractionService()
    app = create_test_app(
        max_request_bytes=limit,
        extraction_service=extraction_service,
        completion_notifier=notifier,
    )
    if delivery == "declared":
        status, response_body = run_raw_asgi_request(
            app,
            oversized_body,
            content_length=len(oversized_body),
        )
    else:
        split_at = len(oversized_body) // 2
        status, response_body = run_raw_asgi_request(
            app,
            oversized_body,
            content_length=None,
            chunks=[oversized_body[:split_at], oversized_body[split_at:]],
        )

    envelope = ErrorEnvelope.model_validate_json(response_body)
    assert status == 413
    assert envelope.statusCode == 413
    assert envelope.code == "PAYLOAD_TOO_LARGE"
    assert envelope.request_id is None
    assert extraction_service.calls == 0
    assert notifier.dispatch_attempts == []


def test_dependency_override_returns_typed_extraction_response(
    full_request: dict[str, Any], full_response: dict[str, Any]
) -> None:
    request_model = ExtractionRequest.model_validate(full_request)
    response_model = ExtractionResponse.model_validate(full_response)

    class FakeExtractionService:
        def __init__(self) -> None:
            self.calls = 0

        async def extract(self, request: ExtractionRequest) -> ExtractionResponse:
            self.calls += 1
            assert request.request_id == request_model.request_id
            return response_model

    class RecordingNotifier:
        def __init__(self) -> None:
            self.dispatch_attempts: list[dict[str, str]] = []

        async def dispatch(self, event: dict[str, str]) -> None:
            self.dispatch_attempts.append(dict(event))

    app = create_test_app()
    fake_service = FakeExtractionService()
    recording_notifier = RecordingNotifier()
    # Phase 05's injectable dependency will read this app-scoped test seam.
    app.state.completion_notifier = recording_notifier

    async def provide_fake_service() -> FakeExtractionService:
        return fake_service

    app.dependency_overrides[get_extraction_service] = provide_fake_service

    with TestClient(app) as client:
        response = client.post(
            "/v1/extractions",
            json=full_request,
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )

    assert response.status_code == 200
    assert ExtractionResponse.model_validate(response.json()) == response_model
    assert fake_service.calls == 1
    assert recording_notifier.dispatch_attempts == [
        {
            "event_type": "extraction.completed",
            "request_id": request_model.request_id,
            "meeting_id": request_model.meeting.id,
            "status": "completed",
        }
    ]


def test_unexpected_service_error_is_safe_and_standardized(
    full_request: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    class BrokenExtractionService:
        async def extract(self, request: ExtractionRequest) -> ExtractionResponse:
            raise RuntimeError(f"private failure with secret {TEST_TOKEN}")

    app = create_test_app()
    async def provide_broken_service() -> BrokenExtractionService:
        return BrokenExtractionService()

    app.dependency_overrides[get_extraction_service] = provide_broken_service

    with TestClient(app) as client:
        response = client.post(
            "/v1/extractions",
            json=full_request,
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )

    assert_error(response, status=500, code="INTERNAL_ERROR")
    assert TEST_TOKEN not in response.text
    assert "private failure" not in response.text
    assert "Traceback" not in response.text
    assert TEST_TOKEN not in caplog.text
    assert "private failure" not in caplog.text


def test_request_timeout_maps_to_retryable_contract_error(
    full_request: dict[str, Any],
) -> None:
    class SlowExtractionService:
        async def extract(self, request: ExtractionRequest) -> ExtractionResponse:
            await asyncio.sleep(0.02)
            raise AssertionError("timeout should cancel the extraction service")

    settings = Settings(
        llm_service_token=SecretStr(TEST_TOKEN),
        llm_service_request_timeout_seconds=0.001,
    )
    app = create_app(settings=settings)
    async def provide_slow_service() -> SlowExtractionService:
        return SlowExtractionService()

    app.dependency_overrides[get_extraction_service] = provide_slow_service

    with TestClient(app) as client:
        response = client.post(
            "/v1/extractions",
            json=full_request,
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )

    envelope = assert_error(response, status=504, code="REQUEST_TIMEOUT")
    assert envelope.retryable is True


def test_openapi_exposes_contract_models_security_and_error_responses() -> None:
    app = create_test_app()

    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    document = response.json()
    assert "/health" in document["paths"]
    assert "/v1/extractions" in document["paths"]
    operation = document["paths"]["/v1/extractions"]["post"]
    assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ExtractionRequest"
    )
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ExtractionResponse"
    )
    for status in ("400", "401", "413", "422", "500", "503"):
        assert status in operation["responses"]
        assert "ErrorEnvelope" in json.dumps(operation["responses"][status])
    schemas = document["components"]["schemas"]
    assert {"ExtractionRequest", "ExtractionResponse", "ErrorEnvelope"} <= set(schemas)
    assert "HTTPBearer" in document["components"]["securitySchemes"]
    assert operation["security"]
    assert not document["paths"]["/health"]["get"].get("security")
    assert TEST_TOKEN not in json.dumps(document)


def test_application_lifecycle_runs_with_injected_settings() -> None:
    app = create_test_app()

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200

    assert app.state.settings.llm_service_token.get_secret_value() == TEST_TOKEN


def test_unconfigured_service_token_fails_startup_without_secret_details() -> None:
    app = create_app(settings=Settings(llm_service_token=None))

    with pytest.raises(RuntimeError, match="LLM_SERVICE_TOKEN"):
        with TestClient(app):
            pass
