import json
from pathlib import Path

import pytest
from pydantic import ValidationError


FIXTURES = Path(__file__).parents[1] / "fixtures"


def _temporal_model():
    try:
        from app.schemas.temporal import TemporalResolution
    except ImportError as error:
        pytest.fail(f"TemporalResolution is not implemented yet: {error}")
    return TemporalResolution


def _fixture(name):
    return json.loads((FIXTURES / "temporal" / name).read_text())


@pytest.mark.parametrize(
    ("fixture", "status"),
    [
        ("exact_date.json", "exact_date"),
        ("date_range.json", "date_range"),
        ("unresolved.json", "unresolved"),
    ],
)
def test_temporal_state_fixtures_validate(fixture, status):
    validated = _temporal_model().model_validate(_fixture(fixture))

    assert validated.status == status


def test_leap_day_is_a_valid_calendar_date():
    temporal = _fixture("exact_date.json")
    temporal["resolved_date"] = "2024-02-29"

    validated = _temporal_model().model_validate(temporal)

    assert validated.resolved_date.isoformat() == "2024-02-29"


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.update(start_date="2026-10-18", end_date="2026-10-12"),
        lambda value: value.update(resolved_date="2026-10-12"),
        lambda value: value.update(needs_review=False),
    ],
)
def test_date_range_rejects_inconsistent_dates_or_review_state(change):
    temporal = _fixture("date_range.json")
    change(temporal)

    with pytest.raises(ValidationError):
        _temporal_model().model_validate(temporal)


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.update(start_date="2026-10-04"),
        lambda value: value.update(end_date="2026-10-06"),
        lambda value: value.update(needs_review=True),
    ],
)
def test_exact_date_rejects_range_fields_or_review_state(change):
    temporal = _fixture("exact_date.json")
    change(temporal)

    with pytest.raises(ValidationError):
        _temporal_model().model_validate(temporal)


def test_unresolved_rejects_any_resolved_date():
    temporal = _fixture("unresolved.json")
    temporal["resolved_date"] = "2026-10-09"

    with pytest.raises(ValidationError):
        _temporal_model().model_validate(temporal)


@pytest.mark.parametrize("bad_date", ["2023-02-29", "2026-13-01", "2026-10-05T00:00:00Z"])
def test_temporal_fields_require_valid_date_only_values(bad_date):
    temporal = _fixture("exact_date.json")
    temporal["resolved_date"] = bad_date

    with pytest.raises(ValidationError):
        _temporal_model().model_validate(temporal)


def test_temporal_source_ids_must_be_nonempty_and_unique():
    temporal = _fixture("exact_date.json")
    temporal["source_segment_ids"] = ["seg-001", "seg-001"]

    with pytest.raises(ValidationError):
        _temporal_model().model_validate(temporal)
