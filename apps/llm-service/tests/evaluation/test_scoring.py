from evaluation.scoring import evaluate_actions, validate_semantic_grounding_review, validate_summary_review
from evaluation.matching import match_actions


def test_zero_action_case_is_correct_absence_without_artificial_tp():
    result = evaluate_actions([], [], transcript_segments=[])
    assert result.tp == result.fp == result.fn == 0
    assert result.correct_empty is True
    assert result.precision is None and result.recall is None and result.f1 is None


def test_false_positive_and_missed_action_are_counted(first_case):
    gold = [{"gold_id": "G-1", "task": "Hoàn thiện API đặt lịch", "owner": None, "raw_due_expression": None, "due_date": None, "due_date_resolution_status": "unresolved", "priority": None, "source_segment_ids": ["SEG-0002"], "owner_evidence_segment_ids": [], "deadline_evidence_segment_ids": []}]
    predictions = [{"id": "ACT-1", "task": "Tạo thêm báo cáo", "owner": None, "raw_due_expression": None, "due_date": None, "due_date_resolution": None, "priority": None}]
    matching = match_actions(predictions, gold, decisions=[{"prediction_id": "ACT-1", "gold_id": "G-1", "decision": "not_match", "reviewer": "reviewer-a"}])
    result = evaluate_actions(gold, predictions, transcript_segments=first_case.request.transcript.segments, matching=matching)
    assert (result.tp, result.fp, result.fn) == (0, 1, 1)
    assert result.precision == 0 and result.recall == 0 and result.f1 == 0


def test_matched_action_scores_null_owner_and_fabricated_deadline_priority():
    gold = [{"gold_id": "G-1", "task": "Gửi tài liệu", "owner": None, "raw_due_expression": None, "due_date": None, "due_date_resolution_status": "unresolved", "priority": None, "source_segment_ids": ["S1"], "owner_evidence_segment_ids": [], "deadline_evidence_segment_ids": []}]
    pred = [{"id": "ACT-1", "task": "Gửi tài liệu", "owner": "Lan", "raw_due_expression": "ngày mai", "due_date": None, "due_date_resolution": {"status": "unresolved"}, "priority": "High"}]
    result = evaluate_actions(gold, pred, transcript_segments=[])
    assert result.owner.accuracy == 0
    assert result.owner.correct_null_rate == 0
    assert result.owner.unsupported_count == 1
    assert result.deadline.fabricated_count == 1
    assert result.priority.fabricated_count == 1


def test_summary_scores_are_pending_without_human_review():
    result = validate_summary_review(None)
    assert result["status"] == "pending_review"
    assert result["faithfulness"] is None


def test_summary_review_rejects_out_of_range_scores():
    try:
        validate_summary_review({"faithfulness": 6, "required_fact_coverage": 0.5, "conciseness_actionability": 3, "semantic_source_grounding": 0.5, "hallucination_count": 0, "reviewer": "r"})
    except ValueError as error:
        assert "faithfulness" in str(error)
    else:
        raise AssertionError("out-of-range score accepted")


def test_manual_action_match_result_is_used_by_scorer():
    gold = [{"gold_id": "G-1", "task": "Viết tài liệu người dùng"}]
    pred = [{"id": "ACT-1", "task": "Soạn hướng dẫn sử dụng"}]
    matching = match_actions(pred, gold, decisions=[{"prediction_id": "ACT-1", "gold_id": "G-1", "decision": "match", "reviewer": "r"}])
    assert matching.pairs == (("ACT-1", "G-1"),)


def test_perfect_action_match_and_reordered_actions_have_unit_metrics():
    gold = [
        {"gold_id": "G-1", "task": "A", "owner": None, "raw_due_expression": None, "due_date": None, "due_date_resolution_status": "unresolved", "priority": None},
        {"gold_id": "G-2", "task": "B", "owner": "Lan", "raw_due_expression": None, "due_date": None, "due_date_resolution_status": "unresolved", "priority": "High"},
    ]
    predictions = [
        {"id": "ACT-2", "task": "B", "owner": "Lan", "raw_due_expression": None, "due_date": None, "due_date_resolution": None, "priority": "High"},
        {"id": "ACT-1", "task": "A", "owner": None, "raw_due_expression": None, "due_date": None, "due_date_resolution": None, "priority": None},
    ]
    match = match_actions(predictions, gold)
    score = evaluate_actions(gold, predictions, transcript_segments=[], matching=match)
    assert (score.tp, score.fp, score.fn) == (2, 0, 0)
    assert score.precision == score.recall == score.f1 == 1
    assert score.owner.accuracy == 1
    assert score.owner.correct_null_rate == 1
    assert score.priority.explicit_accuracy == 1
    assert score.priority.correct_null_rate == 1


