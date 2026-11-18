from __future__ import annotations

import copy
import json

import pytest

from evaluation.loader import DATASET_DIR, load_dataset
from evaluation.validation import validate_audio_request_consistency, validate_audio_transcript, validate_gold
from evaluation.runner import run_cli


def test_all_sixteen_cases_and_contract_requests_load(dataset):
    assert dataset.valid
    assert len(dataset.cases) == 16
    assert sum(case.split == "development" for case in dataset.cases) == 10
    assert sum(case.split == "holdout" for case in dataset.cases) == 6
    assert all(case.request.contract_version == "1.0" for case in dataset.cases)


def test_audio_fields_are_preserved_and_unknown_speaker_maps_to_null(dataset):
    case = next(case for case in dataset.cases if case.case_id == "case-014")
    for audio_segment, request_segment in zip(case.audio["segments"], case.request.transcript.segments):
        assert audio_segment["id"] == request_segment.id
        assert audio_segment["text"] == request_segment.text
        assert audio_segment["start"] == request_segment.start
        assert audio_segment["end"] == request_segment.end
        assert request_segment.speaker_id == (None if audio_segment["speaker"] == "unknown" else audio_segment["speaker"])
    assert case.audio["duration_sec"] == case.request.meeting.duration_seconds


def test_duplicate_audio_segment_ids_are_rejected(dataset):
    audio = copy.deepcopy(dataset.cases[0].audio)
    audio["segments"][1]["id"] = audio["segments"][0]["id"]
    issues = validate_audio_transcript(audio, case_id="synthetic")
    assert any("duplicate" in issue.message.lower() or "unique" in issue.message.lower() for issue in issues)


def test_invalid_audio_timestamp_is_rejected(dataset):
    audio = copy.deepcopy(dataset.cases[0].audio)
    audio["segments"][0]["start"] = -1
    issues = validate_audio_transcript(audio, case_id="synthetic")
    assert any("start" in issue.message.lower() or "timestamp" in issue.message.lower() for issue in issues)


def test_malformed_audio_speaker_object_is_reported_without_crashing(dataset):
    audio = copy.deepcopy(dataset.cases[0].audio)
    audio["speakers"][0]["id"] = ["speaker_1"]
    issues = validate_audio_transcript(audio, case_id="synthetic")
    assert any("speaker" in issue.path.lower() for issue in issues)


def test_missing_required_file_is_reported(write_json, tmp_path):
    root = tmp_path / "dataset"
    manifest = json.loads((DATASET_DIR / "dataset-manifest.json").read_text())
    manifest["cases"] = [manifest["cases"][0]]
    write_json(root / "dataset-manifest.json", manifest)
    case_dir = root / "cases" / "case-001"
    for name in ("audio-transcript-v2.json", "llm-request.json"):
        write_json(case_dir / name, json.loads((DATASET_DIR / "cases/case-001" / name).read_text()))
    result = load_dataset(root, check_expected_counts=False)
    assert any("gold.json" in issue.message for issue in result.issues)


def test_gold_source_reference_must_exist(dataset):
    case = dataset.cases[0]
    gold = copy.deepcopy(case.gold)
    gold["action_items"][0]["source_segment_ids"] = ["SEG-MISSING"]
    issues = validate_gold(gold, case.request, case_id=case.case_id)
    assert any("SEG-MISSING" in issue.message for issue in issues)


def test_malformed_gold_source_list_is_reported_without_crashing(dataset):
    case = dataset.cases[0]
    gold = copy.deepcopy(case.gold)
    gold["action_items"][0]["source_segment_ids"] = [{"not": "a string"}]
    issues = validate_gold(gold, case.request, case_id=case.case_id)
    assert any("source references" in issue.message.lower() for issue in issues)


def test_manifest_duplicate_case_id_is_reported(write_json, tmp_path):
    manifest = json.loads((DATASET_DIR / "dataset-manifest.json").read_text())
    manifest["cases"] = manifest["cases"][:2]
    manifest["cases"][1]["case_id"] = manifest["cases"][0]["case_id"]
    root = tmp_path / "dataset"
    write_json(root / "dataset-manifest.json", manifest)
    result = load_dataset(root, check_expected_counts=False)
    assert any("duplicate" in issue.message.lower() for issue in result.issues)


