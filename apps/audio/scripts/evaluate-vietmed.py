"""Measure ASR against supplied gold; speaker metric is not a full DER benchmark."""
import itertools
import json
import unicodedata
from pathlib import Path


def normalized(text):
    text = unicodedata.normalize("NFC", text).lower()
    text = "".join(c if c.isalnum() or c.isspace() else " " for c in text)
    return " ".join(text.split())


def edit_distance(reference, hypothesis):
    previous = list(range(len(hypothesis) + 1))
    for i, expected in enumerate(reference, 1):
        current = [i]
        for j, actual in enumerate(hypothesis, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (expected != actual)))
        previous = current
    return previous[-1]


root = Path("artifacts/private")
reference = json.loads((root / "vietmed/reference.json").read_text())
transcript = json.loads((root / "audio-result/transcript.json").read_text())
metadata = json.loads((root / "audio-result/metadata.json").read_text())
gold = normalized(" ".join(segment["text"] for segment in reference["segments"]))
hypothesis = normalized(transcript["text"])
gold_tokens, hypothesis_tokens = gold.split(), hypothesis.split()
gold_chars, hypothesis_chars = gold.replace(" ", ""), hypothesis.replace(" ", "")
words = [word for segment in transcript["segments"] for word in segment["words"]]
predicted_ids = sorted({word["speaker"] for word in words if word["speaker"] != "unknown"})
gold_ids = reference["speakers"]
confusion = {}
compared = unknown = 0
for word in words:
    midpoint = (word["start"] + word["end"]) / 2
    expected = next((segment["speaker"] for segment in reference["segments"] if segment["start"] <= midpoint < segment["end"]), None)
    if expected is not None:
        compared += 1
        unknown += word["speaker"] == "unknown"
        key = (word["speaker"], expected)
        confusion[key] = confusion.get(key, 0) + 1
best_score, best_mapping = 0, {}
for chosen in itertools.permutations(predicted_ids, min(len(gold_ids), len(predicted_ids))):
    mapping = dict(zip(chosen, gold_ids))
    score = sum(confusion.get((predicted, expected), 0) for predicted, expected in mapping.items())
    if score > best_score:
        best_score, best_mapping = score, mapping
timestamp_errors = sum(
    not (0 <= word["start"] <= word["end"] <= transcript["duration_sec"] + 0.001)
    for word in words
)
metric = {
    "dataset": reference["dataset"], "kind": reference["kind"],
    "source_sha256": reference["source_sha256"], "duration_sec": reference["duration_sec"],
    "clips": len(reference["segments"]), "gold_speakers": len(gold_ids),
    "models": transcript["models"], "provider_calls": metadata["job"]["provider_calls"],
    "job_attempts": metadata["job"]["attempts"],
    "normalization": "Unicode NFC; lowercase; punctuation to spaces; whitespace collapsed; diacritics retained; CER excludes spaces",
    "gold_whitespace_tokens": len(gold_tokens), "hypothesis_whitespace_tokens": len(hypothesis_tokens),
    "wer": edit_distance(gold_tokens, hypothesis_tokens) / max(1, len(gold_tokens)),
    "cer": edit_distance(gold_chars, hypothesis_chars) / max(1, len(gold_chars)),
    "predicted_speaker_ids": predicted_ids, "best_speaker_mapping": best_mapping,
    "speaker_agreement_at_predicted_word_midpoints": best_score / max(1, compared),
    "compared_words": compared, "unknown_compared_words": unknown,
    "invalid_timestamp_words": timestamp_errors,
    "segments": len(transcript["segments"]), "words": len(words),
    "limitations": [
        "Stitched benchmark, not a natural uninterrupted meeting; medical domain and one recording only.",
        "Vietnamese whitespace-token WER measures syllable-like tokens, not linguistic word segmentation.",
        "Speaker score uses source clip speaker metadata at predicted word midpoints, not gold speech activity; it is NOT DER and ignores ASR-deleted words.",
        "Speaker mapping is chosen after inference to handle arbitrary predicted label permutation.",
        "No threshold was agreed before testing; a successful pipeline does not establish general recognition quality.",
    ],
}
(root / "audio-result/quality.json").write_text(json.dumps(metric, ensure_ascii=False, indent=2))
print(json.dumps(metric, ensure_ascii=False, indent=2))
