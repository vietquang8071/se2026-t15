import json
from pathlib import Path


FIXTURES = Path(__file__).parents[1] / "fixtures"


def _reject_nonstandard_constant(value):
    raise ValueError(f"Non-standard JSON constant: {value}")


def test_all_fixtures_parse_as_standard_json():
    fixture_paths = sorted(FIXTURES.rglob("*.json"))

    assert fixture_paths
    for path in fixture_paths:
        json.loads(path.read_text(), parse_constant=_reject_nonstandard_constant)
