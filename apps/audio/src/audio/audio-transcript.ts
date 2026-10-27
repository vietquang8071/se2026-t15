import { AudioServiceError } from "./audio-types.js";
import type {
  AudioTranscript,
  Chunk,
  DiarizationResult,
  TimedWord,
  WhisperResult,
} from "./audio-types.js";

// A short gap can be a missed boundary between two turns of the same speaker.
const MAX_SAME_SPEAKER_GAP_SECONDS = 0.75;

function validTime(start: unknown, end: unknown, duration: number) {
  return (
    typeof start === "number" &&
    typeof end === "number" &&
    Number.isFinite(start) &&
    Number.isFinite(end) &&
    start >= 0 &&
    end >= start &&
    end <= duration + 0.5
  );
}

export function validateWhisper(raw: unknown, duration: number): WhisperResult {
  const result = raw as WhisperResult;
  if (
    !result ||
    typeof result.text !== "string" ||
    !Array.isArray(result.words) ||
    !Array.isArray(result.segments)
  )
    throw new AudioServiceError("PROVIDER_INVALID_TRANSCRIPT", 502);
  let previous = 0;
  for (const word of result.words) {
    if (
      !word ||
      !validTime(word.start, word.end, duration) ||
      word.start < previous ||
      typeof word.word !== "string"
    )
      throw new AudioServiceError("PROVIDER_INVALID_TIMESTAMPS", 502);
    previous = word.start;
  }
  for (const segment of result.segments) {
    if (
      !segment ||
      !validTime(segment.start, segment.end, duration) ||
      typeof segment.text !== "string"
    )
      throw new AudioServiceError("PROVIDER_INVALID_TIMESTAMPS", 502);
  }
  if (result.text.trim() && !result.words.length)
    throw new AudioServiceError("PROVIDER_WORD_TIMESTAMPS_MISSING", 502);
  return result;
}

