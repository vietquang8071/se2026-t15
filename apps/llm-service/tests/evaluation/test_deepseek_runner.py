from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

import httpx
import pytest

from evaluation.deepseek_runner import MODEL_ID, run_cli
from evaluation.loader import DATASET_DIR, load_dataset
from evaluation.runner import run_cli as run_offline_cli
from evaluation.scoring import reviewable_claim_ids


SERVICE_TOKEN = "manual-runner-service-token-do-not-log"
OPENROUTER_KEY = "manual-runner-openrouter-key-do-not-log"


@pytest.fixture
def configured_env(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "LLM_SERVICE_TOKEN": SERVICE_TOKEN,
        "OPENROUTER_API_KEY": OPENROUTER_KEY,
        "OPENROUTER_MODEL": MODEL_ID,
        "OPENROUTER_STRUCTURED_OUTPUT_MODE": "json_object",
        "OPENROUTER_MAX_OUTPUT_TOKENS": "8192",
        "OPENROUTER_REQUIRE_PARAMETERS": "true",
        "LLM_SERVICE_HOST": "127.0.0.1",
        "LLM_SERVICE_PORT": "8000",
        "LLM_SERVICE_REQUEST_TIMEOUT_SECONDS": "180",
        "LLM_SERVICE_PROVIDER_TIMEOUT_SECONDS": "60",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def _smoke_args(output_dir: Path, *extra: str) -> list[str]:
    return [
        "smoke",
        "--authorize-smoke",
        "--max-cases",
        "1",
        "--spend-limit-usd",
        "0.25",
        "--confirm-account-spending-limit",
        "--output-dir",
        str(output_dir),
        *extra,
    ]


def _development_args(output_dir: Path, *extra: str) -> list[str]:
    return [
        "development",
        "--authorize-development",
        "--max-cases",
        "10",
        "--spend-limit-usd",
        "0.25",
        "--confirm-account-spending-limit",
        "--output-dir",
        str(output_dir),
        *extra,
    ]


def _valid_response(case_id: str = "case-001") -> dict[str, Any]:
    case = load_dataset(DATASET_DIR).case(case_id)
    assert case is not None
    request = case.request
    summary_source = request.transcript.segments[0]
    action_source = next(
        (segment for segment in request.transcript.segments if segment.id == "SEG-0002"),
        summary_source,
    )
    start_ms = round(action_source.start * 1000)
    total_seconds, milliseconds = divmod(start_ms, 1000)
    minutes, seconds = divmod(total_seconds, 60)
    timestamp = f"00:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
    return {
        "contract_version": "1.0",
        "request_id": request.request_id,
        "status": "completed",
        "meeting_id": request.meeting.id,
        "transcript_revision_id": request.transcript.revision_id,
        "requested_modules": request.extraction.requested_modules,
        "modules": {
            "meeting_summary": {
                "title": request.meeting.title,
                "date": str(request.meeting.anchor_date),
                "duration_minutes": round(request.meeting.duration_seconds / 60, 2),
                "participants": [p.display_name for p in request.meeting.participants],
                "overview": (
                    "Nhóm tập trung vào API đặt lịch cho bản thử nghiệm. Minh cam kết "
                    "hoàn thiện API trước thứ Sáu này; người kiểm thử chưa được chốt."
                    if case_id == "case-001"
                    else "Nhóm khởi động API đặt lịch và thống nhất bước triển khai."
                ),
                "key_topics": (
                    [
                        {
                            "topic": "API đặt lịch",
                            "brief_discussion": "Minh nhận hoàn thiện API đặt lịch trước thứ Sáu này.",
                            "source_segment_ids": ["SEG-0001", "SEG-0002"],
                            "needs_review": False,
                            "review_reasons": [],
                        },
                        {
                            "topic": "Kiểm thử",
                            "brief_discussion": "Nhóm chưa chốt người kiểm thử.",
                            "source_segment_ids": ["SEG-0003"],
                            "needs_review": False,
                            "review_reasons": [],
                        },
                    ]
                    if case_id == "case-001"
                    else []
                ),
                "source_segment_ids": (
                    ["SEG-0001", "SEG-0002", "SEG-0003"]
                    if case_id == "case-001"
                    else [summary_source.id]
                ),
                "needs_review": False,
                "review_reasons": [],
            },
            "action_items": [
                {
                    "id": "ACT-001",
                    "task": "Hoàn thiện API đặt lịch",
                    "owner": "Minh",
                    "due_date": None,
                    "raw_due_expression": "trước thứ Sáu này" if case_id == "case-001" else None,
                    "due_date_resolution": (
                        {
                            "status": "unresolved",
                            "resolved_date": None,
                            "start_date": None,
                            "end_date": None,
                            "needs_review": True,
                            "source_segment_ids": [action_source.id],
                        }
                        if case_id == "case-001"
                        else None
                    ),
                    "priority": None,
                    "source_timestamp": timestamp,
                    "context": None,
                    "source_segment_ids": [action_source.id],
                    "needs_review": case_id == "case-001",
                    "review_reasons": ["temporal_unresolved"] if case_id == "case-001" else [],
                }
            ],
            "decision_log": None,
            "open_issues": None,
            "follow_up_items": None,
            "timeline_events": None,
        },
        "processing": {
            "provider": "openrouter",
            "model_id": MODEL_ID,
            "prompt_version": "extract-v1.0",
            "evidence_prompt_version": "evidence-v1.0",
            "started_at": "2026-11-18T09:00:00Z",
            "completed_at": "2026-11-18T09:00:05Z",
            "token_usage": {"input_tokens": 100, "output_tokens": 40},
        },
    }


def _success_transport(body: dict[str, Any], calls: list[dict[str, Any]]) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(
            {
                "url": str(request.url),
                "method": request.method,
                "authorization": request.headers.get("Authorization"),
                "payload": json.loads(request.content),
            }
        )
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handle)


