"""Load the immutable synthetic evaluation dataset and report precise issues."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.schemas.request import ExtractionRequest
from evaluation.validation import (
    ValidationIssue,
    validate_audio_request_consistency,
    validate_audio_transcript,
    validate_gold,
)

PACKAGE_DIR = Path(__file__).resolve().parent
DATASET_DIR = PACKAGE_DIR / "datasets" / "llm-03.7-evaluation"
REQUIRED_FILES = (
    "audio-transcript-v2.json",
    "llm-request.json",
    "gold.json",
)
VALID_SPLITS = {"development", "holdout"}


@dataclass(frozen=True)
class DatasetCase:
    case_id: str
    split: str
    audio: dict[str, Any]
    request: ExtractionRequest
    gold: dict[str, Any]
    case_dir: Path
    scenario: str | None = None


@dataclass(frozen=True)
class DatasetLoadResult:
    root: Path
    manifest: dict[str, Any]
    cases: tuple[DatasetCase, ...]
    issues: tuple[ValidationIssue, ...]

    @property
    def valid(self) -> bool:
        return not self.issues and bool(self.manifest)

    def case(self, case_id: str) -> DatasetCase | None:
        return next((case for case in self.cases if case.case_id == case_id), None)


def _read_json(path: Path, *, case_id: str, label: str, issues: list[ValidationIssue]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        issues.append(ValidationIssue(case_id, "missing_file", f"Required {label} file is missing: {path.name}."))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        issues.append(ValidationIssue(case_id, "invalid_json", f"Could not read {label}: {error}", path.name))
    return None


def load_dataset(
    root: str | Path = DATASET_DIR, *, check_expected_counts: bool = True
) -> DatasetLoadResult:
    dataset_root = Path(root).resolve()
    issues: list[ValidationIssue] = []
    manifest_path = dataset_root / "dataset-manifest.json"
    manifest = _read_json(manifest_path, case_id="dataset", label="manifest", issues=issues)
    if not isinstance(manifest, dict):
        issues.append(ValidationIssue("dataset", "manifest_invalid", "dataset-manifest.json must contain a JSON object."))
        manifest = {}
    entries = manifest.get("cases", [])
    if not isinstance(entries, list):
        issues.append(ValidationIssue("dataset", "manifest_invalid", "Manifest cases must be an array."))
        entries = []
    entry_by_id: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not isinstance(entry.get("case_id"), str):
            issues.append(ValidationIssue("dataset", "manifest_invalid", f"Manifest cases[{index}] needs a case_id."))
            continue
        case_id = entry["case_id"]
        if case_id in entry_by_id:
            issues.append(ValidationIssue(case_id, "duplicate_case_id", f"Duplicate case ID {case_id!r} in dataset manifest."))
            continue
        entry_by_id[case_id] = entry
        if entry.get("split") not in VALID_SPLITS:
            issues.append(ValidationIssue(case_id, "invalid_split", f"Invalid split {entry.get('split')!r}; expected development or holdout."))
        if entry.get("files") != [f"cases/{case_id}/{name}" for name in REQUIRED_FILES]:
            issues.append(ValidationIssue(case_id, "manifest_files_invalid", "Manifest files must reference the three required files in the case directory."))

    cases_root = dataset_root / "cases"
    try:
        discovered = sorted(path.name for path in cases_root.iterdir() if path.is_dir())
    except OSError as error:
        discovered = []
        issues.append(ValidationIssue("dataset", "cases_missing", f"Could not discover case directories: {error}"))
    discovered_set = set(discovered)
    for case_id in sorted(set(entry_by_id) - discovered_set):
        issues.append(ValidationIssue(case_id, "missing_case_directory", "Manifest references a case directory that does not exist."))
    for case_id in sorted(discovered_set - set(entry_by_id)):
        issues.append(ValidationIssue(case_id, "unlisted_case_directory", "Case directory is not referenced by dataset manifest."))

    if check_expected_counts:
        expected = {"cases_total": 16, "development_cases": 10, "holdout_cases": 6}
        for field, count in expected.items():
            if manifest.get(field) != count:
                issues.append(ValidationIssue("dataset", "manifest_count_mismatch", f"Manifest {field} must be {count}, got {manifest.get(field)!r}."))
        if len(entry_by_id) != 16:
            issues.append(ValidationIssue("dataset", "case_count_mismatch", f"Expected 16 unique manifest cases, got {len(entry_by_id)}."))
        for split, expected_count in (("development", 10), ("holdout", 6)):
            count = sum(entry.get("split") == split for entry in entry_by_id.values())
            if count != expected_count:
                issues.append(ValidationIssue("dataset", "split_count_mismatch", f"Expected {expected_count} {split} cases, got {count}."))

    loaded: list[DatasetCase] = []
    for case_id in discovered:
        entry = entry_by_id.get(case_id)
        if entry is None:
            continue
        case_dir = cases_root / case_id
        file_values = {
            name: _read_json(case_dir / name, case_id=case_id, label=name, issues=issues)
            for name in REQUIRED_FILES
        }
        audio = file_values["audio-transcript-v2.json"]
        raw_request = file_values["llm-request.json"]
        gold = file_values["gold.json"]
        audio_issues = validate_audio_transcript(audio, case_id=case_id)
        issues.extend(audio_issues)
        try:
            request = ExtractionRequest.model_validate(raw_request)
        except ValidationError as error:
            for item in error.errors():
                path = ".".join(str(part) for part in item["loc"])
                issues.append(ValidationIssue(case_id, "request_invalid", f"ExtractionRequest validation failed: {item['msg']}", path))
            continue
        if isinstance(audio, dict):
            issues.extend(validate_audio_request_consistency(audio, request, case_id=case_id))
        if isinstance(gold, dict):
            issues.extend(validate_gold(gold, request, case_id=case_id))
        if not isinstance(audio, dict) or not isinstance(gold, dict):
            continue
        loaded.append(DatasetCase(
            case_id=case_id,
            split=entry.get("split", "invalid"),
            audio=audio,
            request=request,
            gold=gold,
            case_dir=case_dir,
            scenario=entry.get("scenario"),
        ))
    return DatasetLoadResult(dataset_root, manifest, tuple(loaded), tuple(issues))