export function validateDiarization(
  raw: unknown,
  duration: number,
): DiarizationResult {
  const result = raw as DiarizationResult;
  if (!result || !Array.isArray(result.segments))
    throw new AudioServiceError("PROVIDER_INVALID_DIARIZATION", 502);
  for (const turn of result.segments) {
    if (
      !turn ||
      !validTime(turn.start, turn.end, duration) ||
      typeof turn.speaker !== "string" ||
      !turn.speaker ||
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
  chunks: { chunk: Chunk; result: WhisperResult }[],
  diarization: DiarizationResult,
): AudioTranscript {
  const labels = new Map<string, string>();
  const turns = [...diarization.segments].sort((a, b) => a.start - b.start);
  for (const turn of turns) {
    if (!labels.has(turn.speaker))
      labels.set(turn.speaker, `speaker_${labels.size + 1}`);
  }
  const gaps = turns.slice(1).flatMap((next, index) => {
    const previous = turns[index];
    const gap = next.start - previous.end;
    if (
      previous.speaker !== next.speaker ||
      gap <= 0 ||
      gap > MAX_SAME_SPEAKER_GAP_SECONDS ||
      turns.some(
        (turn) =>
          turn.speaker !== previous.speaker &&
          turn.start < next.start &&
          turn.end > previous.end,
      )
    )
      return [];
    return [{ previous, next }];
  });
  const words: TimedWord[] = [];
  for (const { chunk, result } of chunks) {
    for (const word of result.words) {
      const midpoint = chunk.offset + (word.start + word.end) / 2;
      // Each chunk owns its core interval; overlap is context, never extra text.
      if (midpoint < chunk.keepStart || midpoint >= chunk.keepEnd) continue;
      const start = chunk.offset + word.start;
      const end = chunk.offset + word.end;
      const matches = new Map<string, number>();
      for (const turn of diarization.segments) {
        // Whisper sometimes gives a word a zero-length timestamp. Preserve that
        // timing and use point containment; do not invent a word duration.
        const intersection =
          end === start
            ? Number(turn.start <= start && start < turn.end)
            : Math.max(
                0,
                Math.min(end, turn.end) - Math.max(start, turn.start),
              );
        if (intersection)
          matches.set(
            turn.speaker,
            (matches.get(turn.speaker) ?? 0) + intersection,
          );
      }
      const ranked = [...matches].sort((a, b) => b[1] - a[1]);
      const length = end === start ? 1 : end - start;
      const winner = ranked[0];
      let speaker =
        winner &&
        winner[1] / length >= 0.5 &&
        (!ranked[1] || ranked[1][1] / length < 0.2)
          ? labels.get(winner[0])!
          : "unknown";
      let bridgedGap = false;
      if (speaker === "unknown") {
        const candidates = gaps.filter(({ previous, next }) => {
          const touchesGap =
            start === end
              ? previous.end <= start && start < next.start
              : start < next.start && end > previous.end;
          const coverage =
            start === end
              ? Number(previous.start <= start && start < next.end)
              : Math.max(
                  0,
                  Math.min(end, next.end) - Math.max(start, previous.start),
                );
          return (
            touchesGap &&
            coverage / length >= 0.5 &&
            ![...matches.keys()].some((id) => id !== previous.speaker)
          );
        });
        const candidateSpeakers = new Set(
          candidates.map(({ previous }) => previous.speaker),
        );
        if (candidateSpeakers.size === 1) {
          speaker = labels.get(candidates[0].previous.speaker)!;
          bridgedGap = true;
        }
      }
      words.push({
        word: word.word.trim(),
        start: Math.min(sourceDuration, start + sourceOffset),
        end: Math.min(sourceDuration, end + sourceOffset),
        speaker,
        ...(bridgedGap ? { speaker_attribution: "bridged_gap" as const } : {}),
      });
    }
  }
  words.sort((a, b) => a.start - b.start);
  const segments: AudioTranscript["segments"] = [];
  for (const word of words) {
    const previous = segments.at(-1);
    if (
      previous &&
      previous.speaker === word.speaker &&
      word.start - previous.end < 1.5 &&
      word.end - previous.start < 20
    ) {
      previous.words.push(word);
      previous.end = Math.max(previous.end, word.end);
      previous.text += ` ${word.word}`;
    } else
      segments.push({
        id: `SEG-${String(segments.length + 1).padStart(4, "0")}`,
        start: word.start,
        end: word.end,
        speaker: word.speaker,
        text: word.word,
        words: [word],
      });
  }
  const used = [...new Set(words.map((word) => word.speaker))];
  return {
    schema_version: 1,
    audio_id: audioId,
    language: "vi",
    timeline: "source",
    source_audio_start_sec: sourceOffset,
    duration_sec: sourceDuration,
    text: segments.map((segment) => segment.text).join("\n"),
    segments,
    speakers: used.map((id) => ({
      id,
      name: id === "unknown" ? "Chưa xác định" : id,
    })),
    warnings: [
      ...(used.includes("unknown")
        ? [
            "Một số từ chưa xác định được người nói hoặc nằm trong vùng chồng tiếng.",
          ]
        : []),
      ...(words.some((word) => word.speaker_attribution === "bridged_gap")
        ? [
            "Một số từ được gán người nói bằng cách nối khoảng trống ngắn giữa hai lượt của cùng người; cần kiểm tra lại.",
          ]
        : []),
      ...(!words.length
        ? ["Không phát hiện lời nói; chưa có transcript để đánh giá."]
        : []),
      "Nhãn người nói do model suy luận, không phải danh tính đã xác thực.",
      "Ghép chunk theo vùng thời gian; cần kiểm tra thủ công từ ở biên chunk và vùng chồng tiếng.",
    ],
    models: {
      transcription: process.env.OPENAI_ASR_MODEL ?? "whisper-1",
      diarization:
        process.env.OPENAI_DIARIZATION_MODEL ?? "gpt-4o-transcribe-diarize",
    },
  };
}
