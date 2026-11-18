from evaluation.reporting import render_markdown, sanitize_report


def test_markdown_identifies_split_pending_metrics_and_failures():
    report = {"dataset": {"dataset_version": "1.0.0", "split": "development", "case_count": 10, "evaluated_count": 2, "skipped_count": 8, "pending_review_count": 2}, "metrics": {"actions": {"tp": 1, "fp": 0, "fn": 0, "precision": 1.0}}, "failures": [{"case_id": "case-001", "failure_category": "schema_invalid", "expected_behavior": "completed extraction", "actual_behavior": "invalid response"}], "cases": [{"case_id": "case-001", "status": "failed", "failure_category": "schema_invalid", "expected_behavior": "completed extraction", "actual_behavior": "invalid response"}]}
    markdown = render_markdown(report)
    assert "development" in markdown
    assert "pending" in markdown.lower()
    assert "case-001" in markdown
    assert "schema_invalid" in markdown


def test_report_sanitizer_removes_secret_values():
    safe = sanitize_report({"token": "super-secret", "nested": {"authorization": "Bearer abc"}, "provider": "x"})
    assert "super-secret" not in str(safe)
    assert "Bearer abc" not in str(safe)
    assert safe["provider"] == "x"
