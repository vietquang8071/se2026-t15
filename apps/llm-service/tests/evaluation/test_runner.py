from __future__ import annotations

import json

import pytest

from evaluation.runner import evaluate_offline, run_cli

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


def test_live_mode_rejects_missing_operator_authorization(capsys):
    assert run_cli(["run", "--mode", "live"]) == 3
    assert "explicit --ack-live" in capsys.readouterr().err


def test_even_authorized_live_mode_fails_closed_without_cost_controls(capsys):
    assert run_cli(["run", "--mode", "live", "--ack-live", "--max-cases", "1", "--spend-limit-usd", "0.5"]) == 3
    assert "Live execution is disabled" in capsys.readouterr().err


def test_development_run_does_not_include_holdout_cases(dataset, tmp_path):
    report = evaluate_offline(dataset, responses_dir=tmp_path, split="development")
    assert len(report["cases"]) == 10
    assert all(case["split"] == "development" for case in report["cases"])
    assert report["operational"]["retry_policy"].endswith("no retries")


def test_case_from_other_split_is_rejected(dataset):
    with pytest.raises(ValueError, match="not in requested development split"):
        evaluate_offline(dataset, split="development", case_ids=["case-011"])


def test_live_budget_must_be_positive():
    assert run_cli(["run", "--mode", "live", "--ack-live", "--max-cases", "1", "--spend-limit-usd", "0"]) == 3


def test_invalid_saved_response_returns_exit_status_one(dataset, tmp_path, first_case, write_json, response_payload_factory):
    response_dir = tmp_path / "responses"
    payload = response_payload_factory(first_case)
    payload["meeting_id"] = "wrong-meeting"
    write_json(response_dir / f"{first_case.case_id}.json", payload)

    assert run_cli(["run", "--responses-dir", str(response_dir), "--case", first_case.case_id, "--output-dir", str(tmp_path / "out")]) == 1


def test_non_utf8_saved_response_is_recorded_as_failure(dataset, tmp_path, first_case):
    response_dir = tmp_path / "responses"
    response_path = response_dir / f"{first_case.case_id}.json"
    response_path.parent.mkdir(parents=True)
    response_path.write_bytes(b"\xff")

    assert run_cli(["run", "--responses-dir", str(response_dir), "--case", first_case.case_id, "--output-dir", str(tmp_path / "out")]) == 1


def test_invalid_dataset_returns_exit_status_two(copy_dataset, capsys):
    root = copy_dataset()
    (root / "cases" / "case-001" / "gold.json").write_text("[]", encoding="utf-8")

    assert run_cli(["run", "--dataset-dir", str(root), "--output-dir", str(root.parent / "out")]) == 2
    assert "case-001" in capsys.readouterr().err


def _write_response_and_review(tmp_path, case, payload, review, write_json):
    response_dir = tmp_path / "responses"
    review_path = write_json(tmp_path / "reviews.json", {"cases": {case.case_id: review}})
    write_json(response_dir / f"{case.case_id}.json", payload)
    return response_dir, review_path


def _complete_summary_review(*, reviewer="reviewer-a"):
    return {
        "faithfulness": 5,
        "required_fact_coverage": 1,
        "conciseness_actionability": 4,
        "semantic_source_grounding": 1,
        "hallucination_count": 0,
        "reviewer": reviewer,
    }


@pytest.mark.parametrize(
    "review",
    [
        {"summary_review": {**_complete_summary_review(), "faithfulness": 6}},
        {"summary_review": {key: value for key, value in _complete_summary_review().items() if key != "reviewer"}},
        {"semantic_grounding": {"reviewer": "reviewer-a", "claims": [{"claim_id": "not-a-response-claim", "verdict": "supported"}]}},
        {"action_matches": [None]},
    ],
    ids=["summary-out-of-range", "missing-reviewer", "unknown-semantic-claim", "non-object-match"],
)
def test_invalid_review_inputs_return_exit_status_three(dataset, tmp_path, first_case, write_json, response_payload_factory, review, capsys):
    response_dir, review_path = _write_response_and_review(tmp_path, first_case, response_payload_factory(first_case), review, write_json)

    status = run_cli(["run", "--responses-dir", str(response_dir), "--reviews", str(review_path), "--case", first_case.case_id, "--output-dir", str(tmp_path / "out")])

    assert status == 3
    error = capsys.readouterr().err.lower()
    assert "review" in error or "annotation" in error or "action match" in error or "semantic grounding" in error


def test_conflicting_manual_match_assignments_return_exit_status_three(dataset, tmp_path, first_case, write_json, response_payload_factory, action_payload_factory, capsys):
    actions = [
        action_payload_factory("SEG-0002", action_id="ACT-001", task="Hoàn thiện API đặt lịch"),
        action_payload_factory("SEG-0003", action_id="ACT-002", task="Kiểm thử API"),
    ]
    actions[1]["source_timestamp"] = "00:00:13.937"
    review = {"action_matches": [
        {"prediction_id": "ACT-001", "gold_id": "GOLD-ACT-001", "decision": "match", "reviewer": "reviewer-a"},
        {"prediction_id": "ACT-002", "gold_id": "GOLD-ACT-001", "decision": "match", "reviewer": "reviewer-a"},
    ]}
    response_dir, review_path = _write_response_and_review(tmp_path, first_case, response_payload_factory(first_case, actions), review, write_json)

    status = run_cli(["run", "--responses-dir", str(response_dir), "--reviews", str(review_path), "--case", first_case.case_id, "--output-dir", str(tmp_path / "out")])

    assert status == 3
    assert "one-to-one" in capsys.readouterr().err.lower()


