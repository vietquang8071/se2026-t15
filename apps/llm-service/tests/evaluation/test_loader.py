from __future__ import annotations

import copy
import json

from evaluation.loader import DATASET_DIR, load_dataset
from evaluation.validation import validate_audio_transcript, validate_gold


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
