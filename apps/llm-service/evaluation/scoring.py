"""Deterministic counts and attribute scoring; semantic judgments stay human-led."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from evaluation.matching import MatchResult
from evaluation.validation import normalize_exact_text, normalize_raw_expression


@dataclass(frozen=True)
class Accuracy:
    correct: int
    denominator: int
    value: float | None
    status: str


@dataclass(frozen=True)
class OwnerMetrics:
    accuracy: float | None
    denominator: int
    correct_null_rate: float | None
    null_denominator: int
    unsupported_count: int
    wrong_owner_count: int


@dataclass(frozen=True)
class DeadlineMetrics:
    raw_expression_accuracy: float | None
    raw_denominator: int
    resolved_date_accuracy: float | None
    date_denominator: int
    temporal_status_accuracy: float | None
    status_denominator: int
    fabricated_count: int
    correct_null_rate: float | None
    null_denominator: int


@dataclass(frozen=True)
class PriorityMetrics:
    explicit_accuracy: float | None
    denominator: int
    correct_null_rate: float | None
    null_denominator: int
    fabricated_count: int


@dataclass(frozen=True)
class ActionEvaluation:
    status: str
    tp: int
    fp: int
    fn: int
    predicted_count: int
    expected_count: int
    precision: float | None
    recall: float | None
    f1: float | None
    correct_empty: bool | None
    matching: dict[str, Any]
    owner: OwnerMetrics
    deadline: DeadlineMetrics
    priority: PriorityMetrics

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _resolution_status(item: Any) -> str | None:
    return _value(_value(item, "due_date_resolution"), "status")


def _ratio(correct: int, denominator: int) -> float | None:
    return correct / denominator if denominator else None


def _owner_is_supported(owner: str | None, action: Any, request: Any, segments: dict[str, Any]) -> bool:
    if owner is None:
        return True
    source_ids = set(_value(action, "source_segment_ids", []) or [])
    for participant in getattr(getattr(request, "meeting", None), "participants", ()):
        if normalize_exact_text(participant.display_name) == normalize_exact_text(owner) and source_ids:
            if set(participant.speaker_ids) & {segments[source_id].speaker_id for source_id in source_ids if source_id in segments}:
                return True
    owner_key = normalize_exact_text(owner)
    for source_id in source_ids:
        segment = segments.get(source_id)
        if segment and owner_key and owner_key in normalize_exact_text(segment.text):
            return True
    return False


def evaluate_actions(
    gold_actions: Iterable[Any],
    predictions: Iterable[Any],
    *,
    transcript_segments: Iterable[Any],
    matching: MatchResult | None = None,
    request: Any = None,
) -> ActionEvaluation:
    gold = list(gold_actions)
    predicted = list(predictions)
    segment_map = {segment.id: segment for segment in transcript_segments}
    if matching is None:
        from evaluation.matching import match_actions

        matching = match_actions(predicted, gold)
    pred_by_id = {_value(item, "id"): item for item in predicted}
    gold_by_id = {_value(item, "gold_id"): item for item in gold}
    tp = len(matching.pairs)
    fp = len(matching.unmatched_prediction_ids)
    fn = len(matching.unmatched_gold_ids)
    complete = matching.status == "complete"
    precision = _ratio(tp, tp + fp) if complete else None
    recall = _ratio(tp, tp + fn) if complete else None
    f1_denominator = 2 * tp + fp + fn
    f1 = 2 * tp / f1_denominator if complete and f1_denominator else None
    correct_empty = not gold and not predicted if complete else None

    owner_correct = owner_denominator = owner_null_correct = owner_null_denominator = 0
    unsupported = wrong_owner = 0
    raw_correct = raw_denominator = date_correct = date_denominator = status_correct = status_denominator = 0
    deadline_fabricated = null_deadline_correct = null_deadline_denominator = 0
    priority_correct = priority_denominator = null_priority_correct = null_priority_denominator = priority_fabricated = 0
    for pred_id, gold_id in matching.pairs:
        pred = pred_by_id[pred_id]
        expected = gold_by_id[gold_id]
        pred_owner, gold_owner = _value(pred, "owner"), _value(expected, "owner")
        owner_denominator += 1
        if normalize_exact_text(pred_owner) == normalize_exact_text(gold_owner):
            owner_correct += 1
        else:
            wrong_owner += 1
        if gold_owner is None:
            owner_null_denominator += 1
            if pred_owner is None:
                owner_null_correct += 1
        if pred_owner is not None and not _owner_is_supported(pred_owner, pred, request, segment_map):
            unsupported += 1

        pred_raw = _value(pred, "raw_due_expression")
        gold_raw = _value(expected, "raw_due_expression")
        pred_date = _value(pred, "due_date")
        gold_date = _value(expected, "due_date")
        pred_status = _resolution_status(pred)
        gold_status = _value(expected, "due_date_resolution_status")
        raw_denominator += 1
        if normalize_raw_expression(pred_raw) == normalize_raw_expression(gold_raw):
            raw_correct += 1
        if gold_date is not None or pred_date is not None:
            date_denominator += 1
            if str(pred_date) == str(gold_date):
                date_correct += 1
        if gold_raw is not None or pred_raw is not None:
            status_denominator += 1
            if pred_status == gold_status:
                status_correct += 1
        if (gold_raw is None and (pred_raw is not None or pred_date is not None)) or (gold_date is None and pred_date is not None):
            deadline_fabricated += 1
        if gold_raw is None:
            null_deadline_denominator += 1
            if pred_raw is None and pred_date is None:
                null_deadline_correct += 1

        pred_priority, gold_priority = _value(pred, "priority"), _value(expected, "priority")
        priority_denominator += 1
        if pred_priority == gold_priority:
            priority_correct += 1
        if gold_priority is None and pred_priority is not None:
            priority_fabricated += 1
        if gold_priority is None:
            null_priority_denominator += 1
            if pred_priority is None:
                null_priority_correct += 1

    matching_dict = {
        "status": matching.status,
        "pairs": [list(pair) for pair in matching.pairs],
        "unmatched_prediction_ids": list(matching.unmatched_prediction_ids),
        "unmatched_gold_ids": list(matching.unmatched_gold_ids),
        "ambiguous_prediction_ids": list(matching.ambiguous_prediction_ids),
        "ambiguous_gold_ids": list(matching.ambiguous_gold_ids),
        "decisions": list(matching.decisions),
        "issues": list(matching.issues),
    }
    return ActionEvaluation(
        status="needs_manual_review" if not complete else "complete",
        tp=tp,
        fp=fp,
        fn=fn,
        predicted_count=len(predicted),
        expected_count=len(gold),
        precision=precision,
        recall=recall,
        f1=f1,
        correct_empty=correct_empty,
        matching=matching_dict,
        owner=OwnerMetrics(_ratio(owner_correct, owner_denominator), owner_denominator, _ratio(owner_null_correct, owner_null_denominator), owner_null_denominator, unsupported, wrong_owner),
        deadline=DeadlineMetrics(_ratio(raw_correct, raw_denominator), raw_denominator, _ratio(date_correct, date_denominator), date_denominator, _ratio(status_correct, status_denominator), status_denominator, deadline_fabricated, _ratio(null_deadline_correct, null_deadline_denominator), null_deadline_denominator),
        priority=PriorityMetrics(_ratio(priority_correct, priority_denominator), priority_denominator, _ratio(null_priority_correct, null_priority_denominator), null_priority_denominator, priority_fabricated),
    )


SUMMARY_SCORE_FIELDS = {
    "faithfulness": (1, 5),
    "required_fact_coverage": (0, 1),
    "conciseness_actionability": (1, 5),
    "semantic_source_grounding": (0, 1),
}


def validate_summary_review(review: Any) -> dict[str, Any]:
    if review is None:
        return {"status": "pending_review", **{field: None for field in SUMMARY_SCORE_FIELDS}, "hallucination_count": None, "reviewer": None, "reviewer_scores": [], "adjudication": None}
    if not isinstance(review, dict):
        raise ValueError("Summary review must be an object.")
    if any(not isinstance(field, str) for field in review):
        raise ValueError("Summary review field names must be strings.")
    allowed_fields = set(SUMMARY_SCORE_FIELDS) | {
        "hallucination_count", "hallucinations", "reviewer", "reviewer_scores", "adjudication"
    }
    unknown_fields = set(review) - allowed_fields
    if unknown_fields:
        raise ValueError(f"Summary review has unknown field(s): {', '.join(sorted(unknown_fields))}.")
    cleaned: dict[str, Any] = {}
    for field, (minimum, maximum) in SUMMARY_SCORE_FIELDS.items():
        value = review.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not minimum <= value <= maximum:
            raise ValueError(f"Summary review {field} must be in range {minimum}..{maximum}.")
        cleaned[field] = value
    count = review.get("hallucination_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("Summary review hallucination_count must be a non-negative integer.")
    reviewer = review.get("reviewer")
    if not _valid_reviewer(reviewer):
        raise ValueError("Summary review requires a reviewer name or ID.")
    annotations = review.get("hallucinations", [])
    if not isinstance(annotations, list) or any(not isinstance(item, str) or not item.strip() for item in annotations):
        raise ValueError("Summary hallucinations must be an array of non-empty annotations.")
    if annotations and count < len(annotations):
        raise ValueError("hallucination_count cannot be smaller than its listed annotations.")
    scores = review.get("reviewer_scores", [])
    if not isinstance(scores, list):
        raise ValueError("reviewer_scores must be an array.")
    for score in scores:
        if not isinstance(score, dict):
            raise ValueError("Each reviewer score must be an object.")
        if any(not isinstance(field, str) for field in score):
            raise ValueError("Reviewer score field names must be strings.")
        reviewer_score_fields = set(SUMMARY_SCORE_FIELDS) | {"hallucination_count", "hallucinations", "reviewer"}
        if set(score) - reviewer_score_fields:
            raise ValueError("Reviewer score has unknown field(s).")
        # Each independent reviewer record uses the same validated score shape.
        validate_summary_review({**score, "reviewer_scores": []})
    adjudication = review.get("adjudication")
    if adjudication is not None and (not isinstance(adjudication, dict) or not _valid_reviewer(adjudication.get("reviewer"))):
        raise ValueError("adjudication must include a reviewer name or ID.")
    if isinstance(adjudication, dict):
        if any(not isinstance(field, str) for field in adjudication):
            raise ValueError("Adjudication field names must be strings.")
        if set(adjudication) - {"reviewer", "reason", "scores"}:
            raise ValueError("adjudication has unknown field(s).")
        reason = adjudication.get("reason")
        if reason is not None and (not isinstance(reason, str) or not reason.strip()):
            raise ValueError("adjudication reason must be non-empty text when supplied.")
    if isinstance(adjudication, dict) and adjudication.get("scores") is not None:
        if not isinstance(adjudication["scores"], dict):
            raise ValueError("adjudication scores must be an object.")
        if any(not isinstance(field, str) for field in adjudication["scores"]):
            raise ValueError("Adjudication score field names must be strings.")
        validate_summary_review({**adjudication["scores"], "reviewer": adjudication["reviewer"], "hallucination_count": adjudication["scores"].get("hallucination_count", count), "reviewer_scores": []})
    return {"status": "reviewed", **cleaned, "hallucination_count": count, "hallucinations": annotations, "reviewer": reviewer.strip(), "reviewer_scores": scores, "adjudication": adjudication}


def _valid_reviewer(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not any(ord(char) < 32 for char in value)


def reviewable_claim_ids(response: Any) -> tuple[str, ...]:
    """Return stable semantic-review IDs for claims in a saved public response.

    Indexes are assigned from the public response arrays, after any internal
    source/evidence filtering performed by the extraction pipeline.
    """
    modules = getattr(response, "modules", None)
    if modules is None and isinstance(response, dict):
        modules = response.get("modules")

    def value(item: Any, key: str) -> Any:
        if isinstance(item, dict):
            return item.get(key)
        return getattr(item, key, None)

    claims: list[str] = []
    summary = value(modules, "meeting_summary")
    if summary is not None:
        if value(summary, "overview") is not None:
            claims.append("summary.overview")
        topics = value(summary, "key_topics") or []
        for index, topic in enumerate(topics):
            if value(topic, "topic") is not None and value(topic, "brief_discussion") is not None:
                claims.append(f"summary.key_topics[{index}]")

    actions = value(modules, "action_items")
    if actions is not None:
        if not actions:
            # The production SourceValidator explicitly verifies this absence claim.
            claims.append("actions.absence")
        else:
            for index, action in enumerate(actions):
                if value(action, "task") is not None:
                    claims.append(f"actions[{index}].task")
                for field in ("owner", "raw_due_expression", "priority", "context"):
                    if value(action, field) is not None:
                        claims.append(f"actions[{index}].{field}")
    return tuple(claims)


def validate_semantic_grounding_review(
    annotations: Any,
    *,
    expected_claim_ids: Iterable[str],
) -> dict[str, Any]:
    expected = tuple(expected_claim_ids)
    if any(not isinstance(claim_id, str) or not claim_id.strip() for claim_id in expected):
        raise ValueError("Expected semantic claim IDs must be non-empty strings.")
    if len(expected) != len(set(expected)):
        raise ValueError("Expected semantic claim IDs must be unique.")
    expected_set = set(expected)

    def result_for(
        status: str,
        *,
        reviewed_ids: set[str] | None = None,
        supported: int | None = None,
        unsupported: int | None = None,
        reviewer: str | None = None,
        claims: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        reviewed_ids = reviewed_ids or set()
        reviewed_count = len(reviewed_ids)
        pending_count = len(expected_set - reviewed_ids)
        denominator = reviewed_count
        provisional_accuracy = supported / denominator if supported is not None and denominator else None
        complete = status == "reviewed" and pending_count == 0
        return {
            "status": status,
            "supported": supported,
            "unsupported": unsupported,
            "denominator": denominator,
            "expected_claim_count": len(expected),
            "reviewed_claim_count": reviewed_count,
            "pending_claim_count": pending_count,
            "review_coverage": reviewed_count / len(expected) if expected else None,
            "accuracy": provisional_accuracy if complete and expected else None,
            "provisional_accuracy": provisional_accuracy if not complete else None,
            "reviewer": reviewer,
            "claims": claims or [],
        }

    if annotations is None:
        return result_for("pending_review")
    if not isinstance(annotations, dict) or set(annotations) != {"reviewer", "claims"} or not _valid_reviewer(annotations.get("reviewer")):
        raise ValueError("Semantic grounding review requires a reviewer and annotations.")
    claims = annotations.get("claims")
    if not isinstance(claims, list):
        raise ValueError("Semantic grounding review claims must be an array.")
    supported = unsupported = 0
    claim_ids: set[str] = set()
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != {"claim_id", "verdict"} or claim.get("verdict") not in ("supported", "unsupported") or not isinstance(claim.get("claim_id"), str) or not claim["claim_id"].strip():
            raise ValueError("Each semantic grounding claim needs claim_id and supported/unsupported verdict.")
        if claim["claim_id"] in claim_ids:
            raise ValueError("Semantic grounding claim_id values must be unique.")
        if claim["claim_id"] not in expected_set:
            raise ValueError(f"Semantic grounding claim {claim['claim_id']!r} does not exist in this public response.")
        claim_ids.add(claim["claim_id"])
        if claim["verdict"] == "supported":
            supported += 1
        else:
            unsupported += 1
    status = "pending_review" if not claim_ids else "reviewed" if claim_ids == expected_set else "partial_review"
    return result_for(
        status,
        reviewed_ids=claim_ids,
        supported=supported if claim_ids else None,
        unsupported=unsupported if claim_ids else None,
        reviewer=annotations["reviewer"].strip(),
        claims=claims,
    )