def test_unknown_review_case_is_rejected(dataset, tmp_path, write_json, capsys):
    review_path = write_json(tmp_path / "reviews.json", {"cases": {"case-999": {"action_matches": []}}})

    status = run_cli(["run", "--reviews", str(review_path), "--output-dir", str(tmp_path / "out")])

    assert status == 3
    assert "case-999" in capsys.readouterr().err


def test_malformed_top_level_review_input_returns_exit_status_three(tmp_path, capsys, write_json):
    review_path = write_json(tmp_path / "reviews.json", {"cases": []})

    status = run_cli(["run", "--reviews", str(review_path), "--output-dir", str(tmp_path / "out")])

    assert status == 3
    assert "review" in capsys.readouterr().err.lower()


def test_non_utf8_review_file_returns_exit_status_three(tmp_path, capsys):
    review_path = tmp_path / "reviews.json"
    review_path.write_bytes(b"\xff")

    status = run_cli(["run", "--reviews", str(review_path), "--output-dir", str(tmp_path / "out")])

    assert status == 3
    assert "review" in capsys.readouterr().err.lower()


@pytest.mark.parametrize(
    "action_matches",
    ["not-an-array", [{}], [{"prediction_id": "ACT-001", "gold_id": "GOLD-ACT-001", "decision": "approved", "reviewer": "r"}]],
    ids=["invalid-array-type", "missing-required-fields", "invalid-decision"],
)
def test_malformed_action_match_annotations_return_exit_status_three(dataset, tmp_path, first_case, write_json, response_payload_factory, action_payload_factory, action_matches, capsys):
    review = {"action_matches": action_matches}
    prediction = action_payload_factory("SEG-0002", task="Hoàn thiện API đặt lịch")
    response_dir, review_path = _write_response_and_review(tmp_path, first_case, response_payload_factory(first_case, [prediction]), review, write_json)

    status = run_cli(["run", "--responses-dir", str(response_dir), "--reviews", str(review_path), "--case", first_case.case_id, "--output-dir", str(tmp_path / "out")])

    assert status == 3
    error = capsys.readouterr().err.lower()
    assert "review" in error or "action match" in error or "action_matches" in error


def test_valid_partial_semantic_review_stays_incomplete_in_aggregate(dataset, tmp_path, write_json, response_payload_factory):
    response_dir = tmp_path / "responses"
    first, second = dataset.case("case-001"), dataset.case("case-002")
    write_json(response_dir / "case-001.json", response_payload_factory(first, []))
    write_json(response_dir / "case-002.json", response_payload_factory(second, []))
    review_path = write_json(tmp_path / "reviews.json", {"cases": {"case-001": {
        "semantic_grounding": {"reviewer": "reviewer-a", "claims": [{"claim_id": "summary.overview", "verdict": "supported"}]}
    }}})

    status = run_cli(["run", "--responses-dir", str(response_dir), "--reviews", str(review_path), "--case", "case-001", "--case", "case-002", "--output-dir", str(tmp_path / "out")])
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    semantic = report["metrics"]["semantic_grounding_review"]

    assert status == 0
    assert report["cases"][0]["semantic_grounding"]["status"] == "partial_review"
    assert semantic["status"] == "partial_review"
    assert semantic["fully_reviewed_cases"] == 0
    assert semantic["partial_cases"] == 1
    assert semantic["pending_cases"] == 2
    assert semantic["pending_claim_count"] > 0
    assert semantic["accuracy"] is None
    assert semantic["provisional_accuracy"] == 1


def test_valid_complete_human_review_succeeds(dataset, tmp_path, first_case, write_json, response_payload_factory, action_payload_factory):
    action = action_payload_factory("SEG-0002", task="Hoàn thiện API đặt lịch", owner="Minh", raw_due_expression="trước thứ Sáu này")
    payload = response_payload_factory(first_case, [action])
    claims = [
        {"claim_id": "summary.overview", "verdict": "supported"},
        {"claim_id": "actions[0].task", "verdict": "supported"},
        {"claim_id": "actions[0].owner", "verdict": "supported"},
        {"claim_id": "actions[0].raw_due_expression", "verdict": "supported"},
    ]
    review = {"summary_review": _complete_summary_review(), "semantic_grounding": {"reviewer": "reviewer-a", "claims": claims}}
    response_dir, review_path = _write_response_and_review(tmp_path, first_case, payload, review, write_json)

    status = run_cli(["run", "--responses-dir", str(response_dir), "--reviews", str(review_path), "--case", first_case.case_id, "--output-dir", str(tmp_path / "out")])
    report = json.loads((tmp_path / "out" / "report.json").read_text())

    assert status == 0
    assert report["cases"][0]["semantic_grounding"]["status"] == "reviewed"
    assert report["metrics"]["semantic_grounding_review"]["accuracy"] == 1


def test_review_decision_referencing_missing_action_is_rejected(dataset, tmp_path, first_case, write_json, response_payload_factory, capsys):
    review = {"action_matches": [{"prediction_id": "ACT-MISSING", "gold_id": "GOLD-ACT-001", "decision": "match", "reviewer": "reviewer-a"}]}
    response_dir, review_path = _write_response_and_review(tmp_path, first_case, response_payload_factory(first_case), review, write_json)

    assert run_cli(["run", "--responses-dir", str(response_dir), "--reviews", str(review_path), "--case", first_case.case_id, "--output-dir", str(tmp_path / "out")]) == 3
    assert "action" in capsys.readouterr().err.lower()
