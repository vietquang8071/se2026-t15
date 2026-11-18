"""Safe JSON and Markdown report output for offline evaluation runs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_SECRET_KEY = re.compile(r"(?:^token$|api[_-]?key|authorization|access[_-]?token|secret|credential|password)", re.I)
_BEARER = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
_KEY_LIKE = re.compile(r"\b(?:sk|or|rk)-[A-Za-z0-9_-]{12,}\b")


def sanitize_report(value: Any, *, _key: str = "") -> Any:
    if _key and _SECRET_KEY.search(_key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(key): sanitize_report(item, _key=str(key)) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_report(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_report(item) for item in value]
    if isinstance(value, str):
        return _KEY_LIKE.sub("[REDACTED]", _BEARER.sub("Bearer [REDACTED]", value))
    return value


def write_reports(report: dict[str, Any], output_dir: str | Path) -> tuple[Path, Path]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    safe = sanitize_report(report)
    json_path, markdown_path = directory / "report.json", directory / "report.md"
    json_path.write_text(json.dumps(safe, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(safe), encoding="utf-8")
    return json_path, markdown_path


def _format(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def render_markdown(report: dict[str, Any]) -> str:
    dataset = report.get("dataset", {})
    metrics = report.get("metrics", {})
    actions = metrics.get("actions", {})
    deadlines = metrics.get("deadline", {})
    lines = [
        "# LLM-03.7 Offline Evaluation Report",
        "",
        f"- Dataset version: `{dataset.get('dataset_version', 'unknown')}`",
        f"- Split: `{dataset.get('split', 'all')}`",
        f"- Cases: {dataset.get('case_count', 0)}; expected gold actions: {dataset.get('expected_action_count', 0)}; evaluated: {dataset.get('evaluated_count', 0)}; skipped: {dataset.get('skipped_count', 0)}; pending human review: {dataset.get('pending_review_count', 0)}",
        "",
        "## Quality metrics",
        "",
        "| Metric | Result | Denominator / notes |",
        "|---|---:|---|",
        f"| Contract compliance | {_format(metrics.get('contract_compliance', {}).get('value'))} | {metrics.get('contract_compliance', {}).get('denominator', 0)} response files |",
        f"| Extraction success rate | {_format(metrics.get('extraction_success_rate', {}).get('value'))} | {metrics.get('extraction_success_rate', {}).get('denominator', 0)} response files |",
        f"| Action TP / FP / FN | {actions.get('tp', 0)} / {actions.get('fp', 0)} / {actions.get('fn', 0)} | predicted {actions.get('predicted_count', 0)}; expected in evaluated responses {actions.get('expected_count', 0)}; gold in selected dataset {dataset.get('expected_action_count', 0)} |",
        f"| Action precision / recall / F1 | {_format(actions.get('precision'))} / {_format(actions.get('recall'))} / {_format(actions.get('f1'))} | status: {actions.get('status', 'not_evaluated')} |",
        f"| Correct empty action cases | {actions.get('correct_empty_cases', 0)} | empty gold and prediction; excluded from F1 |",
        f"| Owner accuracy | {_format(metrics.get('owner', {}).get('accuracy'))} | denominator {metrics.get('owner', {}).get('denominator', 0)}; unsupported {metrics.get('owner', {}).get('unsupported_count', 0)}; wrong {metrics.get('owner', {}).get('wrong_owner_count', 0)} |",
        f"| Deadline raw / date / status accuracy | {_format(deadlines.get('raw_expression_accuracy', {}).get('value'))} / {_format(deadlines.get('resolved_date_accuracy', {}).get('value'))} / {_format(deadlines.get('temporal_status_accuracy', {}).get('value'))} | denominators {deadlines.get('raw_denominator', 0)} / {deadlines.get('date_denominator', 0)} / {deadlines.get('status_denominator', 0)}; fabricated {deadlines.get('fabricated_count', 0)} |",
        f"| Priority accuracy | {_format(metrics.get('priority', {}).get('explicit_accuracy'))} | denominator {metrics.get('priority', {}).get('denominator', 0)}; fabricated {metrics.get('priority', {}).get('fabricated_count', 0)} |",
        f"| Structural source grounding | {_format(metrics.get('structural_grounding', {}).get('value'))} | {metrics.get('structural_grounding', {}).get('denominator', 0)} schema-valid responses; semantic grounding is reviewed separately |",
        f"| Summary semantic review | {metrics.get('summary_review', {}).get('status', 'pending_review')} | reviewed {metrics.get('summary_review', {}).get('denominator', 0)}; pending {metrics.get('summary_review', {}).get('pending', 0)} |",
        f"| Summary faithfulness / coverage / actionability / grounding | {json.dumps(metrics.get('summary_review', {}).get('means', {}), ensure_ascii=False)} | hallucinations {metrics.get('summary_review', {}).get('hallucination_count', 'N/A')} |",
        f"| Semantic evidence grounding | {metrics.get('semantic_grounding_review', {}).get('status', 'pending_review')} | supported {metrics.get('semantic_grounding_review', {}).get('supported', 'N/A')}; unsupported {metrics.get('semantic_grounding_review', {}).get('unsupported', 'N/A')}; claims {metrics.get('semantic_grounding_review', {}).get('denominator', 0)} |",
        "",
        "## Operational metrics",
        "",
        f"- Model/provider observations: {json.dumps(report.get('operational', {}).get('model_provider', []), ensure_ascii=False)}",
        f"- Mean latency (seconds): {_format(report.get('operational', {}).get('mean_latency_seconds'))}",
        f"- Token usage: {json.dumps(report.get('operational', {}).get('token_usage', {}), ensure_ascii=False)}",
        f"- Cost: {report.get('operational', {}).get('cost_status', 'unavailable')}; estimated USD `{_format(report.get('operational', {}).get('estimated_cost_usd'))}`; actual billed USD `{_format(report.get('operational', {}).get('actual_billed_cost_usd'))}`",
        "- HTTP status/failures are not applicable to offline saved responses.",
        "",
        "## Failure analysis",
        "",
    ]
    failures = report.get("failures", [])
    if not failures:
        lines.append("No response validation failures were recorded.")
    else:
        lines.extend(["| Case | Category | Expected | Actual | Uncertainty / reference errors |", "|---|---|---|---|---|"])
        for failure in failures:
            uncertain = "; ".join(failure.get("evaluation_uncertainty", []))
            missing = "; ".join(failure.get("missing_or_invalid_references", []))
            lines.append(f"| {failure.get('case_id')} | {failure.get('failure_category')} | {failure.get('expected_behavior', '')} | {failure.get('actual_behavior', '')} | {missing}; {uncertain} |")
    lines.extend(["", "## Per-case status", "", "| Case | Split | Status | Actions TP/FP/FN | Summary review |", "|---|---|---|---:|---|"])
    for case in report.get("cases", []):
        action = case.get("action_items") or {}
        counts = f"{action.get('tp', 0)}/{action.get('fp', 0)}/{action.get('fn', 0)}" if case.get("status") == "evaluated" else "N/A"
        lines.append(f"| {case.get('case_id')} | {case.get('split')} | {case.get('status')} | {counts} | {(case.get('summary_review') or {}).get('status', 'N/A')} |")
    lines.extend(["", "Semantic matching and summary judgments are not inferred automatically. Pending values are not zero scores.", ""])
    return "\n".join(lines)

