import { AudioServiceError } from "./audio-types.js";
import type { AudioTranscriptV2, DiarizationResult } from "./audio-types.js";
import { DIARIZATION_MODEL } from "./audio-provider.js";

// Allow only a small rounding difference at the duration boundary.
const TIME_TOLERANCE_SECONDS = 0.05;

export function validateDiarization(
  raw: unknown,
  duration: number,
): DiarizationResult {
  if (
    !raw ||
    typeof raw !== "object" ||
    !Number.isFinite(duration) ||
    duration <= 0
  )
    throw new AudioServiceError("PROVIDER_INVALID_DIARIZATION", 502);
  const result = raw as DiarizationResult;
  if (
    !Array.isArray(result.segments) ||
    (result.text !== undefined && typeof result.text !== "string") ||
    (!result.segments.length && result.text?.trim())
  )
    throw new AudioServiceError("PROVIDER_INVALID_DIARIZATION", 502);
  for (const turn of result.segments) {
    if (
      !turn ||
      typeof turn.start !== "number" ||
      typeof turn.end !== "number" ||
      !Number.isFinite(turn.start) ||
      !Number.isFinite(turn.end) ||
      turn.start < 0 ||
      turn.end < turn.start ||
      turn.end > duration + TIME_TOLERANCE_SECONDS ||
      typeof turn.speaker !== "string" ||
      !turn.speaker.trim() ||
      typeof turn.text !== "string"
    )
      throw new AudioServiceError("PROVIDER_INVALID_DIARIZATION", 502);
  }
  return result;
}

export function buildTranscript(
  audioId: string,
  sourceDuration: number,
  sourceOffset: number,
  diarization: DiarizationResult,
): AudioTranscriptV2 {
  if (
    !Number.isFinite(sourceDuration) ||
    sourceDuration <= 0 ||
    !Number.isFinite(sourceOffset) ||
    sourceOffset < 0 ||
    sourceOffset > sourceDuration
  )
    throw new AudioServiceError("INVALID_SOURCE_TIMELINE", 422);
  const turns = [...diarization.segments].sort((a, b) => a.start - b.start);
  const labels = new Map<string, string>();
  const segments = turns.map((turn, index) => {
    const start = turn.start + sourceOffset;
    const end = turn.end + sourceOffset;
    if (
      start > sourceDuration + TIME_TOLERANCE_SECONDS ||
      end > sourceDuration + TIME_TOLERANCE_SECONDS
    )
      throw new AudioServiceError("PROVIDER_INVALID_DIARIZATION", 502);
    const providerSpeaker = turn.speaker.trim();
    const isUnknown = ["unknown", "unassigned"].includes(
      providerSpeaker.toLowerCase(),
    );
    if (!isUnknown && !labels.has(providerSpeaker))
      labels.set(providerSpeaker, `speaker_${labels.size + 1}`);
    return {
      id: `SEG-${String(index + 1).padStart(4, "0")}`,
      start: Math.min(sourceDuration, start),
      end: Math.min(sourceDuration, end),
      speaker: isUnknown ? "unknown" : labels.get(providerSpeaker)!,
      text: turn.text,
    };
  });
  const used = [...new Set(segments.map((segment) => segment.speaker))];
  return {
    schema_version: 2,
    audio_id: audioId,
    language: "vi",
    timeline: "source",
    source_audio_start_sec: sourceOffset,
    duration_sec: sourceDuration,
    text: segments
      .map((segment) => segment.text.trim())
      .filter(Boolean)
      .join("\n"),
    segments,
    speakers: used.map((id) => ({
      id,
      name: id === "unknown" ? "Chưa xác định" : id,
    })),
    warnings: [
      ...(used.includes("unknown")
        ? ["Provider không xác định người nói cho một số đoạn."]
        : []),
      ...(!segments.length
        ? ["Không phát hiện lời nói; chưa có transcript để đánh giá."]
        : []),
      "Nhãn người nói do model suy luận, không phải danh tính đã xác thực.",
    ],
    models: { transcription_and_diarization: DIARIZATION_MODEL },
  };
}
