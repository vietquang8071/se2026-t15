from __future__ import annotations

import json

import pytest

from evaluation.runner import LiveAuthorizationError, evaluate_offline, run_cli

def test_offline_runner_marks_missing_responses_not_evaluated(dataset, tmp_path):
    report = evaluate_offline(dataset, responses_dir=tmp_path, split="development")
    assert report["dataset"]["case_count"] == 10
    assert report["dataset"]["evaluated_count"] == 0
    assert report["dataset"]["skipped_count"] == 10
    assert report["run"]["network_requests"] == 0
    assert all(case["status"] == "not_evaluated" for case in report["cases"])
    assert report["metrics"]["actions"]["status"] == "not_evaluated"
    assert report["operational"]["http_failures"] is None


def test_case_filter_and_reports_work_without_api_keys(dataset, tmp_path, first_case, write_json, response_payload_factory, action_payload_factory, monkeypatch):
    response_dir = tmp_path / "responses"
    predicted_action = action_payload_factory("SEG-0002", task="Hoàn thiện API đặt lịch", owner="Minh", raw_due_expression="trước thứ Sáu này")
    write_json(response_dir / f"{first_case.case_id}.json", response_payload_factory(first_case, [predicted_action]))
    out = tmp_path / "out"
    monkeypatch.delenv("LLM_SERVICE_TOKEN", raising=False)
    status = run_cli(["run", "--responses-dir", str(response_dir), "--case", first_case.case_id, "--output-dir", str(out)])
    assert status == 0
    report = json.loads((out / "report.json").read_text())
    assert report["dataset"]["case_count"] == 1
    assert report["metrics"]["actions"]["f1"] == 1
    assert report["cases"][0]["action_items"]["owner"]["accuracy"] == 1
    assert report["cases"][0]["review_context"]["summary"]["forbidden_claims"]
    assert report["cases"][0]["operational"]["token_usage_status"] == "reported"
    assert (out / "report.md").is_file()


def test_live_mode_rejects_missing_operator_authorization():
    with pytest.raises(LiveAuthorizationError):
        run_cli(["run", "--mode", "live"])


def test_even_authorized_live_mode_fails_closed_without_cost_controls():
    with pytest.raises(LiveAuthorizationError):
        run_cli(["run", "--mode", "live", "--ack-live", "--max-cases", "1", "--spend-limit-usd", "0.5"])


def test_development_run_does_not_include_holdout_cases(dataset, tmp_path):
    report = evaluate_offline(dataset, responses_dir=tmp_path, split="development")
    assert len(report["cases"]) == 10
    assert all(case["split"] == "development" for case in report["cases"])
    assert report["operational"]["retry_policy"].endswith("no retries")


def test_case_from_other_split_is_rejected(dataset):
    with pytest.raises(ValueError, match="not in requested development split"):
        evaluate_offline(dataset, split="development", case_ids=["case-011"])


def test_live_budget_must_be_positive():
    with pytest.raises(LiveAuthorizationError):
        run_cli(["run", "--mode", "live", "--ack-live", "--max-cases", "1", "--spend-limit-usd", "0"])
