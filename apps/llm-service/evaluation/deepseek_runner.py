"""Explicitly authorized DeepSeek runs through the local LLM Service API.

The ordinary invocation is a network-free preflight. This module never calls
OpenRouter directly and deliberately leaves ``evaluation.runner`` offline.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import ipaddress
import json
import math
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.request import ExtractionRequest
from evaluation.loader import DATASET_DIR, DatasetCase, DatasetLoadResult, load_dataset
from evaluation.reporting import write_reports
from evaluation.runner import evaluate_offline
from evaluation.validation import ResponseValidation, validate_response

MODEL_ID = "deepseek/deepseek-v4.1-flash-1017"
DEFAULT_OUTPUT_DIR = Path("/tmp/llm03.7.2")
MIN_OUTPUT_TOKENS = 4096
DEVELOPMENT_CASE_IDS = tuple(f"case-{number:03d}" for number in range(1, 11))
HOLDOUT_CASE_IDS = tuple(f"case-{number:03d}" for number in range(11, 17))


class RunnerError(ValueError):
    """A sanitized preflight, authorization, or output-safety error."""


class SmokeReviewGateError(ValueError):
    """A technical, pending, invalid, or failed smoke-review gate state."""

    def __init__(self, status: str, message: str) -> None:
        super().__init__(message)
        self.status = status


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _load_runtime_settings() -> tuple[Settings | None, list[str]]:
    try:
        settings = Settings(_env_file=None)
    except ValidationError as error:
        names = sorted(
            {
                str(item["loc"][0])
                for item in error.errors(include_input=False)
                if item.get("loc")
            }
        )
        details = ", ".join(names) if names else "runtime settings"
        return None, [f"Invalid runtime configuration: {details}."]

    issues: list[str] = []
    if settings.llm_service_token is None:
        issues.append("LLM_SERVICE_TOKEN is not configured.")
    if settings.openrouter_api_key is None:
        issues.append("OPENROUTER_API_KEY is not configured for the service runtime.")
    if settings.openrouter_model != MODEL_ID:
        issues.append(f"OPENROUTER_MODEL must be exactly {MODEL_ID}.")
    if settings.openrouter_structured_output_mode != "json_object":
        issues.append("OPENROUTER_STRUCTURED_OUTPUT_MODE must be json_object.")
    if settings.openrouter_max_output_tokens < MIN_OUTPUT_TOKENS:
        issues.append(
            f"OPENROUTER_MAX_OUTPUT_TOKENS must be at least {MIN_OUTPUT_TOKENS}."
        )
    if not settings.openrouter_require_parameters:
        issues.append("OPENROUTER_REQUIRE_PARAMETERS must be true for JSON formatting.")
    if (
        settings.llm_service_request_timeout_seconds
        < 2 * settings.llm_service_provider_timeout_seconds
    ):
        issues.append(
            "LLM_SERVICE_REQUEST_TIMEOUT_SECONDS must cover both bounded provider stages."
        )
    try:
        provider_base = urlsplit(settings.openrouter_base_url)
    except ValueError:
        provider_base = urlsplit("")
    if (
        provider_base.scheme != "https"
        or provider_base.hostname != "openrouter.ai"
        or provider_base.path.rstrip("/") != "/api/v1"
        or provider_base.username is not None
        or provider_base.password is not None
        or provider_base.query
        or provider_base.fragment
    ):
        issues.append("OPENROUTER_BASE_URL must be the HTTPS OpenRouter API base URL.")
    return settings, issues


def _service_url(settings: Settings, override: str | None) -> str:
    origin = override or f"http://127.0.0.1:{settings.llm_service_port}"
    try:
        parsed = urlsplit(origin)
        hostname = parsed.hostname
        port = parsed.port or settings.llm_service_port
        is_loopback = hostname == "localhost" or (
            hostname is not None and ipaddress.ip_address(hostname).is_loopback
        )
    except (ValueError, TypeError):
        is_loopback = False
        hostname = None
        port = settings.llm_service_port
        parsed = urlsplit("")
    if (
        parsed.scheme not in {"http", "https"}
        or not is_loopback
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or not 1 <= port <= 65535
    ):
        raise RunnerError("Service URL must be a loopback HTTP(S) origin without credentials.")
    host = f"[{hostname}]" if hostname and ":" in hostname else hostname
    return f"{parsed.scheme}://{host}:{port}/v1/extractions"


def _load_preflight(
    dataset_dir: str | Path = DATASET_DIR,
    service_url: str | None = None,
) -> tuple[DatasetLoadResult, Settings | None, str | None, list[str]]:
    dataset = load_dataset(dataset_dir)
    settings, settings_issues = _load_runtime_settings()
    issues = list(settings_issues)
    if not dataset.valid:
        issues.extend(
            f"{issue.case_id}:{issue.path or '-'}:{issue.code}: {issue.message}"
            for issue in dataset.issues
        )
    elif len(dataset.cases) != 16:
        issues.append("Dataset must contain exactly 16 cases.")
    else:
        development_count = sum(case.split == "development" for case in dataset.cases)
        holdout_count = sum(case.split == "holdout" for case in dataset.cases)
        if development_count != 10 or holdout_count != 6:
            issues.append("Dataset must contain 10 development and 6 holdout cases.")

    endpoint: str | None = None
    if settings is not None:
        try:
            endpoint = _service_url(settings, service_url)
        except RunnerError as error:
            issues.append(str(error))
    return dataset, settings, endpoint, issues


def _print_preflight(
    dataset: DatasetLoadResult,
    settings: Settings | None,
    endpoint: str | None,
    issues: list[str],
) -> int:
    if issues:
        print("DeepSeek runner preflight: NOT READY (no network request made).")
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 2

    assert settings is not None
    development_count = sum(case.split == "development" for case in dataset.cases)
    holdout_count = sum(case.split == "holdout" for case in dataset.cases)
    print("DeepSeek runner preflight: READY (no network request made).")
    print(f"Dataset: {len(dataset.cases)} valid cases ({development_count} development, {holdout_count} holdout).")
    print(f"Model: {settings.openrouter_model}")
    print(f"Structured output: {settings.openrouter_structured_output_mode}")
    print(f"Maximum output tokens per provider generation: {settings.openrouter_max_output_tokens}")
    print(f"Service endpoint: {endpoint}")
    print(f"Request/provider timeouts: {settings.llm_service_request_timeout_seconds:g}s / {settings.llm_service_provider_timeout_seconds:g}s")
    print("Credentials configured: service token and OpenRouter key (values hidden).")
    print("Paid execution is not authorized by preflight.")
    return 0


def _authorize(args: argparse.Namespace) -> None:
    if args.command == "smoke":
        if not args.authorize_smoke:
            raise RunnerError("Smoke mode requires the separate --authorize-smoke acknowledgment.")
        if args.max_cases != 1:
            raise RunnerError("Smoke mode is fixed to case-001 and requires --max-cases 1.")
    elif args.command == "development":
        if not args.authorize_development:
            raise RunnerError(
                "Development mode requires separate --authorize-development approval."
            )
        if args.max_cases is None or not 1 <= args.max_cases <= 10:
            raise RunnerError("Development mode requires --max-cases between 1 and 10.")
    else:
        if not args.authorize_holdout:
            raise RunnerError("Holdout mode requires the separate --authorize-holdout acknowledgment.")
        if args.max_cases is None or not 1 <= args.max_cases <= len(HOLDOUT_CASE_IDS):
            raise RunnerError("Holdout mode requires --max-cases between 1 and 6.")
    if (
        args.spend_limit_usd is None
        or not math.isfinite(args.spend_limit_usd)
        or args.spend_limit_usd <= 0
    ):
        raise RunnerError("Live execution requires an explicit positive --spend-limit-usd.")
    if not args.confirm_account_spending_limit:
        raise RunnerError(
            "Live execution requires --confirm-account-spending-limit after an account-level cap is configured."
        )


def _select_cases(dataset: DatasetLoadResult, args: argparse.Namespace) -> list[DatasetCase]:
    allowed_case_ids = (
        HOLDOUT_CASE_IDS if args.command == "holdout" else DEVELOPMENT_CASE_IDS
    )
    expected_split = "holdout" if args.command == "holdout" else "development"
    if args.command == "smoke":
        case_ids = ["case-001"]
    elif args.case_ids:
        if len(args.case_ids) != len(set(args.case_ids)):
            raise RunnerError(f"{expected_split.title()} case IDs must not be repeated.")
        case_ids = list(args.case_ids)
    else:
        case_ids = list(allowed_case_ids[: args.max_cases])

    cases: list[DatasetCase] = []
    for case_id in case_ids:
        case = dataset.case(case_id)
        if case is None:
            raise RunnerError(f"Unknown {expected_split} case ID: {case_id}.")
        if case_id not in allowed_case_ids or case.split != expected_split:
            if expected_split == "development":
                raise RunnerError(
                    f"Live evaluation is forbidden for non-development case {case_id}."
                )
            raise RunnerError(
                f"Live {expected_split} evaluation is forbidden for case {case_id}."
            )
        cases.append(case)

    if args.command == "smoke" and cases != [dataset.case("case-001")]:
        raise RunnerError("Smoke mode can execute only case-001.")
    if len(cases) > args.max_cases:
        raise RunnerError("Selected case count exceeds --max-cases.")
    return cases


def _fingerprint(case: DatasetCase, settings: Settings, endpoint: str) -> str:
    request_bytes = json.dumps(
        case.request.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    config = {
        "dataset_version": "1.0.0",
        "model_id": settings.openrouter_model,
        "structured_output_mode": settings.openrouter_structured_output_mode,
        "max_output_tokens": settings.openrouter_max_output_tokens,
        "temperature": settings.openrouter_temperature,
        "require_parameters": settings.openrouter_require_parameters,
        "provider_timeout_seconds": settings.llm_service_provider_timeout_seconds,
        "request_timeout_seconds": settings.llm_service_request_timeout_seconds,
        "service_endpoint": endpoint,
        "request_sha256": hashlib.sha256(request_bytes).hexdigest(),
    }
    config_bytes = json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(config_bytes).hexdigest()


def _validate_saved_response(case: DatasetCase, path: Path) -> ResponseValidation | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    result = validate_response(case.request, raw)
    if (
        not result.semantic_evaluation_available
        or result.response is None
        or result.response.processing.provider != "openrouter"
        or result.response.processing.model_id != MODEL_ID
    ):
        return None
    return result


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _output_paths(output_dir: str | Path, dataset_root: Path, mode: str) -> dict[str, Path]:
    root = Path(output_dir).expanduser().resolve()
    dataset_root = dataset_root.resolve()
    if root == dataset_root or root.is_relative_to(dataset_root):
        raise RunnerError("Output directory must be outside the immutable dataset.")
    return {
        "root": root,
        "responses": root / "responses",
        "failures": root / "failures",
        "metadata": root / "metadata",
        "reports": root / "reports" / mode,
        "reviews": root / "reviews",
        "run_metadata": root / "metadata" / f"{mode}.json",
        "review_template": root / "reviews" / f"review-template-{mode}.json",
        "smoke_approval": root / "reviews" / "smoke-approval.json",
    }


def _prepare_output(
    paths: dict[str, Path],
    dataset: DatasetLoadResult,
    cases: list[DatasetCase],
    settings: Settings,
    endpoint: str,
    mode: str,
) -> list[str]:
    conflicts: list[str] = []
    fixed_paths = [
        paths["run_metadata"],
        paths["review_template"],
        paths["reports"] / "report.json",
        paths["reports"] / "report.md",
    ]
    if mode == "smoke":
        fixed_paths.append(paths["smoke_approval"])
    for fixed_path in fixed_paths:
        if fixed_path.exists():
            conflicts.append(f"Existing output will not be overwritten: {fixed_path.name}.")

    for case in cases:
        response_path = paths["responses"] / f"{case.case_id}.json"
        metadata_path = paths["metadata"] / f"{case.case_id}.json"
        failure_path = paths["failures"] / f"{case.case_id}.json"
        if response_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                metadata = None
            response = _validate_saved_response(case, response_path)
            expected_fingerprint = _fingerprint(case, settings, endpoint)
            if (
                not isinstance(metadata, dict)
                or metadata.get("status") != "success"
                or metadata.get("mode") != ("smoke" if mode == "development" and case.case_id == "case-001" else mode)
                or metadata.get("config_fingerprint") != expected_fingerprint
                or response is None
            ):
                conflicts.append(
                    f"Existing response for {case.case_id} is not a verified same-configuration result."
                )
        elif metadata_path.exists() or failure_path.exists():
            conflicts.append(
                f"Existing case record for {case.case_id} will not be overwritten."
            )

    if mode == "development":
        # Development may select a subset, but the smoke response remains mandatory.
        smoke_case = dataset.case("case-001")
        try:
            smoke_record = json.loads(paths["metadata"].joinpath("smoke.json").read_text(encoding="utf-8"))
            smoke_case_metadata = json.loads(paths["metadata"].joinpath("case-001.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            smoke_record = None
            smoke_case_metadata = None
        smoke_validation = (
            _validate_saved_response(smoke_case, paths["responses"] / "case-001.json")
            if smoke_case is not None
            else None
        )
        if (
            not isinstance(smoke_record, dict)
            or smoke_record.get("mode") != "smoke"
            or smoke_record.get("run_status") != "success"
            or smoke_record.get("technical_smoke_status") != "technical_smoke_passed"
            or not isinstance(smoke_case_metadata, dict)
            or smoke_case_metadata.get("mode") != "smoke"
            or smoke_case_metadata.get("status") != "success"
            or not isinstance(smoke_case_metadata.get("response_sha256"), str)
            or smoke_case_metadata.get("config_fingerprint")
            != (_fingerprint(smoke_case, settings, endpoint) if smoke_case else None)
            or smoke_validation is None
        ):
            conflicts.append("Development requires a successful same-configuration case-001 smoke run in this output directory.")
    if conflicts:
        return conflicts
    for name in ("responses", "failures", "metadata", "reports", "reviews"):
        paths[name].mkdir(parents=True, exist_ok=True)
    return []


def _response_failure_category(status_code: int) -> str:
    if status_code == 401:
        return "service_authentication"
    if status_code == 403:
        return "service_forbidden"
    if status_code == 429:
        return "service_rate_limit"
    if 500 <= status_code <= 599:
        return "service_error"
    return "service_http_error"


def _write_json_exclusive(path: Path, value: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as output:
        output.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))
        output.write("\n")


def _case_fingerprint_metadata(
    *,
    case: DatasetCase,
    settings: Settings,
    endpoint: str,
    mode: str,
    status: str,
    http_status: int | None,
    latency_seconds: float,
    response: ResponseValidation | None,
    failure_category: str | None,
    http_attempted: bool,
    response_sha256: str | None = None,
) -> dict[str, Any]:
    processing = response.response.processing if response and response.response else None
    usage = processing.token_usage if processing else None
    return {
        "case_id": case.case_id,
        "split": case.split,
        "mode": mode,
        "status": status,
        "failure_category": failure_category,
        "http_status": http_status,
        "latency_seconds": round(latency_seconds, 6),
        "http_attempted": http_attempted,
        "attempt_count": int(http_attempted),
        "retry_count": 0,
        "provider": processing.provider if processing else "openrouter",
        "requested_model_id": MODEL_ID,
        "returned_model_id": processing.model_id if processing else None,
        "actual_provider_route": None,
        "actual_provider_route_status": "not_exposed_by_contract",
        "prompt_version": processing.prompt_version if processing else None,
        "evidence_prompt_version": processing.evidence_prompt_version if processing else None,
        "input_tokens": usage.input_tokens if usage else None,
        "output_tokens": usage.output_tokens if usage else None,
        "token_usage_status": "reported" if usage else "unavailable",
        "estimated_cost_usd": None,
        "actual_billed_cost_usd": None,
        "cost_status": "unavailable_provider_route_or_billing_data",
        "config_fingerprint": _fingerprint(case, settings, endpoint),
        "response_sha256": response_sha256,
        "recorded_at": _now(),
    }


async def _send_one(
    client: httpx.AsyncClient,
    *,
    case: DatasetCase,
    settings: Settings,
    endpoint: str,
    mode: str,
) -> dict[str, Any]:
    allowed_case_ids = HOLDOUT_CASE_IDS if mode == "holdout" else DEVELOPMENT_CASE_IDS
    expected_split = "holdout" if mode == "holdout" else "development"
    if case.split != expected_split or case.case_id not in allowed_case_ids:
        if expected_split == "development":
            raise RunnerError(
                f"Live evaluation is forbidden for non-development case {case.case_id}."
            )
        raise RunnerError(f"Live {expected_split} evaluation is forbidden for case {case.case_id}.")

    request_path = case.case_dir / "llm-request.json"
    try:
        payload = json.loads(request_path.read_text(encoding="utf-8"))
        validated_request = ExtractionRequest.model_validate(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError):
        return {"case": case, "status": "not_attempted", "http_attempted": False, "failure_category": "request_file_invalid", "http_status": None, "latency_seconds": 0.0, "response": None}
    if not isinstance(payload, dict) or validated_request != case.request:
        return {"case": case, "status": "not_attempted", "http_attempted": False, "failure_category": "request_file_invalid", "http_status": None, "latency_seconds": 0.0, "response": None}

    started = time.perf_counter()
    try:
        response = await client.post(endpoint, json=payload)
    except httpx.TimeoutException:
        return {"case": case, "status": "failed", "http_attempted": True, "failure_category": "timeout", "http_status": None, "latency_seconds": time.perf_counter() - started, "response": None}
    except httpx.RequestError:
        return {"case": case, "status": "failed", "http_attempted": True, "failure_category": "connection_error", "http_status": None, "latency_seconds": time.perf_counter() - started, "response": None}
    latency = time.perf_counter() - started
    if response.status_code != 200:
        return {"case": case, "status": "failed", "http_attempted": True, "failure_category": _response_failure_category(response.status_code), "http_status": response.status_code, "latency_seconds": latency, "response": None}
    try:
        body = response.json()
    except (ValueError, UnicodeError):
        return {"case": case, "status": "failed", "http_attempted": True, "failure_category": "invalid_json_response", "http_status": response.status_code, "latency_seconds": latency, "response": None}
    if not isinstance(body, dict):
        return {"case": case, "status": "failed", "http_attempted": True, "failure_category": "invalid_json_response", "http_status": response.status_code, "latency_seconds": latency, "response": None}

    validation = validate_response(case.request, body)
    if (
        not validation.semantic_evaluation_available
        or validation.response is None
        or validation.response.processing.provider != "openrouter"
        or validation.response.processing.model_id != MODEL_ID
    ):
        category = (
            "unexpected_model"
            if validation.response is not None
            and validation.response.processing.model_id != MODEL_ID
            else "response_contract_invalid"
        )
        return {"case": case, "status": "failed", "http_attempted": True, "failure_category": category, "http_status": response.status_code, "latency_seconds": latency, "response": None}

    return {"case": case, "status": "success", "http_attempted": True, "failure_category": None, "http_status": response.status_code, "latency_seconds": latency, "response": body, "validation": validation}


async def _execute(
    *,
    cases: list[DatasetCase],
    dataset: DatasetLoadResult,
    settings: Settings,
    endpoint: str,
    paths: dict[str, Path],
    mode: str,
    spend_limit_usd: float,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    results: list[dict[str, Any]] = []
    reused_case_ids: list[str] = []
    http_attempt_count = 0
    timeout = httpx.Timeout(settings.llm_service_request_timeout_seconds)
    headers = {
        "Authorization": f"Bearer {settings.llm_service_token.get_secret_value()}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(
        timeout=timeout,
        transport=transport,
        follow_redirects=False,
        trust_env=False,
        headers=headers,
    ) as client:
        for case in cases:
            allowed_case_ids = HOLDOUT_CASE_IDS if mode == "holdout" else DEVELOPMENT_CASE_IDS
            expected_split = "holdout" if mode == "holdout" else "development"
            if case.split != expected_split or case.case_id not in allowed_case_ids:
                if expected_split == "development":
                    raise RunnerError(
                        f"Live evaluation is forbidden for non-development case {case.case_id}."
                    )
                raise RunnerError(f"Live {expected_split} evaluation is forbidden for case {case.case_id}.")

            response_path = paths["responses"] / f"{case.case_id}.json"
            if response_path.exists():
                validation = _validate_saved_response(case, response_path)
                if validation is None:
                    raise RunnerError(f"Existing response for {case.case_id} failed validation.")
                reused_case_ids.append(case.case_id)
                results.append(
                    {
                        "case_id": case.case_id,
                        "split": case.split,
                        "status": "reused",
                        "http_status": 200,
                        "http_attempted": False,
                        "attempt_count": 0,
                        "latency_seconds": None,
                        "failure_category": None,
                    }
                )
                continue

            max_case_count = len(HOLDOUT_CASE_IDS) if mode == "holdout" else len(DEVELOPMENT_CASE_IDS)
            if http_attempt_count >= max_case_count:
                if mode == "holdout":
                    raise RunnerError(
                        "Holdout request count exceeded the case-count maximum of 6."
                    )
                raise RunnerError(
                    "Development request count exceeded the hard case-count maximum of 10."
                )
            result = await _send_one(
                client,
                case=case,
                settings=settings,
                endpoint=endpoint,
                mode=mode,
            )
            http_attempted = result["http_attempted"]
            http_attempt_count += int(http_attempted)
            if result["status"] == "success":
                _write_json_exclusive(response_path, result["response"])
                response_sha256 = _file_sha256(response_path)
                metadata = _case_fingerprint_metadata(
                    case=case,
                    settings=settings,
                    endpoint=endpoint,
                    mode=mode,
                    status="success",
                    http_status=result["http_status"],
                    latency_seconds=result["latency_seconds"],
                    response=result["validation"],
                    failure_category=None,
                    http_attempted=True,
                    response_sha256=response_sha256,
                )
                _write_json_exclusive(paths["metadata"] / f"{case.case_id}.json", metadata)
                results.append(
                    {
                        "case_id": case.case_id,
                        "split": case.split,
                        "status": "success",
                        "http_status": result["http_status"],
                        "http_attempted": True,
                        "attempt_count": 1,
                        "latency_seconds": round(result["latency_seconds"], 6),
                        "failure_category": None,
                        "provider": metadata["provider"],
                        "model_id": metadata["returned_model_id"],
                        "prompt_version": metadata["prompt_version"],
                        "evidence_prompt_version": metadata["evidence_prompt_version"],
                        "input_tokens": metadata["input_tokens"],
                        "output_tokens": metadata["output_tokens"],
                    }
                )
                continue

            failure_record = {
                "case_id": case.case_id,
                "split": case.split,
                "status": "failed" if http_attempted else "not_attempted",
                "failure_category": result["failure_category"],
                "http_status": result["http_status"],
                "http_attempted": http_attempted,
                "attempt_count": int(http_attempted),
                "retry_count": 0,
                "latency_seconds": round(result["latency_seconds"], 6),
                "recorded_at": _now(),
            }
            _write_json_exclusive(paths["failures"] / f"{case.case_id}.json", failure_record)
            metadata = _case_fingerprint_metadata(
                case=case,
                settings=settings,
                endpoint=endpoint,
                mode=mode,
                status="failed" if http_attempted else "not_attempted",
                http_status=result["http_status"],
                latency_seconds=result["latency_seconds"],
                response=None,
                failure_category=result["failure_category"],
                http_attempted=http_attempted,
            )
            _write_json_exclusive(paths["metadata"] / f"{case.case_id}.json", metadata)
            results.append(
                {
                    "case_id": case.case_id,
                    "split": case.split,
                    "status": "failed" if http_attempted else "not_attempted",
                    "http_status": result["http_status"],
                    "http_attempted": http_attempted,
                    "attempt_count": int(http_attempted),
                    "latency_seconds": round(result["latency_seconds"], 6),
                    "failure_category": result["failure_category"],
                }
            )
            # A failed request may have incurred cost; a local request error stops too.
            break

    completed_case_ids = {result["case_id"] for result in results}
    for case in cases:
        if case.case_id not in completed_case_ids:
            results.append(
                {
                    "case_id": case.case_id,
                    "split": case.split,
                    "status": "not_attempted",
                    "http_status": None,
                    "http_attempted": False,
                    "attempt_count": 0,
                    "latency_seconds": None,
                    "failure_category": None,
                    "not_attempted_reason": "run_stopped_after_prior_failure",
                }
            )

    return results, reused_case_ids


def _create_review_template(path: Path, case_ids: list[str]) -> None:
    _write_json_exclusive(path, {"cases": {case_id: {} for case_id in case_ids}})


def _create_smoke_approval_template(
    path: Path,
    *,
    response_sha256: str,
) -> None:
    _write_json_exclusive(
        path,
        {
            "schema_version": "llm03.7.2-smoke-approval-v1",
            "case_id": "case-001",
            "response_sha256": response_sha256,
            "review_file": "review-template-smoke.json",
            "review_sha256": None,
            "decision": "pending_review",
            "reviewer": None,
            "rationale": None,
        },
    )


def _live_execution_metrics(
    cases: list[DatasetCase], results: list[dict[str, Any]]
) -> dict[str, Any]:
    attempted = [result for result in results if result.get("http_attempted") is True]
    successful_count = sum(result.get("status") == "success" for result in attempted)
    failed_count = sum(result.get("status") == "failed" for result in attempted)
    reused_count = sum(result.get("status") == "reused" for result in results)
    attempted_count = len(attempted)
    not_attempted_count = len(cases) - attempted_count - reused_count
    if successful_count + failed_count != attempted_count or not_attempted_count < 0:
        raise RunnerError("Live execution case accounting is inconsistent.")

    failure_categories = Counter(
        result["failure_category"]
        for result in attempted
        if result.get("status") == "failed" and result.get("failure_category")
    )
    pre_request_failure_categories = Counter(
        result["failure_category"]
        for result in results
        if not result.get("http_attempted")
        and result.get("status") == "not_attempted"
        and result.get("failure_category")
    )
    status_distribution = Counter(
        str(result["http_status"])
        for result in attempted
        if result.get("http_status") is not None
    )
    return {
        "selected_case_count": len(cases),
        "attempted_count": attempted_count,
        "successful_count": successful_count,
        "failed_count": failed_count,
        "reused_count": reused_count,
        "not_attempted_count": not_attempted_count,
        "live_execution_success_rate": (
            successful_count / attempted_count if attempted_count else None
        ),
        "live_execution_success_rate_denominator": attempted_count,
        "failure_categories": dict(sorted(failure_categories.items())),
        "pre_request_failure_categories": dict(
            sorted(pre_request_failure_categories.items())
        ),
        "http_status_distribution": dict(sorted(status_distribution.items())),
    }


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SmokeReviewGateError("invalid_review", f"Could not read {label}.") from error
    if not isinstance(value, dict):
        raise SmokeReviewGateError("invalid_review", f"{label} must be a JSON object.")
    return value


def _valid_review_identity(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and not any(ord(character) < 32 for character in value)
    )


def _smoke_quality_gate(
    dataset: DatasetLoadResult,
    paths: dict[str, Path],
) -> dict[str, Any]:
    case = dataset.case("case-001")
    if case is None:
        raise SmokeReviewGateError("technical_smoke_failed", "case-001 is missing from the dataset.")
    try:
        run_record = _read_json_object(paths["metadata"] / "smoke.json", label="smoke run record")
        case_metadata = _read_json_object(paths["metadata"] / "case-001.json", label="smoke case metadata")
    except SmokeReviewGateError as error:
        raise SmokeReviewGateError(
            "technical_smoke_failed", "A successful technical smoke record is required."
        ) from error

    live_metrics = run_record.get("live_execution")
    if (
        run_record.get("mode") != "smoke"
        or run_record.get("run_status") != "success"
        or run_record.get("technical_smoke_status") != "technical_smoke_passed"
        or not isinstance(live_metrics, dict)
        or live_metrics.get("attempted_count") != 1
        or live_metrics.get("successful_count") != 1
        or case_metadata.get("mode") != "smoke"
        or case_metadata.get("status") != "success"
    ):
        raise SmokeReviewGateError(
            "technical_smoke_failed", "case-001 has not passed technical smoke validation."
        )

    response_path = paths["responses"] / "case-001.json"
    try:
        response_bytes = response_path.read_bytes()
        response_sha256 = hashlib.sha256(response_bytes).hexdigest()
        response_validation = validate_response(case.request, response_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError):
        raise SmokeReviewGateError(
            "technical_smoke_failed", "The saved case-001 response is unavailable or unreadable."
        ) from None
    if (
        not response_validation.semantic_evaluation_available
        or response_validation.response is None
        or response_validation.response.processing.provider != "openrouter"
        or response_validation.response.processing.model_id != MODEL_ID
        or response_validation.structural_grounding_valid is not True
    ):
        raise SmokeReviewGateError(
            "technical_smoke_failed", "The saved case-001 response no longer passes Contract v1 validation."
        )
    if (
        not isinstance(case_metadata.get("response_sha256"), str)
        or case_metadata["response_sha256"] != response_sha256
    ):
        raise SmokeReviewGateError(
            "invalid_review", "The reviewed response fingerprint does not match the saved smoke response."
        )

    review_path = paths["reviews"] / "review-template-smoke.json"
    approval_path = paths["reviews"] / "smoke-approval.json"
    if not review_path.is_file() or not approval_path.is_file():
        raise SmokeReviewGateError(
            "semantic_review_pending", "Smoke semantic review and explicit approval are pending."
        )
    try:
        review_bytes = review_path.read_bytes()
        approval = _read_json_object(approval_path, label="smoke approval")
    except OSError as error:
        raise SmokeReviewGateError("invalid_review", "Could not read smoke review files.") from error

    expected_approval_fields = {
        "schema_version",
        "case_id",
        "response_sha256",
        "review_file",
        "review_sha256",
        "decision",
        "reviewer",
        "rationale",
    }
    review_sha256 = hashlib.sha256(review_bytes).hexdigest()
    if (
        set(approval) != expected_approval_fields
        or approval.get("schema_version") != "llm03.7.2-smoke-approval-v1"
        or approval.get("case_id") != "case-001"
        or approval.get("response_sha256") != response_sha256
        or approval.get("review_file") != review_path.name
    ):
        raise SmokeReviewGateError(
            "invalid_review", "Smoke approval does not match the saved response and review fingerprints."
        )
    decision = approval.get("decision")
    pending_decision = decision == "pending_review"
    if pending_decision:
        if (
            approval.get("review_sha256") is not None
            or approval.get("reviewer") is not None
            or approval.get("rationale") is not None
        ):
            raise SmokeReviewGateError(
                "invalid_review", "Pending smoke approval contains reviewer or decision data."
            )
    elif not isinstance(decision, str) or decision not in {"approved", "rejected"}:
        raise SmokeReviewGateError("invalid_review", "Smoke approval decision is invalid.")
    elif approval.get("review_sha256") != review_sha256:
        raise SmokeReviewGateError(
            "invalid_review", "Smoke approval does not match the saved review fingerprint."
        )
    elif not _valid_review_identity(approval.get("reviewer")):
        raise SmokeReviewGateError("invalid_review", "Smoke approval requires a reviewer identity.")
    elif not isinstance(approval.get("rationale"), str) or not approval["rationale"].strip():
        raise SmokeReviewGateError("invalid_review", "Smoke approval requires a non-empty rationale.")

    try:
        review_document = json.loads(review_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SmokeReviewGateError("invalid_review", "Smoke review file is not valid UTF-8 JSON.") from error
    if not isinstance(review_document, dict) or set(review_document) != {"cases"}:
        raise SmokeReviewGateError("invalid_review", "Smoke review must use the existing {cases: ...} format.")
    review_cases = review_document["cases"]
    if not isinstance(review_cases, dict):
        raise SmokeReviewGateError("invalid_review", "Smoke review cases must be an object.")
    if set(review_cases) - {"case-001"}:
        raise SmokeReviewGateError("invalid_review", "Smoke review may contain only case-001.")

    try:
        offline_report = evaluate_offline(
            dataset,
            responses_dir=paths["responses"],
            split="development",
            case_ids=["case-001"],
            reviews=review_cases,
        )
    except ValueError as error:
        raise SmokeReviewGateError("invalid_review", "Smoke review annotations failed evaluation validation.") from error
    try:
        current_response_sha256 = _file_sha256(response_path)
    except OSError as error:
        raise SmokeReviewGateError(
            "technical_smoke_failed", "The saved case-001 response became unavailable during review validation."
        ) from error
    if current_response_sha256 != response_sha256:
        raise SmokeReviewGateError(
            "invalid_review", "The saved smoke response changed while validating its review fingerprint."
        )
    case_report = offline_report["cases"][0]
    if case_report.get("status") != "evaluated":
        raise SmokeReviewGateError("technical_smoke_failed", "The saved smoke response cannot be evaluated.")
    if pending_decision:
        raise SmokeReviewGateError(
            "semantic_review_pending", "Smoke review has not received explicit human approval."
        )
    if decision == "rejected":
        raise SmokeReviewGateError("semantic_review_failed", "The human reviewer rejected the smoke result.")
    summary = case_report.get("summary_review", {})
    semantic = case_report.get("semantic_grounding", {})
    action = case_report.get("action_items") or {}
    if (
        summary.get("status") != "reviewed"
        or semantic.get("status") != "reviewed"
        or action.get("matching", {}).get("status") != "complete"
    ):
        raise SmokeReviewGateError(
            "semantic_review_pending", "Summary, semantic claims, or Action Item matching remain unresolved."
        )

    owner = action.get("owner", {})
    deadline = action.get("deadline", {})
    priority = action.get("priority", {})
    if (semantic.get("unsupported") or 0) > 0:
        raise SmokeReviewGateError("semantic_review_failed", "A reviewed required claim is unsupported.")
    if (
        summary.get("required_fact_coverage") != 1
        or summary.get("semantic_source_grounding") != 1
        or summary.get("hallucination_count") != 0
    ):
        raise SmokeReviewGateError("semantic_review_failed", "Summary review found missing facts, weak grounding, or hallucinations.")
    if (
        action.get("tp") != len(case.gold["action_items"])
        or action.get("fp") != 0
        or action.get("fn") != 0
        or action.get("predicted_count") != action.get("expected_count")
    ):
        raise SmokeReviewGateError("semantic_review_failed", "Action Item predictions do not exactly cover the smoke gold labels.")
    if owner.get("accuracy") != 1 or owner.get("unsupported_count") != 0 or owner.get("wrong_owner_count") != 0:
        raise SmokeReviewGateError("semantic_review_failed", "Smoke Action Item owner is incorrect or unsupported.")
    if (
        deadline.get("raw_expression_accuracy") != 1
        or deadline.get("date_denominator") != 0
        or deadline.get("resolved_date_accuracy") is not None
        or deadline.get("temporal_status_accuracy") != 1
        or deadline.get("fabricated_count") != 0
    ):
        raise SmokeReviewGateError("semantic_review_failed", "Smoke Action Item deadline is incorrect or fabricated.")
    if priority.get("explicit_accuracy") != 1 or priority.get("fabricated_count") != 0:
        raise SmokeReviewGateError("semantic_review_failed", "Smoke Action Item priority is incorrect or fabricated.")

    return {
        "status": "semantic_review_passed",
        "decision": decision,
        "reviewer": approval["reviewer"].strip(),
        "response_sha256": response_sha256,
        "review_sha256": review_sha256,
        "summary_reviewer": summary.get("reviewer"),
        "semantic_grounding_reviewer": semantic.get("reviewer"),
        "expected_claim_count": semantic.get("expected_claim_count"),
        "reviewed_claim_count": semantic.get("reviewed_claim_count"),
        "review_coverage": semantic.get("review_coverage"),
        "action_metrics": {
            "tp": action.get("tp"),
            "fp": action.get("fp"),
            "fn": action.get("fn"),
        },
    }


def _run_record(
    *,
    mode: str,
    dataset: DatasetLoadResult,
    settings: Settings,
    endpoint: str,
    cases: list[DatasetCase],
    results: list[dict[str, Any]],
    reused_case_ids: list[str],
    case_limit: int,
    spend_limit_usd: float,
    smoke_quality_gate: dict[str, Any] | None,
) -> dict[str, Any]:
    live_metrics = _live_execution_metrics(cases, results)
    if mode == "smoke":
        technical_smoke_status = (
            "technical_smoke_passed"
            if live_metrics["successful_count"] == 1 and live_metrics["attempted_count"] == 1
            else "technical_smoke_failed"
        )
        semantic_review_status = "semantic_review_pending"
    elif mode == "development":
        technical_smoke_status = (
            smoke_quality_gate.get("technical_smoke_status", "technical_smoke_passed")
            if smoke_quality_gate
            else "technical_smoke_failed"
        )
        semantic_review_status = (
            smoke_quality_gate.get("status", "semantic_review_pending")
            if smoke_quality_gate
            else "semantic_review_pending"
        )
    else:
        technical_smoke_status = None
        semantic_review_status = None
    return {
        "schema_version": "llm03.7.2-run-v1",
        "mode": mode,
        "run_status": "success" if results and all(result["status"] in {"success", "reused"} for result in results) else "failed",
        "recorded_at": _now(),
        "dataset_id": dataset.manifest.get("dataset_id"),
        "dataset_version": dataset.manifest.get("dataset_version"),
        "split": "holdout" if mode == "holdout" else "development",
        "selected_case_ids": [case.case_id for case in cases],
        "case_limit": case_limit,
        "reused_case_ids": reused_case_ids,
        "case_results": results,
        "live_execution": live_metrics,
        "attempt_count": live_metrics["attempted_count"],
        "technical_smoke_status": technical_smoke_status,
        "semantic_review_status": semantic_review_status,
        "smoke_quality_gate": smoke_quality_gate,
        "retry_count": 0,
        "max_concurrency": 1,
        "provider": "openrouter",
        "requested_model_id": settings.openrouter_model,
        "actual_provider_route": None,
        "actual_provider_route_status": "not_exposed_by_public_contract",
        "prompt_versions": "captured_per_case_when_response_is_valid",
        "token_usage": "captured_per_case_when_reported_by_service",
        "estimated_cost_usd": None,
        "actual_billed_cost_usd": None,
        "cost_status": "unknown_without_selected_provider_route_and_billing_data",
        "budget": {
            "authorized_limit_usd": spend_limit_usd,
            "account_level_limit_confirmed_by_operator": True,
            "account_level_limit_independently_verified": False,
            "hard_cap_enforced_by_runner": False,
            "estimated_cost_usd": None,
            "actual_billed_cost_usd": None,
            "note": "The run limit is an explicit authorization value; only an independently configured provider/account limit can constrain billing.",
        },
        "service_endpoint": endpoint,
        "request_timeout_seconds": settings.llm_service_request_timeout_seconds,
        "provider_timeout_seconds_per_generation": settings.llm_service_provider_timeout_seconds,
        "expected_provider_stages": ["extraction", "evidence_verification"],
        "observed_provider_generation_count": None,
    }


def _write_live_report(
    report: dict[str, Any],
    output_dir: Path,
    *,
    run_record: dict[str, Any],
) -> None:
    report["live_execution"] = run_record["live_execution"]
    if run_record.get("smoke_quality_gate") is not None:
        report["smoke_quality_gate"] = run_record["smoke_quality_gate"]
    _, markdown_path = write_reports(report, output_dir)
    live = run_record["live_execution"]
    lines = [
        "",
        "## Live execution metrics",
        "",
        "These counters describe the manual HTTP execution. Offline response-based metrics above retain their existing denominator semantics.",
        "",
        "| Counter | Value |",
        "|---|---:|",
    ]
    for field in (
        "selected_case_count",
        "attempted_count",
        "successful_count",
        "failed_count",
        "reused_count",
        "not_attempted_count",
        "live_execution_success_rate",
        "live_execution_success_rate_denominator",
    ):
        lines.append(f"| {field} | {live[field]} |")
    lines.extend(
        [
            "",
            f"- Failure categories (attempted cases): `{json.dumps(live['failure_categories'], sort_keys=True)}`",
            f"- Pre-request failure categories: `{json.dumps(live['pre_request_failure_categories'], sort_keys=True)}`",
            f"- HTTP status distribution (attempted cases): `{json.dumps(live['http_status_distribution'], sort_keys=True)}`",
        ]
    )
    if run_record.get("smoke_quality_gate") is not None:
        lines.extend(
            [
                "",
                "## Smoke semantic quality gate",
                "",
                f"- Technical smoke: `{run_record['technical_smoke_status']}`",
                f"- Semantic review: `{run_record['semantic_review_status']}`",
                f"- Human decision: `{run_record['smoke_quality_gate'].get('decision')}`",
            ]
        )
    markdown_path.write_text(markdown_path.read_text(encoding="utf-8") + "\n".join(lines) + "\n", encoding="utf-8")


def _authorization_parser(parser: argparse.ArgumentParser, acknowledgement: str) -> None:
    parser.add_argument("--dataset-dir", type=Path, default=DATASET_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--service-url", help="Loopback service origin; defaults to 127.0.0.1 and the configured port.")
    parser.add_argument("--max-cases", type=int)
    parser.add_argument("--spend-limit-usd", type=float)
    parser.add_argument("--confirm-account-spending-limit", action="store_true")
    parser.add_argument(acknowledgement, action="store_true")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evaluation.deepseek_runner",
        description="Offline preflight and explicitly authorized local API evaluation.",
    )
    subparsers = parser.add_subparsers(dest="command")
    preflight = subparsers.add_parser("preflight", help="network-free dataset and runtime checks")
    preflight.add_argument("--dataset-dir", type=Path, default=DATASET_DIR)
    preflight.add_argument("--service-url", help="Loopback service origin; no request is sent.")
    review = subparsers.add_parser(
        "verify-smoke-review", help="offline validation of the saved case-001 human quality review"
    )
    review.add_argument("--dataset-dir", type=Path, default=DATASET_DIR)
    review.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    smoke = subparsers.add_parser("smoke", help="case-001 only; separate smoke authorization required")
    _authorization_parser(smoke, "--authorize-smoke")
    development = subparsers.add_parser(
        "development", help="development split only; separate authorization required"
    )
    _authorization_parser(development, "--authorize-development")
    development.add_argument("--case", dest="case_ids", action="append")
    holdout = subparsers.add_parser(
        "holdout", help="holdout split only; separate authorization required"
    )
    _authorization_parser(holdout, "--authorize-holdout")
    holdout.add_argument("--case", dest="case_ids", action="append")
    return parser


def run_cli(
    argv: list[str] | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        argv = ["preflight"]
    args = _parser().parse_args(argv)
    if args.command is None:
        args.command = "preflight"

    if args.command == "preflight":
        dataset, settings, endpoint, issues = _load_preflight(
            args.dataset_dir, args.service_url
        )
        return _print_preflight(dataset, settings, endpoint, issues)

    if args.command == "verify-smoke-review":
        dataset = load_dataset(args.dataset_dir)
        if not dataset.valid:
            print("Smoke review verification failed: dataset is invalid.", file=sys.stderr)
            return 2
        try:
            paths = _output_paths(args.output_dir, dataset.root, "development")
            gate = _smoke_quality_gate(dataset, paths)
        except SmokeReviewGateError as error:
            print(f"Smoke quality gate: {error.status}: {error}", file=sys.stderr)
            return 1 if error.status == "semantic_review_failed" else 3
        except RunnerError as error:
            print(f"Smoke review verification rejected: {error}", file=sys.stderr)
            return 2
        print(f"Smoke quality gate: {gate['status']} (reviewer: {gate['reviewer']}).")
        return 0

    try:
        _authorize(args)
    except RunnerError as error:
        print(f"DeepSeek runner authorization rejected: {error}", file=sys.stderr)
        return 3

    dataset, settings, endpoint, issues = _load_preflight(
        args.dataset_dir, args.service_url
    )
    if issues or settings is None or endpoint is None:
        print("DeepSeek runner preflight failed; no request was sent.", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 2
    try:
        cases = _select_cases(dataset, args)
        paths = _output_paths(args.output_dir, dataset.root, args.command)
        conflicts = _prepare_output(
            paths, dataset, cases, settings, endpoint, args.command
        )
        if conflicts:
            raise RunnerError(" ".join(conflicts))
    except RunnerError as error:
        print(f"DeepSeek runner rejected input: {error}", file=sys.stderr)
        return 2

    smoke_quality_gate: dict[str, Any] | None = None
    if args.command == "development":
        try:
            smoke_quality_gate = _smoke_quality_gate(dataset, paths)
        except SmokeReviewGateError as error:
            print(f"Development blocked: {error.status}: {error}", file=sys.stderr)
            return 3

    try:
        results, reused_case_ids = asyncio.run(
            _execute(
                cases=cases,
                dataset=dataset,
                settings=settings,
                endpoint=endpoint,
                paths=paths,
                mode=args.command,
                spend_limit_usd=args.spend_limit_usd,
                transport=transport,
            )
        )
        successful_case_ids = [
            result["case_id"]
            for result in results
            if result["status"] in {"success", "reused"}
        ]
        _create_review_template(paths["review_template"], successful_case_ids)
        if args.command == "smoke" and "case-001" in successful_case_ids:
            smoke_case_metadata = json.loads(
                (paths["metadata"] / "case-001.json").read_text(encoding="utf-8")
            )
            _create_smoke_approval_template(
                paths["smoke_approval"],
                response_sha256=smoke_case_metadata["response_sha256"],
            )
        record = _run_record(
            mode=args.command,
            dataset=dataset,
            settings=settings,
            endpoint=endpoint,
            cases=cases,
            results=results,
            reused_case_ids=reused_case_ids,
            case_limit=args.max_cases,
            spend_limit_usd=args.spend_limit_usd,
            smoke_quality_gate=smoke_quality_gate,
        )
        _write_json_exclusive(paths["run_metadata"], record)
        report = evaluate_offline(
            dataset,
            responses_dir=paths["responses"],
            split="holdout" if args.command == "holdout" else "development",
            case_ids=[case.case_id for case in cases],
        )
        _write_live_report(report, paths["reports"], run_record=record)
    except RunnerError as error:
        print(f"DeepSeek runner stopped: {error}", file=sys.stderr)
        return 2
    except OSError:
        print("DeepSeek runner could not persist output; inspect the output directory.", file=sys.stderr)
        return 2

    print(f"DeepSeek {args.command} run finished: {len(successful_case_ids)} response(s) available.")
    print(f"Operational record: {paths['run_metadata']}")
    print(f"Offline report: {paths['reports'] / 'report.json'} and {paths['reports'] / 'report.md'}")
    return 0 if all(result["status"] in {"success", "reused"} for result in results) else 1


def main() -> None:
    raise SystemExit(run_cli())


if __name__ == "__main__":
    main()
