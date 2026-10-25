export interface TimedWord {
  word: string;
  start: number;
  end: number;
  speaker: string;
}

export interface TranscriptSegment {
  id: string;
  start: number;
  end: number;
  text: string;
  speaker: string;
  words: TimedWord[];
}

export interface AudioTranscript {
  schema_version: 1;
  audio_id: string;
  language: "vi";
  timeline: "source";
  source_audio_start_sec: number;
  duration_sec: number;
  text: string;
  speakers: { id: string; name: string }[];
  segments: TranscriptSegment[];
  warnings: string[];
  models: { transcription: string; diarization: string };
}

export interface WhisperResult {
  text: string;
  segments: { start: number; end: number; text: string }[];
  words: { start: number; end: number; word: string }[];
}

export interface DiarizationResult {
  segments: { start: number; end: number; speaker: string; text: string }[];
}

export interface Chunk {
  index: number;
  path: string;
  offset: number;
  duration: number;
  keepStart: number;
  keepEnd: number;
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