def test_invalid_split_is_reported(write_json, tmp_path):
    manifest = json.loads((DATASET_DIR / "dataset-manifest.json").read_text())
    entry = copy.deepcopy(manifest["cases"][0])
    entry["split"] = "validation"
    manifest["cases"] = [entry]
    root = tmp_path / "dataset"
    write_json(root / "dataset-manifest.json", manifest)
    case_dir = root / "cases" / entry["case_id"]
    for name in ("audio-transcript-v2.json", "llm-request.json", "gold.json"):
        write_json(case_dir / name, json.loads((DATASET_DIR / "cases" / entry["case_id"] / name).read_text()))
    result = load_dataset(root, check_expected_counts=False)
    assert any(issue.code == "invalid_split" for issue in result.issues)


def test_gold_temporal_nullability_must_be_consistent(dataset):
    case = dataset.cases[0]
    gold = copy.deepcopy(case.gold)
    gold["action_items"][0]["due_date"] = "2026-11-20"
    issues = validate_gold(gold, case.request, case_id=case.case_id)
    assert any("must not contain a resolved due_date" in issue.message for issue in issues)


@pytest.mark.parametrize("invalid_gold", [[], None, "invalid"])
def test_non_object_gold_is_a_case_scoped_dataset_error(copy_dataset, invalid_gold, capsys):
    root = copy_dataset()
    gold_path = root / "cases" / "case-001" / "gold.json"
    gold_path.write_text(json.dumps(invalid_gold), encoding="utf-8")

    result = load_dataset(root)

    assert not result.valid
    assert not any(case.case_id == "case-001" for case in result.cases)
    assert any(issue.case_id == "case-001" and issue.code == "gold_invalid" and issue.path == "gold.json" for issue in result.issues)
    assert run_cli(["validate-dataset", "--dataset-dir", str(root)]) == 2
    output = capsys.readouterr().err
    assert "case-001" in output
    assert "gold.json" in output


def test_manifest_count_cannot_hide_a_case_that_failed_to_load(copy_dataset):
    root = copy_dataset()
    (root / "cases" / "case-016" / "gold.json").unlink()

    result = load_dataset(root)

    assert len(result.cases) == 15
    assert not result.valid
    assert any(issue.code == "case_count_mismatch" and "loaded" in issue.message for issue in result.issues)


def test_loaded_count_must_match_manifest_total_even_without_fixed_expected_counts(copy_dataset):
    root = copy_dataset()
    manifest_path = root / "dataset-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["cases_total"] = 15
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = load_dataset(root, check_expected_counts=False)

    assert len(result.cases) == 16
    assert not result.valid
    assert any(issue.code == "case_count_mismatch" and "Manifest declares 15" in issue.message for issue in result.issues)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda audio: audio.update(segments=None),
        lambda audio: audio.update(segments="invalid"),
        lambda audio: audio.update(segments={}),
        lambda audio: audio.update(segments=[None]),
        lambda audio: audio["segments"][0].pop("id"),
        lambda audio: audio["segments"][0].update(start=-1),
        lambda audio: audio.pop("duration_sec"),
        lambda audio: audio["segments"][0].update(speaker={"id": "speaker_1"}),
    ],
    ids=["null-segments", "string-segments", "object-segments", "null-segment", "missing-id", "invalid-timestamp", "missing-duration", "invalid-speaker"],
)
def test_malformed_audio_returns_structured_issue_and_cli_status_two(copy_dataset, mutate, capsys):
    root = copy_dataset()
    audio_path = root / "cases" / "case-001" / "audio-transcript-v2.json"
    audio = json.loads(audio_path.read_text(encoding="utf-8"))
    mutate(audio)
    audio_path.write_text(json.dumps(audio, ensure_ascii=False), encoding="utf-8")

    result = load_dataset(root)

    assert not result.valid
    assert any(issue.case_id == "case-001" and issue.code == "audio_invalid" for issue in result.issues)
    assert run_cli(["validate-dataset", "--dataset-dir", str(root)]) == 2
    output = capsys.readouterr().err
    assert "case-001" in output
    assert "Traceback" not in output


@pytest.mark.parametrize("segments", [None, "invalid", {}, [None]])
def test_consistency_checker_rejects_malformed_segments_without_crashing(dataset, first_case, segments):
    audio = copy.deepcopy(first_case.audio)
    audio["segments"] = segments

    issues = validate_audio_request_consistency(audio, first_case.request, case_id="synthetic")

    assert issues
    assert all(issue.case_id == "synthetic" for issue in issues)


def test_consistency_checker_rejects_unusable_timestamp_before_offset_comparison(first_case):
    audio = copy.deepcopy(first_case.audio)
    audio["source_audio_start_sec"] = 0.5
    audio["segments"][0]["start"] = []

    issues = validate_audio_request_consistency(audio, first_case.request, case_id="synthetic")

    assert any("structural validation" in issue.message for issue in issues)
