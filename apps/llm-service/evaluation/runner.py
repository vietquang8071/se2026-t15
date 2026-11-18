"""CLI for deterministic offline evaluation; live execution is fail-closed."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluation.loader import DATASET_DIR, DatasetCase, DatasetLoadResult, load_dataset
from evaluation.matching import match_actions
from evaluation.reporting import write_reports
from evaluation.scoring import (
    evaluate_actions,
    reviewable_claim_ids,
    validate_semantic_grounding_review,
    validate_summary_review,
)
from evaluation.validation import ResponseValidation, validate_response


class LiveAuthorizationError(ValueError):
    """Live mode was not explicitly authorized or cannot be safely budgeted."""


def _load_review_file(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read review annotations: {error}") from error
    if not isinstance(raw, dict):
        raise ValueError("Review file must contain a JSON object.")
    if "cases" in raw:
        if set(raw) != {"cases"}:
            raise ValueError("Review file with a cases field must contain no other top-level fields.")
        cases = raw["cases"]
    else:
        cases = raw
    if not isinstance(cases, dict):
        raise ValueError("Review annotations must map case IDs to review objects.")
    if any(not isinstance(case_id, str) or not case_id.strip() for case_id in cases):
        raise ValueError("Review case IDs must be non-empty strings.")
    return cases


def _read_response(path: Path, case: DatasetCase) -> tuple[ResponseValidation | None, str | None]:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return None, f"Could not read response file: {error}"
    result = validate_response(case.request, raw)
    return result, None


def _action_review(case_reviews: dict[str, Any]) -> tuple[list[dict[str, Any]], Any]:
    if not isinstance(case_reviews, dict):
        raise ValueError("Each case review must be an object.")
    decisions = case_reviews.get("action_matches", [])
    if not isinstance(decisions, list):
        raise ValueError("action_matches must be an array.")
    if any(not isinstance(decision, dict) for decision in decisions):
        raise ValueError("Each action match decision must be an object.")
    return decisions, case_reviews.get("summary_review")


def _validate_case_review(
    case: DatasetCase,
    case_reviews: Any,
    response: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    if not isinstance(case_reviews, dict):
        raise ValueError(f"Review for {case.case_id} must be an object.")
    if any(not isinstance(field, str) for field in case_reviews):
        raise ValueError(f"Review field names for {case.case_id} must be strings.")
    allowed_fields = {"action_matches", "summary_review", "semantic_grounding"}
    unknown_fields = set(case_reviews) - allowed_fields
    if unknown_fields:
        raise ValueError(f"Review for {case.case_id} has unknown fields: {', '.join(sorted(unknown_fields))}.")
    decisions, raw_summary_review = _action_review(case_reviews)
    expected_decision_fields = {"prediction_id", "gold_id", "decision", "reviewer"}
    prediction_ids = {
        action.id for action in (response.modules.action_items or [])
    } if response is not None and response.modules.action_items is not None else set()
    gold_ids = {action["gold_id"] for action in case.gold["action_items"]}
    seen_pairs: set[tuple[str, str]] = set()
    matched_predictions: set[str] = set()
    matched_gold: set[str] = set()
    for decision in decisions:
        if set(decision) != expected_decision_fields:
            raise ValueError(f"Each action match decision for {case.case_id} needs prediction_id, gold_id, decision, and reviewer only.")
        prediction_id, gold_id = decision.get("prediction_id"), decision.get("gold_id")
        outcome, reviewer = decision.get("decision"), decision.get("reviewer")
        if not isinstance(prediction_id, str) or not prediction_id.strip() or prediction_id not in prediction_ids:
            raise ValueError(f"Action match for {case.case_id} references a missing prediction action.")
        if not isinstance(gold_id, str) or not gold_id.strip() or gold_id not in gold_ids:
            raise ValueError(f"Action match for {case.case_id} references a missing gold action.")
        if outcome not in ("match", "not_match"):
            raise ValueError(f"Action match for {case.case_id} has an invalid decision value.")
        if not isinstance(reviewer, str) or not reviewer.strip() or any(ord(char) < 32 for char in reviewer):
            raise ValueError(f"Action match for {case.case_id} needs valid reviewer metadata.")
        pair = (prediction_id, gold_id)
        if pair in seen_pairs:
            raise ValueError(f"Duplicate or conflicting action match decision for {case.case_id}.")
        seen_pairs.add(pair)
        if outcome == "match":
            if prediction_id in matched_predictions or gold_id in matched_gold:
                raise ValueError(f"Action matches for {case.case_id} conflict with one-to-one matching.")
            matched_predictions.add(prediction_id)
            matched_gold.add(gold_id)

    raw_semantic_review = case_reviews.get("semantic_grounding")
    if response is None:
        if decisions or raw_summary_review is not None or raw_semantic_review is not None:
            raise ValueError(f"Review annotations for {case.case_id} cannot be checked without a valid saved response.")
        summary_review = validate_summary_review(None)
        semantic_review = validate_semantic_grounding_review(None, expected_claim_ids=())
        return decisions, summary_review, semantic_review

    summary_review = validate_summary_review(raw_summary_review)
    semantic_review = validate_semantic_grounding_review(
        raw_semantic_review,
        expected_claim_ids=reviewable_claim_ids(response),
    )
    return decisions, summary_review, semantic_review


def evaluate_offline(
    dataset: DatasetLoadResult,
    *,
    responses_dir: str | Path | None = None,
    split: str | None = None,
    case_ids: list[str] | None = None,
    reviews: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if split not in (None, "development", "holdout"):
        raise ValueError("split must be development or holdout.")
    selected = [case for case in dataset.cases if (split is None or case.split == split) and (case_ids is None or case.case_id in case_ids)]
    if case_ids is not None:
        missing = sorted(set(case_ids) - {case.case_id for case in dataset.cases})
        if missing:
            raise ValueError(f"Unknown case ID(s): {', '.join(missing)}")
        outside_split = sorted(case_id for case_id in set(case_ids) if split and dataset.case(case_id) and dataset.case(case_id).split != split)
        if outside_split:
            raise ValueError(f"Case ID(s) are not in requested {split} split: {', '.join(outside_split)}")
    review_by_case = {} if reviews is None else reviews
    if not isinstance(review_by_case, dict):
        raise ValueError("Review annotations must map case IDs to review objects.")
    if any(not isinstance(case_id, str) or not case_id.strip() for case_id in review_by_case):
        raise ValueError("Review case IDs must be non-empty strings.")
    known_case_ids = {case.case_id for case in dataset.cases}
    unknown_review_cases = sorted(set(review_by_case) - known_case_ids)
    if unknown_review_cases:
        raise ValueError(f"Review file contains unknown case ID(s): {', '.join(unknown_review_cases)}.")
    for review_case_id, review_value in review_by_case.items():
        if not isinstance(review_value, dict):
            raise ValueError(f"Review for {review_case_id} must be an object.")
        if any(not isinstance(field, str) for field in review_value):
            raise ValueError(f"Review field names for {review_case_id} must be strings.")
        unknown_fields = set(review_value) - {"action_matches", "summary_review", "semantic_grounding"}
        if unknown_fields:
            raise ValueError(f"Review for {review_case_id} has unknown fields: {', '.join(sorted(unknown_fields))}.")
        if "action_matches" in review_value and not isinstance(review_value["action_matches"], list):
            raise ValueError(f"action_matches for {review_case_id} must be an array.")
    response_root = Path(responses_dir) if responses_dir is not None else None
    validated_reviews: dict[str, tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]] = {}
    for review_case_id, case_review in review_by_case.items():
        reviewed_case = dataset.case(review_case_id)
        if reviewed_case is None:
            continue
        review_response = None
        review_response_path = response_root / f"{review_case_id}.json" if response_root else None
        if review_response_path is not None and review_response_path.is_file():
            validation, _ = _read_response(review_response_path, reviewed_case)
            if validation is not None and validation.semantic_evaluation_available:
                review_response = validation.response
        validated_reviews[review_case_id] = _validate_case_review(reviewed_case, case_review, review_response)
    report_cases: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    latencies: list[float] = []
    model_provider: set[tuple[str, str]] = set()
    input_tokens = output_tokens = 0
    token_usage_cases = 0
    contract_valid = completed_count = response_count = structural_count = structural_valid = 0
    action_scores: list[dict[str, Any]] = []
    summary_values: dict[str, list[float]] = {"faithfulness": [], "required_fact_coverage": [], "conciseness_actionability": [], "semantic_source_grounding": []}
    summary_hallucinations = 0
    summary_reviewed = summary_pending = correct_empty_cases = 0
    semantic_case_reviews: list[dict[str, Any]] = []
    for case in selected:
        response_path = response_root / f"{case.case_id}.json" if response_root else None
        if response_path is None or not response_path.is_file():
            report_cases.append({"case_id": case.case_id, "split": case.split, "scenario": case.scenario, "status": "not_evaluated", "failure_category": None, "action_items": None, "summary_review": {"status": "not_evaluated"}, "semantic_grounding": {"status": "not_evaluated"}, "expected_behavior": "A saved response is required for scoring.", "actual_behavior": "No response file was provided.", "evaluation_uncertainty": []})
            continue
        response_count += 1
        validation, read_error = _read_response(response_path, case)
        if validation is None:
            case_record = {"case_id": case.case_id, "split": case.split, "scenario": case.scenario, "status": "failed", "failure_category": "response_file_invalid", "validation": {"json_valid": False, "schema_valid": False, "relationship_valid": None, "completed": False, "semantic_evaluation_available": False, "errors": [read_error]}, "action_items": None}
        else:
            case_record = {
                "case_id": case.case_id,
                "split": case.split,
                "scenario": case.scenario,
                "status": "evaluated" if validation.semantic_evaluation_available else "failed",
                "failure_category": validation.failure_category,
                "validation": {
                    "json_valid": validation.json_valid,
                    "schema_valid": validation.schema_valid,
                    "relationship_valid": validation.relationship_valid,
                    "completed": validation.completed,
                    "semantic_evaluation_available": validation.semantic_evaluation_available,
                    "structural_grounding_valid": validation.structural_grounding_valid,
                    "semantic_grounding_status": validation.semantic_grounding_status,
                    "errors": list(validation.errors),
                },
                "action_items": None,
            }
        case_review = review_by_case.get(case.case_id, {})
        response = validation.response if validation is not None and validation.semantic_evaluation_available else None
        if case.case_id in validated_reviews:
            decisions, validated_summary_review, validated_semantic_review = validated_reviews[case.case_id]
        else:
            decisions, validated_summary_review, validated_semantic_review = _validate_case_review(case, case_review, response)
        if validation is not None:
            if validation.schema_valid:
                contract_valid += int(validation.relationship_valid is True)
            if validation.completed and validation.relationship_valid:
                completed_count += 1
            if validation.structural_grounding_valid is not None:
                structural_count += 1
                structural_valid += int(validation.structural_grounding_valid)
            if response is not None:
                metadata = response.processing
                model_provider.add((metadata.provider, metadata.model_id))
                latency = (metadata.completed_at - metadata.started_at).total_seconds()
                latencies.append(latency)
                if metadata.token_usage is not None:
                    input_tokens += metadata.token_usage.input_tokens
                    output_tokens += metadata.token_usage.output_tokens
                    token_usage_cases += 1
                case_record["operational"] = {
                    "provider": metadata.provider,
                    "model_id": metadata.model_id,
                    "prompt_version": metadata.prompt_version,
                    "evidence_prompt_version": metadata.evidence_prompt_version,
                    "started_at": metadata.started_at.isoformat(),
                    "completed_at": metadata.completed_at.isoformat(),
                    "latency_seconds": latency,
                    "token_usage": None if metadata.token_usage is None else metadata.token_usage.model_dump(mode="json"),
                    "token_usage_status": "reported" if metadata.token_usage is not None else "unavailable",
                    "http_status": None,
                    "error_category": None,
                    "attempt_count": None,
                    "estimated_cost_usd": None,
                    "actual_billed_cost_usd": None,
                    "cost_status": "unavailable_no_verified_model_price",
                }
            if validation.semantic_evaluation_available and response is not None:
                matching = match_actions(response.modules.action_items, case.gold["action_items"], decisions=decisions)
                score = evaluate_actions(
                    case.gold["action_items"], response.modules.action_items,
                    transcript_segments=case.request.transcript.segments,
                    matching=matching,
                    request=case.request,
                ).to_dict()
                case_record["action_items"] = score
                action_scores.append(score)
                summary_gold = case.gold["meeting_summary"]
                case_record["review_context"] = {
                    "predictions": {
                        "meeting_summary": None if response.modules.meeting_summary is None else {
                            "overview": response.modules.meeting_summary.overview,
                            "key_topics": [topic.model_dump(mode="json") for topic in response.modules.meeting_summary.key_topics],
                            "source_segment_ids": response.modules.meeting_summary.source_segment_ids,
                        },
                        "action_items": [
                            {"id": action.id, "task": action.task, "owner": action.owner, "raw_due_expression": action.raw_due_expression, "due_date": action.due_date.isoformat() if action.due_date else None, "due_date_resolution_status": action.due_date_resolution.status if action.due_date_resolution else None, "priority": action.priority, "source_segment_ids": action.source_segment_ids}
                            for action in (response.modules.action_items or [])
                        ],
                    },
                    "summary": {
                        "reference_overview": summary_gold["reference_overview"],
                        "key_topics": summary_gold["key_topics"],
                        "source_segment_ids": summary_gold["source_segment_ids"],
                        "forbidden_claims": summary_gold["forbidden_claims"],
                    },
                    "action_items": case.gold["action_items"],
                }
                if score["correct_empty"]:
                    correct_empty_cases += 1
                case_record["summary_review"] = validated_summary_review
                summary_review = validated_summary_review
                if summary_review["status"] == "reviewed":
                    summary_reviewed += 1
                    summary_hallucinations += summary_review["hallucination_count"]
                    for field in summary_values:
                        summary_values[field].append(float(summary_review[field]))
                else:
                    summary_pending += 1
                semantic_review = validated_semantic_review
                case_record["semantic_grounding"] = semantic_review
                semantic_case_reviews.append(semantic_review)
            elif response is not None:
                case_record["summary_review"] = {"status": "pending_review"}
                case_record["semantic_grounding"] = {"status": "pending_review"}
                summary_pending += 1
        if case_record["status"] == "failed":
            errors = case_record.get("validation", {}).get("errors", [])
            case_record["expected_behavior"] = "Completed Contract v1 response with matching request IDs and valid evidence."
            case_record["actual_behavior"] = "; ".join(errors) or "Response did not pass Contract v1 validation."
            case_record["evaluation_uncertainty"] = ["Action and Summary semantic metrics are unavailable for invalid extraction responses."]
            case_record["missing_or_invalid_references"] = [error for error in errors if "source" in error.lower() or "reference" in error.lower()]
            failures.append({key: case_record.get(key) for key in ("case_id", "failure_category", "expected_behavior", "actual_behavior", "evaluation_uncertainty", "missing_or_invalid_references")})
        elif case_record["status"] == "evaluated":
            score = case_record.get("action_items") or {}
            if score.get("status") == "needs_manual_review":
                case_record.setdefault("evaluation_uncertainty", []).append("Action match remains ambiguous pending reviewer decision.")
            if case_record.get("summary_review", {}).get("status") == "pending_review":
                case_record.setdefault("evaluation_uncertainty", []).append("Summary semantic scores are pending human review.")
        report_cases.append(case_record)

    total_cases = len(selected)
    evaluated_count = response_count
    skipped_count = total_cases - response_count
    pending_cases = sum(1 for item in report_cases if item.get("status") == "evaluated" and (item.get("summary_review", {}).get("status") != "reviewed" or (item.get("action_items") or {}).get("status") == "needs_manual_review" or item.get("semantic_grounding", {}).get("status") != "reviewed"))
    unresolved_action_cases = sum(1 for score in action_scores if score["status"] != "complete")
    tp = sum(score["tp"] for score in action_scores)
    fp = sum(score["fp"] for score in action_scores)
    fn = sum(score["fn"] for score in action_scores)
    action_metrics_complete = unresolved_action_cases == 0
    action_status = "not_evaluated" if not action_scores else ("complete" if action_metrics_complete else "needs_manual_review")
    precision = tp / (tp + fp) if action_metrics_complete and tp + fp else None
    recall = tp / (tp + fn) if action_metrics_complete and tp + fn else None
    f1_denominator = 2 * tp + fp + fn
    f1 = 2 * tp / f1_denominator if action_metrics_complete and f1_denominator else None
    owner_denominator = sum(score["owner"]["denominator"] for score in action_scores)
    owner_correct = sum(round((score["owner"]["accuracy"] or 0) * score["owner"]["denominator"]) for score in action_scores)
    owner_null_denom = sum(score["owner"]["null_denominator"] for score in action_scores)
    owner_null_correct = sum(round((score["owner"]["correct_null_rate"] or 0) * score["owner"]["null_denominator"]) for score in action_scores)
    deadline_fields = ("raw_expression_accuracy", "resolved_date_accuracy", "temporal_status_accuracy", "correct_null_rate")
    deadline_aggregate: dict[str, Any] = {}
    for metric, denominator_key in zip(deadline_fields, ("raw_denominator", "date_denominator", "status_denominator", "null_denominator")):
        denom = sum(score["deadline"][denominator_key] for score in action_scores)
        numer = sum(round((score["deadline"][metric] or 0) * score["deadline"][denominator_key]) for score in action_scores)
        deadline_aggregate[metric] = {"value": numer / denom if denom and action_metrics_complete else None, "denominator": denom, "status": "complete" if action_metrics_complete else "pending_review"}
    priority_denominator = sum(score["priority"]["denominator"] for score in action_scores)
    priority_correct = sum(round((score["priority"]["explicit_accuracy"] or 0) * score["priority"]["denominator"]) for score in action_scores)
    priority_null_denominator = sum(score["priority"]["null_denominator"] for score in action_scores)
    priority_null_correct = sum(round((score["priority"]["correct_null_rate"] or 0) * score["priority"]["null_denominator"]) for score in action_scores)
    summary_pending = sum(1 for item in report_cases if item.get("status") == "evaluated" and item.get("summary_review", {}).get("status") != "reviewed")
    report = {
        "run": {"mode": "offline", "generated_at": datetime.now(timezone.utc).isoformat(), "network_requests": 0, "live_execution": "disabled"},
        "dataset": {"dataset_id": dataset.manifest.get("dataset_id"), "dataset_version": dataset.manifest.get("dataset_version"), "split": split or "all", "case_count": total_cases, "expected_action_count": sum(len(case.gold["action_items"]) for case in selected), "evaluated_count": evaluated_count, "skipped_count": skipped_count, "pending_review_count": pending_cases},
        "metrics": {
            "contract_compliance": {"value": contract_valid / response_count if response_count else None, "numerator": contract_valid, "denominator": response_count},
            "extraction_success_rate": {"value": completed_count / response_count if response_count else None, "numerator": completed_count, "denominator": response_count},
            "actions": {"tp": tp, "fp": fp, "fn": fn, "predicted_count": sum(score["predicted_count"] for score in action_scores), "expected_count": sum(score["expected_count"] for score in action_scores), "precision": precision, "recall": recall, "f1": f1, "status": action_status, "unresolved_cases": unresolved_action_cases, "correct_empty_cases": correct_empty_cases},
            "owner": {"accuracy": owner_correct / owner_denominator if owner_denominator else None, "denominator": owner_denominator, "correct_null_rate": owner_null_correct / owner_null_denom if owner_null_denom else None, "null_denominator": owner_null_denom, "unsupported_count": sum(score["owner"]["unsupported_count"] for score in action_scores), "wrong_owner_count": sum(score["owner"]["wrong_owner_count"] for score in action_scores)},
            "deadline": {**deadline_aggregate, "raw_denominator": deadline_aggregate["raw_expression_accuracy"]["denominator"], "date_denominator": deadline_aggregate["resolved_date_accuracy"]["denominator"], "status_denominator": deadline_aggregate["temporal_status_accuracy"]["denominator"], "fabricated_count": sum(score["deadline"]["fabricated_count"] for score in action_scores)},
            "priority": {"explicit_accuracy": priority_correct / priority_denominator if priority_denominator else None, "denominator": priority_denominator, "correct_null_rate": priority_null_correct / priority_null_denominator if priority_null_denominator else None, "null_denominator": priority_null_denominator, "fabricated_count": sum(score["priority"]["fabricated_count"] for score in action_scores)},
            "structural_grounding": {"value": structural_valid / structural_count if structural_count else None, "numerator": structural_valid, "denominator": structural_count, "semantic_grounding": "reported separately through human review"},
            "semantic_grounding_review": _aggregate_semantic_reviews(semantic_case_reviews),
            "summary_review": {"status": "not_evaluated" if not action_scores else ("reviewed" if summary_pending == 0 and summary_reviewed else "pending_review"), "denominator": summary_reviewed, "pending": summary_pending, "means": {field: sum(values) / len(values) if values else None for field, values in summary_values.items()}, "hallucination_count": summary_hallucinations if summary_reviewed else None},
        },
        "operational": {"model_provider": [{"provider": provider, "model_id": model} for provider, model in sorted(model_provider)], "mean_latency_seconds": sum(latencies) / len(latencies) if latencies else None, "latency_denominator": len(latencies), "token_usage": {"input_tokens": input_tokens if token_usage_cases else None, "output_tokens": output_tokens if token_usage_cases else None, "reported_case_count": token_usage_cases, "unavailable_case_count": max(0, response_count - token_usage_cases)}, "estimated_cost_usd": None, "actual_billed_cost_usd": None, "cost_status": "unavailable_no_verified_model_price", "http_status": None, "http_status_availability": "not_applicable_offline", "http_failures": None, "attempt_count": None, "retry_policy": "offline saved-response loading; no retries"},
        "failures": failures,
        "cases": report_cases,
    }
    return report


def _validate_live_authorization(args: argparse.Namespace) -> None:
    if not args.ack_live:
        raise LiveAuthorizationError("Live mode requires explicit --ack-live acknowledgment.")
    if args.max_cases is None or args.max_cases <= 0:
        raise LiveAuthorizationError("Live mode requires an explicit positive --max-cases.")
    if args.spend_limit_usd is None or not math.isfinite(args.spend_limit_usd) or args.spend_limit_usd <= 0:
        raise LiveAuthorizationError("Live mode requires an explicit positive --spend-limit-usd.")
    raise LiveAuthorizationError("Live execution is disabled in LLM-03.7.1: provider pricing and reliable pre-request cost enforcement are not verified. No request was sent.")


def _aggregate_semantic_reviews(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    if not reviews:
        return {
            "status": "not_evaluated",
            "supported": None,
            "unsupported": None,
            "denominator": 0,
            "expected_claim_count": 0,
            "reviewed_claim_count": 0,
            "pending_claim_count": 0,
            "review_coverage": None,
            "accuracy": None,
            "provisional_accuracy": None,
            "fully_reviewed_cases": 0,
            "partial_cases": 0,
            "pending_cases": 0,
        }
    expected = sum(review["expected_claim_count"] for review in reviews)
    reviewed = sum(review["reviewed_claim_count"] for review in reviews)
    pending = sum(review["pending_claim_count"] for review in reviews)
    supported = sum(review["supported"] or 0 for review in reviews)
    unsupported = sum(review["unsupported"] or 0 for review in reviews)
    fully_reviewed = sum(review["status"] == "reviewed" for review in reviews)
    partial = sum(review["status"] == "partial_review" for review in reviews)
    pending_cases = sum(review["status"] != "reviewed" for review in reviews)
    if pending == 0 and expected > 0:
        status = "reviewed"
    elif reviewed:
        status = "partial_review"
    else:
        status = "pending_review"
    provisional_accuracy = supported / reviewed if reviewed else None
    return {
        "status": status,
        "supported": supported if reviewed else None,
        "unsupported": unsupported if reviewed else None,
        "denominator": reviewed,
        "expected_claim_count": expected,
        "reviewed_claim_count": reviewed,
        "pending_claim_count": pending,
        "review_coverage": reviewed / expected if expected else None,
        "accuracy": provisional_accuracy if status == "reviewed" else None,
        "provisional_accuracy": provisional_accuracy if status != "reviewed" else None,
        "fully_reviewed_cases": fully_reviewed,
        "partial_cases": partial,
        "pending_cases": pending_cases,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m evaluation.runner", description="LLM-03 offline evaluation tools")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-dataset", help="validate dataset files and contracts")
    validate.add_argument("--dataset-dir", type=Path, default=DATASET_DIR)
    run = subparsers.add_parser("run", help="evaluate saved ExtractionResponse JSON files offline")
    run.add_argument("--dataset-dir", type=Path, default=DATASET_DIR)
    run.add_argument("--mode", choices=("offline", "live"), default="offline")
    run.add_argument("--responses-dir", type=Path)
    run.add_argument("--split", choices=("development", "holdout"))
    run.add_argument("--case", dest="case_ids", action="append")
    run.add_argument("--reviews", type=Path)
    run.add_argument("--output-dir", type=Path, default=Path("evaluation/reports/latest"))
    run.add_argument("--ack-live", action="store_true", help="explicit live acknowledgment; live remains fail-closed")
    run.add_argument("--max-cases", type=int)
    run.add_argument("--spend-limit-usd", type=float)
    return parser


def run_cli(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "run" and args.mode == "live":
        try:
            _validate_live_authorization(args)
        except LiveAuthorizationError as error:
            print(f"evaluation runner: {error}", file=sys.stderr)
            return 3
    dataset = load_dataset(args.dataset_dir)
    if not dataset.valid:
        for issue in dataset.issues:
            location = f" {issue.path}" if issue.path else ""
            print(f"{issue.case_id}:{location}: {issue.code}: {issue.message}", file=sys.stderr)
        return 2
    if args.command == "validate-dataset":
        print(f"Dataset {dataset.manifest.get('dataset_version')} valid: {len(dataset.cases)} cases (10 development, 6 holdout).")
        return 0
    try:
        reviews = _load_review_file(args.reviews)
        report = evaluate_offline(dataset, responses_dir=args.responses_dir, split=args.split, case_ids=args.case_ids, reviews=reviews)
    except ValueError as error:
        print(f"evaluation runner: invalid evaluation input: {error}", file=sys.stderr)
        return 3
    json_path, markdown_path = write_reports(report, args.output_dir)
    print(f"Offline evaluation complete: {json_path} and {markdown_path}")
    failed = sum(case.get("status") == "failed" for case in report["cases"])
    return 1 if failed else 0


def main() -> None:
    try:
        status = run_cli()
    except (LiveAuthorizationError, ValueError) as error:
        print(f"evaluation runner: {error}", file=sys.stderr)
        status = 3
    raise SystemExit(status)


if __name__ == "__main__":
    main()