def _smoke_review(
    output_dir: Path,
    *,
    response: dict[str, Any] | None = None,
    reviewed_claims: list[dict[str, str]] | None = None,
    decision: str = "approved",
    summary_review: dict[str, Any] | None = None,
    action_matches: list[dict[str, str]] | None = None,
) -> None:
    response_path = output_dir / "responses" / "case-001.json"
    if response is None:
        response = json.loads(response_path.read_text(encoding="utf-8"))
    claim_ids = reviewable_claim_ids(response)
    claims = reviewed_claims or [
        {"claim_id": claim_id, "verdict": "supported"} for claim_id in claim_ids
    ]
    case_review = {
        "action_matches": action_matches or [],
        "summary_review": summary_review
        or {
            "faithfulness": 5,
            "required_fact_coverage": 1,
            "conciseness_actionability": 4,
            "semantic_source_grounding": 1,
            "hallucination_count": 0,
            "hallucinations": [],
            "reviewer": "reviewer-a",
        },
        "semantic_grounding": {"reviewer": "reviewer-a", "claims": claims},
    }
    review_path = output_dir / "reviews" / "review-template-smoke.json"
    review_path.write_text(
        json.dumps({"cases": {"case-001": case_review}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    approval = {
        "schema_version": "llm03.7.2-smoke-approval-v1",
        "case_id": "case-001",
        "response_sha256": hashlib.sha256(response_path.read_bytes()).hexdigest(),
        "review_file": "review-template-smoke.json",
        "review_sha256": hashlib.sha256(review_path.read_bytes()).hexdigest(),
        "decision": decision,
        "reviewer": "reviewer-a",
        "rationale": "Đã đối chiếu các facts, Action Item và bằng chứng với transcript.",
    }
    (output_dir / "reviews" / "smoke-approval.json").write_text(
        json.dumps(approval, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _successful_smoke(output_dir: Path, *, response: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    assert run_cli(
        _smoke_args(output_dir),
        transport=_success_transport(response or _valid_response(), calls),
    ) == 0
    return calls


def test_default_invocation_is_preflight_without_network(
    configured_env: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden_client(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("default preflight must not create an HTTP client")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden_client)

    assert run_cli([]) == 0
    assert "no network request" in capsys.readouterr().out.lower()


def test_smoke_authorization_does_not_authorize_development(
    configured_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = [
        "development",
        "--max-cases",
        "10",
        "--spend-limit-usd",
        "0.25",
        "--confirm-account-spending-limit",
        "--output-dir",
        str(tmp_path),
    ]

    assert run_cli(args) == 3
    assert "development" in capsys.readouterr().err.lower()


def test_smoke_authorization_flag_is_not_accepted_by_development_parser(
    configured_env: None, tmp_path: Path
) -> None:
    args = _development_args(
        tmp_path,
        "--authorize-smoke",
        "--max-cases",
        "1",
        "--case",
        "case-001",
    )

    with pytest.raises(SystemExit) as error:
        run_cli(args)
    assert error.value.code == 2


def test_smoke_rejects_a_case_limit_above_one(
    configured_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _smoke_args(tmp_path, "--max-cases", "2")

    assert run_cli(args) == 3
    assert "case-001" in capsys.readouterr().err


def test_smoke_requires_its_own_explicit_acknowledgment(
    configured_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _smoke_args(tmp_path)
    args.remove("--authorize-smoke")
    calls: list[dict[str, Any]] = []

    assert run_cli(
        args, transport=httpx.MockTransport(lambda request: calls.append({}) or httpx.Response(200))
    ) == 3
    assert calls == []
    assert "authorize-smoke" in capsys.readouterr().err


def test_missing_credentials_fail_preflight_without_leaking_values(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("LLM_SERVICE_TOKEN", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_MODEL", MODEL_ID)

    assert run_cli(["preflight"]) == 2
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "LLM_SERVICE_TOKEN" in output
    assert "OPENROUTER_API_KEY" in output
    assert SERVICE_TOKEN not in output
    assert OPENROUTER_KEY not in output


def test_invalid_model_configuration_fails_before_http(
    configured_env: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OPENROUTER_MODEL", "deepseek/another-model")

    assert run_cli(_smoke_args(tmp_path)) == 2
    assert "OPENROUTER_MODEL" in capsys.readouterr().err


def test_holdout_case_is_rejected_before_http(
    configured_env: None,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[dict[str, Any]] = []
    args = _development_args(tmp_path, "--case", "case-011")

    assert run_cli(args, transport=httpx.MockTransport(lambda request: calls.append({}) or httpx.Response(200))) == 2
    assert calls == []
    assert "case-011" in capsys.readouterr().err


def test_invalid_dataset_is_rejected_before_http(
    configured_env: None,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import shutil

    copied_dataset = tmp_path / "dataset"
    shutil.copytree(DATASET_DIR, copied_dataset)
    (copied_dataset / "cases" / "case-001" / "gold.json").unlink()
    calls: list[dict[str, Any]] = []

    assert run_cli(
        _smoke_args(tmp_path / "invalid-dataset", "--dataset-dir", str(copied_dataset)),
        transport=httpx.MockTransport(lambda request: calls.append({}) or httpx.Response(200)),
    ) == 2
    assert calls == []
    assert "case-001" in capsys.readouterr().err


def test_live_output_cannot_be_written_inside_dataset(
    configured_env: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[dict[str, Any]] = []
    output = DATASET_DIR / "reports"

    assert run_cli(
        _smoke_args(output),
        transport=httpx.MockTransport(lambda request: calls.append({}) or httpx.Response(200)),
    ) == 2
    assert calls == []
    assert "dataset" in capsys.readouterr().err.lower()


def test_non_loopback_service_url_is_rejected_before_http(
    configured_env: None,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[dict[str, Any]] = []

    assert run_cli(
        _smoke_args(tmp_path / "remote", "--service-url", "https://example.com"),
        transport=httpx.MockTransport(lambda request: calls.append({}) or httpx.Response(200)),
    ) == 2
    assert calls == []
    assert "loopback" in capsys.readouterr().err.lower()


def test_valid_contract_response_is_saved_and_provider_payload_is_unchanged(
    configured_env: None, tmp_path: Path
) -> None:
    calls: list[dict[str, Any]] = []
    output_dir = tmp_path / "llm0372"
    transport = _success_transport(_valid_response(), calls)

    assert run_cli(_smoke_args(output_dir), transport=transport) == 0

    saved = json.loads((output_dir / "responses" / "case-001.json").read_text())
    assert saved["request_id"] == "eval-llm037-case-001"
    assert calls[0]["method"] == "POST"
    assert calls[0]["url"] == "http://127.0.0.1:8000/v1/extractions"
    assert calls[0]["authorization"] == f"Bearer {SERVICE_TOKEN}"
    assert calls[0]["payload"]["request_id"] == saved["request_id"]
    source_request = json.loads(
        (DATASET_DIR / "cases" / "case-001" / "llm-request.json").read_text()
    )
    assert calls[0]["payload"] == source_request
    assert "gold" not in calls[0]["payload"]
    assert (output_dir / "metadata" / "smoke.json").is_file()
    assert (output_dir / "reports" / "smoke" / "report.json").is_file()
    assert (output_dir / "reviews" / "review-template-smoke.json").is_file()


def test_invalid_contract_response_is_saved_as_failure_not_success(
    configured_env: None, tmp_path: Path
) -> None:
    calls: list[dict[str, Any]] = []
    invalid = _valid_response()
    invalid["request_id"] = "different-request"

    assert run_cli(
        _smoke_args(tmp_path / "bad-response"),
        transport=_success_transport(invalid, calls),
    ) == 1

    root = tmp_path / "bad-response"
    assert not (root / "responses" / "case-001.json").exists()
    failure = json.loads((root / "failures" / "case-001.json").read_text())
    assert failure["failure_category"] == "response_contract_invalid"
    assert failure["attempt_count"] == 1


@pytest.mark.parametrize(
    ("status", "category"),
    [
        (401, "service_authentication"),
        (403, "service_forbidden"),
        (429, "service_rate_limit"),
        (503, "service_error"),
    ],
)
def test_http_failures_are_sanitized_and_never_retried(
    configured_env: None,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    status: int,
    category: str,
) -> None:
    calls: list[httpx.Request] = []
    poison = f"server echoed {OPENROUTER_KEY} and {SERVICE_TOKEN}"

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, json={"message": poison, "code": "SAFE_CODE"})

    assert run_cli(
        _smoke_args(tmp_path / str(status)), transport=httpx.MockTransport(handle)
    ) == 1
    output = capsys.readouterr().out + capsys.readouterr().err
    assert len(calls) == 1
    assert OPENROUTER_KEY not in output
    assert SERVICE_TOKEN not in output
    failure = json.loads((tmp_path / str(status) / "failures" / "case-001.json").read_text())
    assert failure["failure_category"] == category
    assert poison not in json.dumps(failure)


def test_timeout_is_recorded_once_without_retry(
    configured_env: None, tmp_path: Path
) -> None:
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ReadTimeout("sensitive timeout detail", request=request)

    assert run_cli(
        _smoke_args(tmp_path / "timeout"), transport=httpx.MockTransport(handle)
    ) == 1
    assert len(calls) == 1
    failure = json.loads((tmp_path / "timeout" / "failures" / "case-001.json").read_text())
    assert failure["failure_category"] == "timeout"
    assert "sensitive timeout detail" not in json.dumps(failure)


def test_development_case_limit_is_respected(
    configured_env: None, tmp_path: Path
) -> None:
    calls: list[dict[str, Any]] = []
    output = tmp_path / "one-case"
    assert run_cli(
        _smoke_args(output),
        transport=_success_transport(_valid_response(), calls),
    ) == 0
    _smoke_review(output)
    args = _development_args(output, "--max-cases", "1", "--case", "case-002")
    body = _valid_response("case-002")

    assert run_cli(args, transport=_success_transport(body, calls)) == 0
    assert len(calls) == 2
    assert (output / "responses" / "case-002.json").exists()
    assert not (output / "responses" / "case-011.json").exists()


def test_development_default_is_exactly_ten_sequential_cases(
    configured_env: None, tmp_path: Path
) -> None:
    cases = load_dataset(DATASET_DIR).cases
    request_to_case = {case.request.request_id: case.case_id for case in cases}
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        case_id = request_to_case[body["request_id"]]
        calls.append(case_id)
        return httpx.Response(200, json=_valid_response(case_id))

    output = tmp_path / "all-development"
    assert run_cli(
        _smoke_args(output), transport=httpx.MockTransport(handle)
    ) == 0
    _smoke_review(output)
    assert run_cli(
        _development_args(output), transport=httpx.MockTransport(handle)
    ) == 0
    expected = [f"case-{number:03d}" for number in range(1, 11)]
    assert calls == expected
    assert sorted(path.stem for path in (output / "responses").glob("*.json")) == expected
    report = json.loads((output / "reports" / "development" / "report.json").read_text())
    assert report["dataset"]["split"] == "development"
    assert report["metrics"]["semantic_grounding_review"]["status"] == "pending_review"
    assert report["metrics"]["summary_review"]["status"] == "pending_review"


def test_positive_spend_amount_without_account_cap_confirmation_is_rejected(
    configured_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[dict[str, Any]] = []
    args = [
        "smoke",
        "--authorize-smoke",
        "--max-cases",
        "1",
        "--spend-limit-usd",
        "0.25",
        "--output-dir",
        str(tmp_path),
    ]

    assert run_cli(args, transport=httpx.MockTransport(lambda request: calls.append({}) or httpx.Response(200))) == 3
    assert calls == []
    assert "account-level" in capsys.readouterr().err.lower()


def test_non_positive_spend_authorization_is_rejected_before_http(
    configured_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _smoke_args(tmp_path)
    amount_index = args.index("--spend-limit-usd") + 1
    args[amount_index] = "0"
    calls: list[dict[str, Any]] = []

    assert run_cli(
        args, transport=httpx.MockTransport(lambda request: calls.append({}) or httpx.Response(200))
    ) == 3
    assert calls == []
    assert "positive" in capsys.readouterr().err.lower()


def test_unknown_cost_is_not_reported_as_hard_budget_enforcement(
    configured_env: None, tmp_path: Path
) -> None:
    calls: list[dict[str, Any]] = []

    assert run_cli(
        _smoke_args(tmp_path / "budget"),
        transport=_success_transport(_valid_response(), calls),
    ) == 0
    metadata = json.loads((tmp_path / "budget" / "metadata" / "smoke.json").read_text())
    assert metadata["budget"]["authorized_limit_usd"] == 0.25
    assert metadata["budget"]["account_level_limit_confirmed_by_operator"] is True
    assert metadata["budget"]["hard_cap_enforced_by_runner"] is False
    assert metadata["budget"]["estimated_cost_usd"] is None
    assert metadata["budget"]["actual_billed_cost_usd"] is None


def test_runner_uses_a_finite_timeout_for_the_internal_request(
    configured_env: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from evaluation import deepseek_runner

    actual_client = httpx.AsyncClient
    captured: dict[str, Any] = {}

    def recording_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        captured["timeout"] = kwargs.get("timeout")
        captured["trust_env"] = kwargs.get("trust_env")
        return actual_client(*args, **kwargs)

    monkeypatch.setattr(deepseek_runner.httpx, "AsyncClient", recording_client)
    calls: list[dict[str, Any]] = []

    assert run_cli(
        _smoke_args(tmp_path / "bounded-timeout"),
        transport=_success_transport(_valid_response(), calls),
    ) == 0
    timeout = captured["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect == 180.0
    assert timeout.read == 180.0
    assert captured["trust_env"] is False


def test_unexpected_returned_model_is_not_saved_as_success(
    configured_env: None, tmp_path: Path
) -> None:
    calls: list[dict[str, Any]] = []
    wrong_model = _valid_response()
    wrong_model["processing"]["model_id"] = "deepseek/another-model"

    assert run_cli(
        _smoke_args(tmp_path / "wrong-model"),
        transport=_success_transport(wrong_model, calls),
    ) == 1
    root = tmp_path / "wrong-model"
    assert not (root / "responses" / "case-001.json").exists()
    failure = json.loads((root / "failures" / "case-001.json").read_text())
    assert failure["failure_category"] == "unexpected_model"


def test_existing_response_is_never_overwritten(
    configured_env: None, tmp_path: Path
) -> None:
    output_dir = tmp_path / "existing"
    response_path = output_dir / "responses" / "case-001.json"
    response_path.parent.mkdir(parents=True)
    original = b"preserve existing response\n"
    response_path.write_bytes(original)
    calls: list[dict[str, Any]] = []

    assert run_cli(
        _smoke_args(output_dir),
        transport=httpx.MockTransport(lambda request: calls.append({}) or httpx.Response(200)),
    ) == 2
    assert response_path.read_bytes() == original
    assert calls == []


def test_development_reuses_matching_smoke_response_without_second_request(
    configured_env: None, tmp_path: Path
) -> None:
    output_dir = tmp_path / "reuse"
    smoke_calls: list[dict[str, Any]] = []
    assert run_cli(
        _smoke_args(output_dir),
        transport=_success_transport(_valid_response(), smoke_calls),
    ) == 0
    _smoke_review(output_dir)
    original_response = (output_dir / "responses" / "case-001.json").read_bytes()
    original_case_metadata = (output_dir / "metadata" / "case-001.json").read_bytes()

    def forbidden_request(request: httpx.Request) -> httpx.Response:
        raise AssertionError("matching smoke response should be reused")

    assert run_cli(
        _development_args(output_dir, "--max-cases", "1", "--case", "case-001"),
        transport=httpx.MockTransport(forbidden_request),
    ) == 0
    assert (output_dir / "responses" / "case-001.json").read_bytes() == original_response
    assert (output_dir / "metadata" / "case-001.json").read_bytes() == original_case_metadata
    development = json.loads((output_dir / "metadata" / "development.json").read_text())
    assert development["reused_case_ids"] == ["case-001"]


def test_development_run_requires_a_successful_smoke_record(
    configured_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[dict[str, Any]] = []

    assert run_cli(
        _development_args(tmp_path / "without-smoke", "--case", "case-002"),
        transport=httpx.MockTransport(lambda request: calls.append({}) or httpx.Response(200)),
    ) == 2
    assert calls == []
    assert "smoke" in capsys.readouterr().err.lower()


def test_offline_evaluator_remains_fail_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_offline_cli(
        [
            "run",
            "--mode",
            "live",
            "--ack-live",
            "--max-cases",
            "1",
            "--spend-limit-usd",
            "0.25",
            "--output-dir",
            str(tmp_path),
        ]
    ) == 3
    assert "disabled" in capsys.readouterr().err.lower()


def _development_metadata(output_dir: Path) -> dict[str, Any]:
    return json.loads((output_dir / "metadata" / "development.json").read_text())


def _run_development_cases(
    output_dir: Path,
    case_ids: list[str],
    transport: httpx.AsyncBaseTransport,
) -> int:
    extra = ["--max-cases", str(len(case_ids))]
    for case_id in case_ids:
        extra.extend(["--case", case_id])
    return run_cli(_development_args(output_dir, *extra), transport=transport)


def test_action_fixture_cites_commitment_segment_and_source_time() -> None:
    response = _valid_response()
    action = response["modules"]["action_items"][0]

    assert action["source_segment_ids"] == ["SEG-0002"]
    assert action["source_timestamp"] == "00:00:08.832"
    assert action["raw_due_expression"] == "trước thứ Sáu này"
    assert action["due_date_resolution"]["status"] == "unresolved"


def test_successful_technical_smoke_is_left_pending_semantic_review(
    configured_env: None, tmp_path: Path
) -> None:
    output = tmp_path / "pending-smoke"

    assert _successful_smoke(output)

    record = json.loads((output / "metadata" / "smoke.json").read_text())
    approval = json.loads((output / "reviews" / "smoke-approval.json").read_text())
    assert record["technical_smoke_status"] == "technical_smoke_passed"
    assert record["semantic_review_status"] == "semantic_review_pending"
    assert approval["decision"] == "pending_review"


def test_live_metrics_include_failed_attempt_and_unattempted_cases(
    configured_env: None, tmp_path: Path
) -> None:
    output = tmp_path / "live-metrics"
    _successful_smoke(output)
    _smoke_review(output)
    calls: list[str] = []
    case_by_request = {
        case.request.request_id: case.case_id for case in load_dataset(DATASET_DIR).cases
    }

    def handle(request: httpx.Request) -> httpx.Response:
        request_body = json.loads(request.content)
        case_id = case_by_request[request_body["request_id"]]
        calls.append(case_id)
        if case_id == "case-003":
            return httpx.Response(503, json={"error": "provider unavailable"})
        return httpx.Response(200, json=_valid_response(case_id))

    assert _run_development_cases(
        output,
        ["case-002", "case-003", "case-004"],
        httpx.MockTransport(handle),
    ) == 1

    record = _development_metadata(output)
    live = record["live_execution"]
    assert calls == ["case-002", "case-003"]
    assert live == {
        "selected_case_count": 3,
        "attempted_count": 2,
        "successful_count": 1,
        "failed_count": 1,
        "reused_count": 0,
        "not_attempted_count": 1,
        "live_execution_success_rate": 0.5,
        "live_execution_success_rate_denominator": 2,
        "failure_categories": {"service_error": 1},
        "pre_request_failure_categories": {},
        "http_status_distribution": {"200": 1, "503": 1},
    }
    assert record["case_results"][-1]["case_id"] == "case-004"
    assert record["case_results"][-1]["status"] == "not_attempted"
    assert record["case_results"][-1]["attempt_count"] == 0
    assert (output / "responses" / "case-002.json").is_file()
    assert json.loads((output / "failures" / "case-003.json").read_text())["http_status"] == 503
    offline = json.loads((output / "reports" / "development" / "report.json").read_text())
    assert offline["dataset"]["evaluated_count"] == 1
    assert offline["dataset"]["skipped_count"] == 2


def test_live_metrics_count_all_successful_attempts(
    configured_env: None, tmp_path: Path
) -> None:
    output = tmp_path / "all-success"
    _successful_smoke(output)
    _smoke_review(output)
    request_to_case = {
        case.request.request_id: case.case_id for case in load_dataset(DATASET_DIR).cases
    }
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        case_id = request_to_case[json.loads(request.content)["request_id"]]
        calls.append(case_id)
        return httpx.Response(200, json=_valid_response(case_id))

    assert _run_development_cases(
        output,
        ["case-002", "case-003"],
        httpx.MockTransport(handle),
    ) == 0

    live = _development_metadata(output)["live_execution"]
    assert calls == ["case-002", "case-003"]
    assert live["selected_case_count"] == 2
    assert live["attempted_count"] == live["successful_count"] == 2
    assert live["failed_count"] == live["reused_count"] == live["not_attempted_count"] == 0
    assert live["live_execution_success_rate"] == 1
    assert live["live_execution_success_rate_denominator"] == 2


def test_live_metrics_include_http_429_without_retry(
    configured_env: None, tmp_path: Path
) -> None:
    output = tmp_path / "rate-limited"
    _successful_smoke(output)
    _smoke_review(output)
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(429, json={"error": "rate limited"})

    assert _run_development_cases(
        output, ["case-002"], httpx.MockTransport(handle)
    ) == 1
    live = _development_metadata(output)["live_execution"]
    assert len(calls) == 1
    assert live["attempted_count"] == live["failed_count"] == 1
    assert live["successful_count"] == 0
    assert live["failure_categories"] == {"service_rate_limit": 1}
    assert live["http_status_distribution"] == {"429": 1}
    assert live["live_execution_success_rate"] == 0
    assert live["live_execution_success_rate_denominator"] == 1


def test_timeout_after_success_counts_timeout_as_failed_attempt(
    configured_env: None, tmp_path: Path
) -> None:
    output = tmp_path / "timeout-after-success"
    _successful_smoke(output)
    _smoke_review(output)
    calls: list[str] = []
    request_to_case = {
        case.request.request_id: case.case_id for case in load_dataset(DATASET_DIR).cases
    }

    def handle(request: httpx.Request) -> httpx.Response:
        case_id = request_to_case[json.loads(request.content)["request_id"]]
        calls.append(case_id)
        if case_id == "case-003":
            raise httpx.ReadTimeout("private timeout text", request=request)
        return httpx.Response(200, json=_valid_response(case_id))

    assert _run_development_cases(
        output, ["case-002", "case-003"], httpx.MockTransport(handle)
    ) == 1
    live = _development_metadata(output)["live_execution"]
    assert calls == ["case-002", "case-003"]
    assert live["attempted_count"] == 2
    assert live["successful_count"] == live["failed_count"] == 1
    assert live["failure_categories"] == {"timeout": 1}
    assert live["http_status_distribution"] == {"200": 1}
    assert live["live_execution_success_rate"] == 0.5


def test_invalid_contract_http_200_counts_as_live_extraction_failure(
    configured_env: None, tmp_path: Path
) -> None:
    output = tmp_path / "invalid-contract"
    calls: list[dict[str, Any]] = []
    invalid = _valid_response()
    invalid["request_id"] = "wrong-request"

    assert run_cli(
        _smoke_args(output), transport=_success_transport(invalid, calls)
    ) == 1

    record = json.loads((output / "metadata" / "smoke.json").read_text())
    live = record["live_execution"]
    assert live["attempted_count"] == 1
    assert live["successful_count"] == 0
    assert live["failed_count"] == 1
    assert live["live_execution_success_rate"] == 0
    assert live["http_status_distribution"] == {"200": 1}
    assert live["failure_categories"] == {"response_contract_invalid": 1}


def test_reused_smoke_is_excluded_from_development_success_rate(
    configured_env: None, tmp_path: Path
) -> None:
    output = tmp_path / "reuse-rate"
    _successful_smoke(output)
    _smoke_review(output)

    assert _run_development_cases(
        output,
        ["case-001", "case-002"],
        _success_transport(_valid_response("case-002"), []),
    ) == 0
    live = _development_metadata(output)["live_execution"]
    assert live["selected_case_count"] == 2
    assert live["attempted_count"] == live["successful_count"] == 1
    assert live["reused_count"] == 1
    assert live["not_attempted_count"] == live["failed_count"] == 0
    assert live["live_execution_success_rate"] == 1
    assert live["live_execution_success_rate_denominator"] == 1


def test_reused_only_run_has_null_live_success_rate(
    configured_env: None, tmp_path: Path
) -> None:
    output = tmp_path / "reused-only"
    _successful_smoke(output)
    _smoke_review(output)

    assert _run_development_cases(
        output, ["case-001"], httpx.MockTransport(lambda request: pytest.fail("no request expected"))
    ) == 0
    live = _development_metadata(output)["live_execution"]
    assert live["selected_case_count"] == 1
    assert live["attempted_count"] == 0
    assert live["successful_count"] == live["failed_count"] == 0
    assert live["reused_count"] == 1
    assert live["not_attempted_count"] == 0
    assert live["live_execution_success_rate"] is None
    assert live["live_execution_success_rate_denominator"] == 0


def test_development_without_smoke_review_is_blocked_before_http(
    configured_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "missing-review"
    calls = _successful_smoke(output)
    additional_calls: list[dict[str, Any]] = []

    assert _run_development_cases(
        output,
        ["case-002"],
        _success_transport(_valid_response("case-002"), additional_calls),
    ) == 3
    assert len(calls) == 1
    assert additional_calls == []
    assert "semantic_review_pending" in capsys.readouterr().err


def test_incomplete_smoke_review_remains_pending_and_blocks_development(
    configured_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "partial-review"
    _successful_smoke(output)
    _smoke_review(output, reviewed_claims=[{"claim_id": "summary.overview", "verdict": "supported"}])
    calls: list[dict[str, Any]] = []

    assert run_cli(["verify-smoke-review", "--output-dir", str(output)]) == 3
    assert _run_development_cases(
        output, ["case-002"], _success_transport(_valid_response("case-002"), calls)
    ) == 3
    assert calls == []
    captured = capsys.readouterr()
    assert "semantic_review_pending" in captured.out + captured.err


def test_unsupported_semantic_claim_fails_smoke_quality_gate(
    configured_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "unsupported-claim"
    _successful_smoke(output)
    claims = [
        {"claim_id": claim_id, "verdict": "supported"}
        for claim_id in reviewable_claim_ids(_valid_response())
    ]
    claims[0] = {**claims[0], "verdict": "unsupported"}
    _smoke_review(output, reviewed_claims=claims)

    assert run_cli(["verify-smoke-review", "--output-dir", str(output)]) == 1
    result = json.loads((output / "metadata" / "smoke.json").read_text())
    assert result["technical_smoke_status"] == "technical_smoke_passed"
    assert result["semantic_review_status"] == "semantic_review_pending"


@pytest.mark.parametrize(
    ("response_change", "expected_failure"),
    [
        ({"owner": "Lan"}, "owner"),
        ({"raw_due_expression": "ngày mai"}, "deadline"),
    ],
    ids=["fabricated-owner", "unsupported-deadline"],
)
def test_fabricated_owner_or_deadline_fails_smoke_quality_gate(
    configured_env: None,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    response_change: dict[str, Any],
    expected_failure: str,
) -> None:
    output = tmp_path / expected_failure
    response = _valid_response()
    response["modules"]["action_items"][0].update(response_change)
    _successful_smoke(output, response=response)
    _smoke_review(output)

    assert run_cli(["verify-smoke-review", "--output-dir", str(output)]) == 1
    message = capsys.readouterr().out.lower()
    assert expected_failure in message


def test_malformed_smoke_review_is_rejected_without_traceback_or_http(
    configured_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "bad-review"
    _successful_smoke(output)
    review_path = output / "reviews" / "review-template-smoke.json"
    review_path.write_text('{"cases":{"case-001":{"summary_review":{"faithfulness":8}}}}')
    _smoke_review(output, summary_review={"faithfulness": 8})
    calls: list[dict[str, Any]] = []

    assert _run_development_cases(
        output, ["case-002"], _success_transport(_valid_response("case-002"), calls)
    ) == 3
    assert calls == []
    error = capsys.readouterr().err.lower()
    assert "review" in error
    assert "traceback" not in error


def test_malformed_review_is_rejected_even_before_approval(
    configured_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "malformed-pending-review"
    _successful_smoke(output)
    review_path = output / "reviews" / "review-template-smoke.json"
    review_path.write_text("{not-json", encoding="utf-8")

    assert run_cli(["verify-smoke-review", "--output-dir", str(output)]) == 3
    assert "invalid_review" in capsys.readouterr().err


def test_malformed_smoke_approval_is_rejected_without_traceback(
    configured_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "bad-approval"
    _successful_smoke(output)
    _smoke_review(output)
    approval_path = output / "reviews" / "smoke-approval.json"
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["decision"] = []
    approval_path.write_text(json.dumps(approval), encoding="utf-8")

    assert run_cli(["verify-smoke-review", "--output-dir", str(output)]) == 3
    error = capsys.readouterr().err.lower()
    assert "invalid_review" in error
    assert "traceback" not in error


def test_review_for_another_saved_response_is_rejected(
    configured_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "stale-review"
    _successful_smoke(output)
    _smoke_review(output)
    response_path = output / "responses" / "case-001.json"
    changed = json.loads(response_path.read_text())
    changed["modules"]["meeting_summary"]["overview"] += " Thay đổi sau review."
    response_path.write_text(json.dumps(changed, ensure_ascii=False, indent=2))

    assert run_cli(["verify-smoke-review", "--output-dir", str(output)]) == 3
    assert "fingerprint" in capsys.readouterr().err.lower()


def test_valid_review_and_explicit_approval_allow_development(
    configured_env: None, tmp_path: Path
) -> None:
    output = tmp_path / "approved-smoke"
    _successful_smoke(output)
    _smoke_review(output)

    assert run_cli(["verify-smoke-review", "--output-dir", str(output)]) == 0
    development_calls: list[dict[str, Any]] = []
    assert _run_development_cases(
        output,
        ["case-002"],
        _success_transport(_valid_response("case-002"), development_calls),
    ) == 0
    assert len(development_calls) == 1
    run = _development_metadata(output)
    assert run["smoke_quality_gate"]["status"] == "semantic_review_passed"
    assert run["smoke_quality_gate"]["decision"] == "approved"


def test_explicit_rejection_does_not_authorize_development(
    configured_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "rejected-smoke"
    _successful_smoke(output)
    _smoke_review(output, decision="rejected")
    calls: list[dict[str, Any]] = []

    assert _run_development_cases(
        output, ["case-002"], _success_transport(_valid_response("case-002"), calls)
    ) == 3
    assert calls == []
    assert "semantic_review_failed" in capsys.readouterr().err


def test_development_authorization_remains_required_after_smoke_approval(
    configured_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "approval-without-dev-ack"
    _successful_smoke(output)
    _smoke_review(output)
    calls: list[dict[str, Any]] = []
    args = [
        "development",
        "--max-cases",
        "1",
        "--spend-limit-usd",
        "0.25",
        "--confirm-account-spending-limit",
        "--output-dir",
        str(output),
        "--case",
        "case-002",
    ]

    assert run_cli(args, transport=_success_transport(_valid_response("case-002"), calls)) == 3
    assert calls == []
    assert "authorize-development" in capsys.readouterr().err


def test_manual_match_decision_resolves_paraphrase_for_smoke_gate(
    configured_env: None, tmp_path: Path
) -> None:
    output = tmp_path / "paraphrase-review"
    response = _valid_response()
    response["modules"]["action_items"][0]["task"] = "Hoàn tất API đặt lịch"
    _successful_smoke(output, response=response)
    _smoke_review(
        output,
        action_matches=[
            {
                "prediction_id": "ACT-001",
                "gold_id": "GOLD-ACT-001",
                "decision": "match",
                "reviewer": "reviewer-a",
            }
        ],
    )

    assert run_cli(["verify-smoke-review", "--output-dir", str(output)]) == 0