def test_single_sided_action_errors_have_zero_f1():
    gold = [{"gold_id": "G-1", "task": "A"}]
    missed = evaluate_actions(gold, [], transcript_segments=[])
    false_positive = evaluate_actions([], [{"id": "ACT-1", "task": "B"}], transcript_segments=[])
    assert (missed.tp, missed.fp, missed.fn, missed.f1) == (0, 0, 1, 0)
    assert (false_positive.tp, false_positive.fp, false_positive.fn, false_positive.f1) == (0, 1, 0, 0)


def test_final_reassignment_owner_is_evaluated_as_gold():
    gold = [{"gold_id": "G-1", "task": "Chuẩn bị release", "owner": "Lan", "raw_due_expression": None, "due_date": None, "due_date_resolution_status": "unresolved", "priority": None}]
    predictions = [{"id": "ACT-1", "task": "Chuẩn bị release", "owner": "Lan", "raw_due_expression": None, "due_date": None, "due_date_resolution": None, "priority": None}]
    result = evaluate_actions(gold, predictions, transcript_segments=[])
    assert result.owner.accuracy == 1
    assert result.owner.wrong_owner_count == 0


def test_iso_deadline_and_unresolved_deadline_are_scored_separately():
    gold = [{"gold_id": "G-1", "task": "Nộp checklist", "owner": None, "raw_due_expression": "2026-12-15", "due_date": "2026-12-15", "due_date_resolution_status": "exact_date", "priority": None}]
    prediction = [{"id": "ACT-1", "task": "Nộp checklist", "owner": None, "raw_due_expression": "2026-12-15", "due_date": "2026-12-15", "due_date_resolution": {"status": "exact_date"}, "priority": None}]
    result = evaluate_actions(gold, prediction, transcript_segments=[])
    assert result.deadline.raw_expression_accuracy == 1
    assert result.deadline.resolved_date_accuracy == 1
    assert result.deadline.temporal_status_accuracy == 1


def test_unresolved_relative_deadline_is_not_treated_as_bad_resolution():
    gold = [{"gold_id": "G-1", "task": "Gửi hồ sơ", "owner": None, "raw_due_expression": "trước thứ Sáu", "due_date": None, "due_date_resolution_status": "unresolved", "priority": None}]
    prediction = [{"id": "ACT-1", "task": "Gửi hồ sơ", "owner": None, "raw_due_expression": "trước thứ Sáu", "due_date": None, "due_date_resolution": {"status": "unresolved"}, "priority": None}]
    result = evaluate_actions(gold, prediction, transcript_segments=[])
    assert result.deadline.raw_expression_accuracy == 1
    assert result.deadline.temporal_status_accuracy == 1
    assert result.deadline.resolved_date_accuracy is None


def test_resolved_date_for_unresolved_gold_deadline_is_fabricated():
    gold = [{"gold_id": "G-1", "task": "Gửi hồ sơ", "owner": None, "raw_due_expression": "trước thứ Sáu", "due_date": None, "due_date_resolution_status": "unresolved", "priority": None}]
    prediction = [{"id": "ACT-1", "task": "Gửi hồ sơ", "owner": None, "raw_due_expression": "trước thứ Sáu", "due_date": "2026-11-20", "due_date_resolution": {"status": "exact_date"}, "priority": None}]
    result = evaluate_actions(gold, prediction, transcript_segments=[])
    assert result.deadline.fabricated_count == 1
    assert result.deadline.resolved_date_accuracy == 0


def test_human_semantic_grounding_and_hallucination_annotations_are_preserved():
    review = validate_summary_review({"faithfulness": 2, "required_fact_coverage": 0.5, "conciseness_actionability": 3, "semantic_source_grounding": 0.25, "hallucination_count": 1, "hallucinations": ["Bịa mốc giao hàng"], "reviewer": "r"})
    assert review["status"] == "reviewed"
    assert review["hallucinations"] == ["Bịa mốc giao hàng"]
    semantic = validate_semantic_grounding_review({"reviewer": "r", "claims": [{"claim_id": "action.task", "verdict": "supported"}, {"claim_id": "summary.overview", "verdict": "unsupported"}]})
    assert semantic["supported"] == semantic["unsupported"] == 1
    assert semantic["accuracy"] == 0.5


def test_summary_adjudication_record_requires_reviewer_and_valid_scores():
    payload = {"faithfulness": 4, "required_fact_coverage": 1, "conciseness_actionability": 4, "semantic_source_grounding": 1, "hallucination_count": 0, "reviewer": "r", "adjudication": {"reason": "tie-break"}}
    try:
        validate_summary_review(payload)
    except ValueError as error:
        assert "adjudication" in str(error)
    else:
        raise AssertionError("adjudication without a reviewer was accepted")
