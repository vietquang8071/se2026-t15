import { readFile, stat } from "node:fs/promises";
import { setTimeout as delay } from "node:timers/promises";
import { AudioServiceError, positiveNumber } from "./audio-types.js";

export const PROVIDER_MAX_BYTES = 24_000_000;
export const DIARIZATION_MODEL = "gpt-4o-transcribe-diarize";

export function openAIKey() {
  return (
    process.env.OPENAI_API_KEY?.trim() || process.env.OpenAI_API_KEY?.trim()
  );
}

/** Native fetch keeps provider calls explicit: no hidden SDK retries. */
export async function transcribeWithDiarization(
  filePath: string,
  signal: AbortSignal,
  beforeCall: () => Promise<void>,
): Promise<unknown> {
  const key = openAIKey();
  if (!key) throw new AudioServiceError("OPENAI_KEY_MISSING", 503);
  if ((await stat(filePath)).size >= PROVIDER_MAX_BYTES)
    throw new AudioServiceError("PROVIDER_FILE_TOO_LARGE", 422);
  const bytes = await readFile(filePath);
  for (let attempt = 0; attempt < 3; attempt++) {
    signal.throwIfAborted();
    const form = new FormData();
    form.set("file", new Blob([bytes], { type: "audio/mpeg" }), "audio.mp3");
    form.set("model", DIARIZATION_MODEL);
    form.set("language", "vi");
    form.set("response_format", "diarized_json");
    form.set("chunking_strategy", "auto");
    await beforeCall();
    let retryAfter = 0;
    try {
      const timeout = AbortSignal.timeout(
        positiveNumber("OPENAI_TIMEOUT_MS", 600_000, 600_000),
      );
      const response = await fetch(
        "https://api.openai.com/v1/audio/transcriptions",
        {
          method: "POST",
          body: form,
          headers: { Authorization: `Bearer ${key}` },
          signal: AbortSignal.any([signal, timeout]),
        },
      );
      if (response.ok) {
        try {
          return await response.json();
        } catch {
          throw new AudioServiceError("PROVIDER_INVALID_RESPONSE", 502);
        }
      }
      // Never put raw provider error bodies (potential private data) in logs.
      const body = (await response.json().catch(() => ({}))) as {
        error?: { code?: string };
      };
      if (response.status === 401 || response.status === 403)
        throw new AudioServiceError("PROVIDER_AUTH_FAILED", 502);
      if (body.error?.code === "insufficient_quota")
        throw new AudioServiceError("PROVIDER_QUOTA_EXHAUSTED", 503);
      if (response.status !== 429 && response.status < 500)
        throw new AudioServiceError("PROVIDER_REQUEST_REJECTED", 502);
      retryAfter =
        Math.min(30, Number(response.headers.get("retry-after")) || 0) * 1000;
    } catch (error) {
      if (signal.aborted) throw signal.reason;
      if (error instanceof AudioServiceError) throw error;
    }
    if (attempt === 2) throw new AudioServiceError("PROVIDER_UNAVAILABLE", 503);
    await delay(Math.max(retryAfter, 1000 * 2 ** attempt), undefined, {
      signal,
    });
  }
  throw new AudioServiceError("PROVIDER_UNAVAILABLE", 503);
}
