import { execFile } from "node:child_process";
import { mkdir, stat } from "node:fs/promises";
import { join } from "node:path";
import { promisify } from "node:util";
import { AudioServiceError, positiveNumber } from "./audio-types.js";
import { PROVIDER_MAX_BYTES } from "./audio-provider.js";

const exec = promisify(execFile);

export async function ffmpeg(args: string[], signal: AbortSignal) {
  try {
    await exec(
      process.env.FFMPEG_PATH ?? "ffmpeg",
      [
        "-nostdin",
        "-v",
        "error",
        "-xerror",
        "-protocol_whitelist",
        "file,pipe",
        "-threads",
        "1",
        "-y",
        ...args,
      ],
      {
        signal,
        timeout: positiveNumber("AUDIO_FFMPEG_TIMEOUT_MS", 180_000, 600_000),
        maxBuffer: 256 * 1024,
      },
    );
  } catch (error) {
    if (signal.aborted) throw signal.reason;
    const failure = error as NodeJS.ErrnoException & { killed?: boolean };
    throw new AudioServiceError(
      failure.code === "ENOENT"
        ? "AUDIO_TOOL_UNAVAILABLE"
        : failure.killed
          ? "AUDIO_PROCESSING_TIMEOUT"
          : "AUDIO_PROCESSING_FAILED",
      503,
    );
  }
}

export async function probeDuration(path: string, signal: AbortSignal) {
  const { stdout } = await exec(
    process.env.FFPROBE_PATH ?? "ffprobe",
    [
      "-v",
      "error",
      "-protocol_whitelist",
      "file,pipe",
      "-show_entries",
      "format=duration",
      "-of",
      "json",
      path,
    ],
    { signal, timeout: 10_000, maxBuffer: 64 * 1024 },
  );
  const duration = Number(JSON.parse(stdout).format?.duration);
  if (!Number.isFinite(duration) || duration <= 0 || duration > 3600.1)
    throw new AudioServiceError("INVALID_PROCESSED_DURATION", 422);
  return duration;
}

export async function prepareAudio(
  source: string,
  directory: string,
  signal: AbortSignal,
) {
  await mkdir(directory, { recursive: true });
  const wav = join(directory, "normalized.wav");
  await ffmpeg(
    [
      "-i",
      source,
      "-map",
      "0:a:0",
      "-vn",
      "-ac",
      "1",
      "-ar",
      "16000",
      "-c:a",
      "pcm_s16le",
      wav,
    ],
    signal,
  );
  const duration = await probeDuration(wav, signal);
  const mp3 = join(directory, "diarization.mp3");
  // Keep one provider request so speaker labels remain consistent.
  await ffmpeg(
    [
      "-i",
      wav,
      "-ac",
      "1",
      "-ar",
      "16000",
      "-c:a",
      "libmp3lame",
      "-b:a",
      "32k",
      mp3,
    ],
    signal,
  );
  if ((await stat(mp3)).size >= PROVIDER_MAX_BYTES)
    throw new AudioServiceError("PROVIDER_FILE_TOO_LARGE", 422);
  return { wav, mp3, duration };
}
