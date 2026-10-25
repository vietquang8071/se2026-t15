"""Build a reproducible ~10-minute stitched benchmark, never a fake original call."""
import hashlib
import io
import json
import re
import urllib.request
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import soundfile as sf

destination = Path("artifacts/private/vietmed")
destination.mkdir(parents=True, exist_ok=True)
source = destination / "dev.parquet"
url = "https://huggingface.co/datasets/leduckhai/VietMed/resolve/main/data/dev-00000-of-00001.parquet"
if not source.exists():
    urllib.request.urlretrieve(url, source)
rows = pq.read_table(source).to_pylist()
speakers = ["VietMed_006_a", "VietMed_006_b"]
queues = {
    speaker: sorted(
        [row for row in rows if row["speaker_name"] == speaker],
        key=lambda row: int(re.search(r"_(\d+)$", row["seq_name"])[1]),
    )
    for speaker in speakers
}
parts, references = [], []
total_samples = 0
sample_rate = None
while sample_rate is None or total_samples / sample_rate < 600:
    for speaker in speakers:
        # Five source clips per turn, so identity isn't defined by a fixed time grid.
        for _ in range(5):
            if sample_rate and total_samples / sample_rate >= 600:
                break
            row = queues[speaker].pop(0)
            audio, rate = sf.read(io.BytesIO(row["audio"]["bytes"]), dtype="float32")
            if sample_rate is None:
                sample_rate = rate
            if rate != sample_rate or audio.ndim != 1:
                raise ValueError("Unexpected sample rate/channels; do not silently alter gold timing")
            start = total_samples / rate
            parts.append(audio)
            total_samples += len(audio)
            references.append({
                "start": start, "end": total_samples / rate,
                "speaker": speaker, "text": row["text"],
                "utterance_id": row["utterance_id"], "source_sequence": row["seq_name"],
            })
            gap = np.zeros(round(0.2 * rate), dtype="float32")
            parts.append(gap)
            total_samples += len(gap)
sf.write(destination / "conversation-10min.wav", np.concatenate(parts), sample_rate, subtype="PCM_16")
reference = {
    "source": url, "dataset": "leduckhai/VietMed", "split": "dev",
    "license_as_declared_by_dataset": "MIT",
    "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    "kind": "stitched_two_speaker_benchmark_not_continuous_original_conversation",
    "construction": "Same recording VietMed_006; clips sorted per speaker and alternated in blocks of five, 0.2s gaps. No utterance repeated.",
    "duration_sec": total_samples / sample_rate, "sample_rate": sample_rate,
    "speakers": speakers, "segments": references,
}
(destination / "reference.json").write_text(json.dumps(reference, ensure_ascii=False, indent=2))
print(json.dumps({"duration_sec": reference["duration_sec"], "clips": len(references), "speakers": speakers}))
