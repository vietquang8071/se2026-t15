from evaluation.matching import match_actions


def action(action_id, task):
    return {"id": action_id, "task": task}


def gold_action(action_id, task):
    return {"gold_id": action_id, "task": task}


def test_exact_task_matching_is_order_independent_and_one_to_one():
    result = match_actions(
        [action("ACT-1", "Gửi báo cáo"), action("ACT-2", "Sửa API")],
        [gold_action("G-2", "Sửa API"), gold_action("G-1", "Gửi báo cáo")],
    )
    assert result.pairs == (("ACT-1", "G-1"), ("ACT-2", "G-2"))
    assert result.unmatched_prediction_ids == ()
    assert result.unmatched_gold_ids == ()


def test_paraphrase_stays_pending_until_explicit_reviewer_match():
    predictions = [action("ACT-1", "Hoàn tất tài liệu onboarding")]
    gold = [gold_action("G-1", "Hoàn thiện tài liệu hướng dẫn nhân viên mới")]
    pending = match_actions(predictions, gold)
    assert pending.status == "needs_manual_review"
    assert pending.pairs == ()
    resolved = match_actions(predictions, gold, decisions=[{"prediction_id": "ACT-1", "gold_id": "G-1", "decision": "match", "reviewer": "reviewer-a"}])
    assert resolved.pairs == (("ACT-1", "G-1"),)
    assert resolved.status == "complete"


def test_duplicate_exact_task_candidates_are_ambiguous():
    result = match_actions(
        [action("ACT-1", "Gửi báo cáo"), action("ACT-2", "Gửi báo cáo")],
        [gold_action("G-1", "Gửi báo cáo")],
    )
    assert result.status == "needs_manual_review"
    assert len(result.ambiguous_prediction_ids) == 2
    assert result.pairs == ()


def test_duplicate_prediction_is_not_counted_as_second_true_positive():
    result = match_actions(
        [action("ACT-1", "Gửi báo cáo"), action("ACT-2", "Gửi báo cáo")],
        [gold_action("G-1", "Gửi báo cáo")],
        decisions=[{"prediction_id": "ACT-1", "gold_id": "G-1", "decision": "match", "reviewer": "r"}],
    )
    assert result.pairs == (("ACT-1", "G-1"),)
    assert result.unmatched_prediction_ids == ("ACT-2",)


def test_nonexact_unmatched_pair_requires_review_instead_of_fp_fn():
    result = match_actions([action("ACT-1", "Tạo dashboard")], [gold_action("G-1", "Làm bảng điều khiển")])
    assert result.status == "needs_manual_review"
    assert result.unmatched_prediction_ids == ()
    assert result.unmatched_gold_ids == ()
    assert result.ambiguous_prediction_ids == ("ACT-1",)
    assert result.ambiguous_gold_ids == ("G-1",)


def test_conflicting_manual_matches_cannot_match_one_gold_twice():
    result = match_actions(
        [action("ACT-1", "A"), action("ACT-2", "B")],
        [gold_action("G-1", "C")],
        decisions=[
            {"prediction_id": "ACT-1", "gold_id": "G-1", "decision": "match", "reviewer": "r"},
            {"prediction_id": "ACT-2", "gold_id": "G-1", "decision": "match", "reviewer": "r"},
        ],
    )
    assert result.status == "needs_manual_review"
    assert len(result.pairs) == 1
    assert result.issues
