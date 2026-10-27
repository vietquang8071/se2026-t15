import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { mkdtemp, rm, writeFile, stat, truncate } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { createSilentWav } from "./fixtures.mjs";
import {
  prepareAudio,
  probeDuration,
} from "../../dist/audio-test/audio/audio-media.js";
import { transcribeWithDiarization } from "../../dist/audio-test/audio/audio-provider.js";

let root;
before(async () => {
  root = await mkdtemp(join(tmpdir(), "audio-media-"));
});
after(async () => {
  await rm(root, { recursive: true, force: true });
});

test("FFmpeg prepares one normalized WAV and one full-recording MP3", async () => {
  const source = join(root, "source.wav");
  await createSilentWav(source, 12 * 8000 * 2);
  const prepared = await prepareAudio(
    source,
    join(root, "prepared"),
    new AbortController().signal,
  );
  assert.equal(prepared.duration, 12);
  assert.ok((await stat(prepared.mp3)).size < 24000000);
  assert.ok(
    Math.abs(
      (await probeDuration(prepared.mp3, new AbortController().signal)) - 12,
    ) < 0.2,
  );
  assert.ok((await stat(source)).size > 0);
});

test("provider makes one diarization request with the required multipart fields", async (t) => {
  const path = join(root, "fake.mp3");
  await writeFile(path, "synthetic mock payload");
  process.env.OPENAI_API_KEY = "unit-test-key";
  let calls = 0;
  t.mock.method(globalThis, "fetch", async (url, request) => {
    assert.equal(url, "https://api.openai.com/v1/audio/transcriptions");
    assert.equal(request.headers.Authorization, "Bearer unit-test-key");
    assert.equal(request.body.get("model"), "gpt-4o-transcribe-diarize");
    assert.equal(request.body.get("language"), "vi");
    assert.equal(request.body.get("response_format"), "diarized_json");
    assert.equal(request.body.get("chunking_strategy"), "auto");
    assert.deepEqual(request.body.getAll("timestamp_granularities[]"), []);
    assert.equal(
      await request.body.get("file").text(),
      "synthetic mock payload",
    );
    return Response.json({ segments: [] });
  });
  const result = await transcribeWithDiarization(
    path,
    new AbortController().signal,
    async () => {
      calls++;
    },
  );
  assert.deepEqual(result, { segments: [] });
  assert.equal(calls, 1);
});

test("provider auth/quota errors do not retry or expose response text", async (t) => {
  const path = join(root, "fake.mp3");
  for (const [status, code, expected] of [
    [401, "invalid_api_key", "PROVIDER_AUTH_FAILED"],
    [429, "insufficient_quota", "PROVIDER_QUOTA_EXHAUSTED"],
  ]) {
    let calls = 0;
    const mock = t.mock.method(globalThis, "fetch", async () =>
      Response.json({ error: { code, message: "private" } }, { status }),
    );
    await assert.rejects(
      transcribeWithDiarization(
        path,
        new AbortController().signal,
        async () => {
          calls++;
        },
      ),
      { code: expected, message: expected },
    );
    assert.equal(calls, 1);
    mock.mock.restore();
  }
});

test("oversized provider audio fails before a request is made", async (t) => {
  const path = join(root, "oversized.mp3");
  await writeFile(path, "");
  await truncate(path, 24_000_000);
  let calls = 0;
  t.mock.method(globalThis, "fetch", async () => {
    calls++;
    return Response.json({});
  });
  await assert.rejects(
    transcribeWithDiarization(
      path,
      new AbortController().signal,
      async () => {},
    ),
    { code: "PROVIDER_FILE_TOO_LARGE" },
  );
  assert.equal(calls, 0);
});

test("transient errors retry at most three times and count each attempt", async (t) => {
  let calls = 0;
  t.mock.method(globalThis, "fetch", async () =>
    Response.json({}, { status: 503 }),
  );
  await assert.rejects(
    transcribeWithDiarization(
      join(root, "fake.mp3"),
      new AbortController().signal,
      async () => {
        calls++;
      },
    ),
    { code: "PROVIDER_UNAVAILABLE" },
  );
  assert.equal(calls, 3);
});

test("cancellation interrupts retries", async (t) => {
  let calls = 0;
  const controller = new AbortController();
  t.mock.method(globalThis, "fetch", async () => {
    controller.abort();
    return Response.json({}, { status: 503 });
  });
  await assert.rejects(
    transcribeWithDiarization(
      join(root, "fake.mp3"),
      controller.signal,
      async () => {
        calls++;
      },
    ),
  );
  assert.equal(calls, 1);
});

test("provider applies timeout to each request and counts retries", async (t) => {
  const previous = process.env.OPENAI_TIMEOUT_MS;
  process.env.OPENAI_TIMEOUT_MS = "5";
  let calls = 0;
  t.mock.method(
    globalThis,
    "fetch",
    async (_url, request) =>
      new Promise((_resolve, reject) => {
        request.signal.addEventListener(
          "abort",
          () => reject(request.signal.reason),
          { once: true },
        );
      }),
  );
  try {
    await assert.rejects(
      transcribeWithDiarization(
        join(root, "fake.mp3"),
        new AbortController().signal,
        async () => {
          calls++;
        },
      ),
      { code: "PROVIDER_UNAVAILABLE" },
    );
    assert.equal(calls, 3);
  } finally {
    if (previous === undefined) delete process.env.OPENAI_TIMEOUT_MS;
    else process.env.OPENAI_TIMEOUT_MS = previous;
  }
});
