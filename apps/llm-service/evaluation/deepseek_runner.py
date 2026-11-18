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


class RunnerError(ValueError):
    """A sanitized preflight, authorization, or output-safety error."""


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
    else:
        if not args.authorize_development:
            raise RunnerError(
                "Development mode requires separate --authorize-development approval."
            )
        if args.max_cases is None or not 1 <= args.max_cases <= 10:
            raise RunnerError("Development mode requires --max-cases between 1 and 10.")
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
    if args.command == "smoke":
        case_ids = ["case-001"]
    elif args.case_ids:
        if len(args.case_ids) != len(set(args.case_ids)):
            raise RunnerError("Development case IDs must not be repeated.")
        case_ids = list(args.case_ids)
    else:
        case_ids = list(DEVELOPMENT_CASE_IDS[: args.max_cases])

    cases: list[DatasetCase] = []
    for case_id in case_ids:
        case = dataset.case(case_id)
        if case is None:
            raise RunnerError(f"Unknown development case ID: {case_id}.")
        if case_id not in DEVELOPMENT_CASE_IDS or case.split != "development":
            raise RunnerError(f"Live evaluation is forbidden for non-development case {case_id}.")
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
    for fixed_path in (
        paths["run_metadata"],
        paths["review_template"],
        paths["reports"] / "report.json",
        paths["reports"] / "report.md",
    ):
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
            or not isinstance(smoke_case_metadata, dict)
            or smoke_case_metadata.get("mode") != "smoke"
            or smoke_case_metadata.get("status") != "success"
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
        "attempt_count": 1,
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
    if case.split != "development" or case.case_id not in DEVELOPMENT_CASE_IDS:
        raise RunnerError(f"Live evaluation is forbidden for non-development case {case.case_id}.")

    request_path = case.case_dir / "llm-request.json"
    try:
        payload = json.loads(request_path.read_text(encoding="utf-8"))
        validated_request = ExtractionRequest.model_validate(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError):
        return {"case": case, "status": "failed", "failure_category": "request_file_invalid", "http_status": None, "latency_seconds": 0.0, "response": None}
    if not isinstance(payload, dict) or validated_request != case.request:
        return {"case": case, "status": "failed", "failure_category": "request_file_invalid", "http_status": None, "latency_seconds": 0.0, "response": None}

    started = time.perf_counter()
    try:
        response = await client.post(endpoint, json=payload)
    except httpx.TimeoutException:
        return {"case": case, "status": "failed", "failure_category": "timeout", "http_status": None, "latency_seconds": time.perf_counter() - started, "response": None}
    except httpx.RequestError:
        return {"case": case, "status": "failed", "failure_category": "connection_error", "http_status": None, "latency_seconds": time.perf_counter() - started, "response": None}
    latency = time.perf_counter() - started
    if response.status_code != 200:
        return {"case": case, "status": "failed", "failure_category": _response_failure_category(response.status_code), "http_status": response.status_code, "latency_seconds": latency, "response": None}
    try:
        body = response.json()
    except (ValueError, UnicodeError):
        return {"case": case, "status": "failed", "failure_category": "invalid_json_response", "http_status": response.status_code, "latency_seconds": latency, "response": None}
    if not isinstance(body, dict):
        return {"case": case, "status": "failed", "failure_category": "invalid_json_response", "http_status": response.status_code, "latency_seconds": latency, "response": None}

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
        return {"case": case, "status": "failed", "failure_category": category, "http_status": response.status_code, "latency_seconds": latency, "response": None}

    return {"case": case, "status": "success", "failure_category": None, "http_status": response.status_code, "latency_seconds": latency, "response": body, "validation": validation}


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
    attempted = 0
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
            if case.split != "development" or case.case_id not in DEVELOPMENT_CASE_IDS:
                raise RunnerError(f"Live evaluation is forbidden for non-development case {case.case_id}.")
            if attempted >= len(cases):
                break

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
                        "attempt_count": 0,
                        "latency_seconds": None,
                        "failure_category": None,
                    }
                )
                continue

            if attempted >= 10:
                raise RunnerError("Development request count exceeded the hard case-count maximum of 10.")
            attempted += 1
            result = await _send_one(
                client,
                case=case,
                settings=settings,
                endpoint=endpoint,
                mode=mode,
            )
            if result["status"] == "success":
                _write_json_exclusive(response_path, result["response"])
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
                )
                _write_json_exclusive(paths["metadata"] / f"{case.case_id}.json", metadata)
                results.append(
                    {
                        "case_id": case.case_id,
                        "split": case.split,
                        "status": "success",
                        "http_status": result["http_status"],
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
                "failure_category": result["failure_category"],
                "http_status": result["http_status"],
                "attempt_count": 1,
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
                status="failed",
                http_status=result["http_status"],
                latency_seconds=result["latency_seconds"],
                response=None,
                failure_category=result["failure_category"],
            )
            _write_json_exclusive(paths["metadata"] / f"{case.case_id}.json", metadata)
            results.append(
                {
                    "case_id": case.case_id,
                    "split": case.split,
                    "status": "failed",
                    "http_status": result["http_status"],
                    "attempt_count": 1,
                    "latency_seconds": round(result["latency_seconds"], 6),
                    "failure_category": result["failure_category"],
                }
            )
            # A failed request may still have incurred provider cost; stop the run.
            break

    return results, reused_case_ids


def _create_review_template(path: Path, case_ids: list[str]) -> None:
    _write_json_exclusive(path, {"cases": {case_id: {} for case_id in case_ids}})


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
) -> dict[str, Any]:
    return {
        "schema_version": "llm03.7.2-run-v1",
        "mode": mode,
        "run_status": "success" if results and all(result["status"] in {"success", "reused"} for result in results) else "failed",
        "recorded_at": _now(),
        "dataset_id": dataset.manifest.get("dataset_id"),
        "dataset_version": dataset.manifest.get("dataset_version"),
        "split": "development",
        "selected_case_ids": [case.case_id for case in cases],
        "case_limit": case_limit,
        "reused_case_ids": reused_case_ids,
        "case_results": results,
        "attempt_count": sum(result["attempt_count"] for result in results),
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
    smoke = subparsers.add_parser("smoke", help="case-001 only; separate smoke authorization required")
    _authorization_parser(smoke, "--authorize-smoke")
    development = subparsers.add_parser(
        "development", help="development split only; separate authorization required"
    )
    _authorization_parser(development, "--authorize-development")
    development.add_argument("--case", dest="case_ids", action="append")
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
        )
        _write_json_exclusive(paths["run_metadata"], record)
        report = evaluate_offline(
            dataset,
            responses_dir=paths["responses"],
            split="development",
            case_ids=[case.case_id for case in cases],
        )
        write_reports(report, paths["reports"])
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
