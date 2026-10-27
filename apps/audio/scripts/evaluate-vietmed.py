"""Evaluate transcription and segment speaker overlap against VietMed clip metadata."""
import argparse
import itertools
import json
import unicodedata
from pathlib import Path


def normalized(text):
    text = unicodedata.normalize("NFC", text).lower()
    return " ".join("".join(c if c.isalnum() or c.isspace() else " " for c in text).split())


def edit_distance(reference, hypothesis):
    previous = list(range(len(hypothesis) + 1))
    for i, expected in enumerate(reference, 1):
        current = [i]
        for j, actual in enumerate(hypothesis, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (expected != actual)))
        previous = current
    return previous[-1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=Path("artifacts/private/vietmed/reference.json"))
    parser.add_argument("--transcript", type=Path, default=Path("artifacts/private/audio-result/transcript.json"))
    parser.add_argument("--metadata", type=Path, default=Path("artifacts/private/audio-result/metadata.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/private/audio-result/quality-segment.json"))
    args = parser.parse_args()
    reference = json.loads(args.reference.read_text())
    transcript = json.loads(args.transcript.read_text())
    metadata = json.loads(args.metadata.read_text()) if args.metadata.exists() else {}
    reference_segments = reference["segments"]
    segments = transcript["segments"]
    duration = transcript["duration_sec"]
    full_reference = abs(duration - reference["duration_sec"]) <= 0.05
    gold = normalized(" ".join(segment["text"] for segment in reference_segments))
    hypothesis = normalized(transcript["text"])
    gold_tokens, hypothesis_tokens = gold.split(), hypothesis.split()
    gold_chars, hypothesis_chars = gold.replace(" ", ""), hypothesis.replace(" ", "")
    predicted_ids = sorted({s["speaker"] for s in segments if s["speaker"] != "unknown"})
    gold_ids = reference["speakers"]
    overlap = {}
    total_overlap = 0.0
    unknown_overlap = 0.0
    for segment in segments:
        for ref in reference_segments:
            overlap_seconds = max(0.0, min(segment["end"], ref["end"], duration) - max(segment["start"], ref["start"]))
            if not overlap_seconds:
                continue
            total_overlap += overlap_seconds
            if segment["speaker"] == "unknown":
                unknown_overlap += overlap_seconds
            key = (segment["speaker"], ref["speaker"])
            overlap[key] = overlap.get(key, 0.0) + overlap_seconds
    best_score, best_mapping = 0.0, {}
    count = min(len(predicted_ids), len(gold_ids))
    for chosen in itertools.combinations(predicted_ids, count):
        for expected_ids in itertools.permutations(gold_ids, count):
            mapping = dict(zip(chosen, expected_ids))
            score = sum(overlap.get((predicted, expected), 0.0) for predicted, expected in mapping.items())
            if score > best_score:
                best_score, best_mapping = score, mapping
    metric = {
        "dataset": reference["dataset"], "kind": reference["kind"],
        "duration_sec": duration, "reference_duration_sec": reference["duration_sec"],
        "schema_version": transcript["schema_version"], "models": transcript["models"],
        "provider_calls": metadata.get("job", {}).get("provider_calls"),
        "wer_whitespace_tokens": edit_distance(gold_tokens, hypothesis_tokens) / max(1, len(gold_tokens)) if full_reference else None,
        "cer_without_spaces": edit_distance(gold_chars, hypothesis_chars) / max(1, len(gold_chars)) if full_reference else None,
        "wer_gold_tokens": len(gold_tokens) if full_reference else None,
        "speaker_overlap_seconds_compared": total_overlap,
        "speaker_overlap_seconds_correct": best_score,
        "speaker_overlap_agreement": best_score / total_overlap if total_overlap else None,
        "unknown_overlap_seconds": unknown_overlap,
        "speaker_mapping_optimized_on_this_sample": best_mapping,
        "invalid_segment_timestamps": sum(not (0 <= s["start"] <= s["end"] <= duration + 0.001) for s in segments),
        "segments": len(segments),
        "notes": [
            "Speaker agreement is duration overlap with source clip labels, not DER; no collar or overlap exclusion is applied.",
            "The source is a stitched recording, not a natural meeting; gap/overlap and ASR-deleted speech are not fully scored.",
            "Overlapping predicted segments can count the same reference time more than once; speaker mapping is optimized on this sample.",
            "Whitespace-token WER is syllable-like for Vietnamese; punctuation is removed and diacritics retained.",
            "WER/CER are omitted for a partial reference because the final clip may be cut mid-utterance.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(metric, ensure_ascii=False, indent=2))
    print(json.dumps(metric, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
