export interface TranscriptSegment {
  id: string;
  start: number;
  end: number;
  text: string;
  speaker: string;
}

interface TranscriptBase {
  audio_id: string;
  language: "vi";
  timeline: "source";
  source_audio_start_sec: number;
  duration_sec: number;
  text: string;
  speakers: { id: string; name: string }[];
  warnings: string[];
}

// Existing version-1 transcripts remain readable and are never rewritten as v2.
export interface LegacyAudioTranscript extends TranscriptBase {
  schema_version: 1;
  segments: (TranscriptSegment & {
    words: {
      word: string;
      start: number;
      end: number;
      speaker: string;
      speaker_attribution?: "bridged_gap";
    }[];
  })[];
  models: { transcription: string; diarization: string };
}

export interface AudioTranscriptV2 extends TranscriptBase {
  schema_version: 2;
  segments: TranscriptSegment[];
  models: { transcription_and_diarization: string };
}

export type AudioTranscript = LegacyAudioTranscript | AudioTranscriptV2;

export interface DiarizationResult {
  text?: string;
  segments: { start: number; end: number; speaker: string; text: string }[];
}

export class AudioServiceError extends Error {
  constructor(
    readonly code: string,
    readonly status = 500,
  ) {
    super(code);
  }
}

export function positiveNumber(name: string, fallback: number, max: number) {
  const value = Number(process.env[name] ?? fallback);
  if (!Number.isFinite(value) || value <= 0 || value > max)
    throw new Error(`Invalid configuration: ${name}`);
  return value;
}
