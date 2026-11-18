"""Transparent exact matching plus explicit human decisions for paraphrases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from evaluation.validation import normalize_exact_text


@dataclass(frozen=True)
class MatchResult:
    pairs: tuple[tuple[str, str], ...]
    unmatched_prediction_ids: tuple[str, ...]
    unmatched_gold_ids: tuple[str, ...]
    ambiguous_prediction_ids: tuple[str, ...]
    ambiguous_gold_ids: tuple[str, ...]
    decisions: tuple[dict[str, str], ...]
    issues: tuple[str, ...]
    status: str


def _value(item: Any, key: str) -> Any:
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _id(item: Any, field: str) -> str | None:
    value = _value(item, field)
    return value if isinstance(value, str) and value else None


def match_actions(
    predictions: Iterable[Any],
    gold_actions: Iterable[Any],
    *,
    decisions: Iterable[dict[str, Any]] = (),
) -> MatchResult:
    predicted = list(predictions)
    gold = list(gold_actions)
    pred_ids = [_id(item, "id") for item in predicted]
    gold_ids = [_id(item, "gold_id") for item in gold]
    errors: list[str] = []
    if None in pred_ids or len(pred_ids) != len(set(pred_ids)):
        errors.append("Predicted action IDs must be present and unique for matching.")
    if None in gold_ids or len(gold_ids) != len(set(gold_ids)):
        errors.append("Gold action IDs must be present and unique for matching.")
    p_by_id = {action_id: item for action_id, item in zip(pred_ids, predicted) if action_id}
    g_by_id = {action_id: item for action_id, item in zip(gold_ids, gold) if action_id}
    pairs: list[tuple[str, str]] = []
    matched_p: set[str] = set()
    matched_g: set[str] = set()
    rejected: set[tuple[str, str]] = set()
    normalized_decisions: list[dict[str, str]] = []
    try:
        decision_list = list(decisions)
    except TypeError:
        decision_list = []
        errors.append("Manual match decisions must be an iterable of objects.")
    for decision in decision_list:
        if not isinstance(decision, dict):
            errors.append("Each manual match decision must be an object.")
            continue
        p_id = decision.get("prediction_id")
        g_id = decision.get("gold_id")
        outcome = decision.get("decision")
        reviewer = decision.get("reviewer")
        if not isinstance(p_id, str) or p_id not in p_by_id or not isinstance(g_id, str) or g_id not in g_by_id or outcome not in ("match", "not_match") or not isinstance(reviewer, str) or not reviewer.strip():
            errors.append(f"Invalid manual match decision for prediction {p_id!r} and gold {g_id!r}.")
            continue
        pair = (p_id, g_id)
        if pair in rejected or any(existing.get("prediction_id") == p_id and existing.get("gold_id") == g_id for existing in normalized_decisions):
            errors.append(f"Conflicting duplicate manual decision for {p_id!r} and {g_id!r}.")
            continue
        normalized_decisions.append({"prediction_id": p_id, "gold_id": g_id, "decision": outcome, "reviewer": reviewer.strip()})
        if outcome == "not_match":
            rejected.add(pair)
            continue
        if p_id in matched_p or g_id in matched_g:
            errors.append("Manual action matching must be one-to-one; an action was assigned more than once.")
            continue
        matched_p.add(p_id)
        matched_g.add(g_id)
        pairs.append(pair)

    p_groups: dict[str, list[str]] = {}
    g_groups: dict[str, list[str]] = {}
    for action_id, item in zip(pred_ids, predicted):
        key = normalize_exact_text(_value(item, "task"))
        if action_id and key is not None and action_id not in matched_p:
            p_groups.setdefault(key, []).append(action_id)
    for action_id, item in zip(gold_ids, gold):
        key = normalize_exact_text(_value(item, "task"))
        if action_id and key is not None and action_id not in matched_g:
            g_groups.setdefault(key, []).append(action_id)

    ambiguous_p: set[str] = set()
    ambiguous_g: set[str] = set()
    for key in p_groups:
        if key not in g_groups:
            continue
        candidates_p = [p_id for p_id in p_groups[key] if all((p_id, g_id) not in rejected for g_id in g_groups[key])]
        candidates_g = [g_id for g_id in g_groups[key] if all((p_id, g_id) not in rejected for p_id in p_groups[key])]
        if len(candidates_p) == 1 and len(candidates_g) == 1:
            p_id, g_id = candidates_p[0], candidates_g[0]
            if p_id not in matched_p and g_id not in matched_g:
                pairs.append((p_id, g_id))
                matched_p.add(p_id)
                matched_g.add(g_id)
        elif candidates_p and candidates_g:
            ambiguous_p.update(candidates_p)
            ambiguous_g.update(candidates_g)

    known_unmatched_p = tuple(action_id for action_id in pred_ids if action_id and action_id not in matched_p and action_id not in ambiguous_p)
    known_unmatched_g = tuple(action_id for action_id in gold_ids if action_id and action_id not in matched_g and action_id not in ambiguous_g)
    # A non-exact pair may be a Vietnamese paraphrase. Do not turn it into an FP+FN
    # until a reviewer rules the pair out; exact-text normalization is not semantic.
    if known_unmatched_p and known_unmatched_g:
        unresolved_pairs = [
            (p_id, g_id)
            for p_id in known_unmatched_p
            for g_id in known_unmatched_g
            if (p_id, g_id) not in rejected
        ]
        if unresolved_pairs:
            ambiguous_p.update(p_id for p_id, _ in unresolved_pairs)
            ambiguous_g.update(g_id for _, g_id in unresolved_pairs)
            known_unmatched_p = tuple(p_id for p_id in known_unmatched_p if p_id not in ambiguous_p)
            known_unmatched_g = tuple(g_id for g_id in known_unmatched_g if g_id not in ambiguous_g)
    status = "needs_manual_review" if ambiguous_p or ambiguous_g or errors else "complete"
    if errors and not ambiguous_p and not ambiguous_g:
        # Preserve all remaining cases as unresolved instead of counting malformed IDs as negatives.
        ambiguous_p.update(action_id for action_id in pred_ids if action_id)
        ambiguous_g.update(action_id for action_id in gold_ids if action_id)
        known_unmatched_p = ()
        known_unmatched_g = ()
    return MatchResult(
        pairs=tuple(pairs),
        unmatched_prediction_ids=known_unmatched_p,
        unmatched_gold_ids=known_unmatched_g,
        ambiguous_prediction_ids=tuple(action_id for action_id in pred_ids if action_id in ambiguous_p),
        ambiguous_gold_ids=tuple(action_id for action_id in gold_ids if action_id in ambiguous_g),
        decisions=tuple(normalized_decisions),
        issues=tuple(errors),
        status=status,
    )

