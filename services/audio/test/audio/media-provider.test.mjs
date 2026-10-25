import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { mkdtemp, rm, writeFile, stat } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { createSilentWav } from "./fixtures.mjs";
import {
  prepareAudio,
  createChunks,
} from "../../dist/audio-test/audio/audio-media.js";
import { transcribeFile } from "../../dist/audio-test/audio/audio-provider.js";

let root;
before(async () => {
  root = await mkdtemp(join(tmpdir(), "audio-media-"));
});
after(async () => {
  await rm(root, { recursive: true, force: true });
});

test("real FFmpeg normalization and multi-chunk encoding preserve duration and assign non-overlapping core intervals", async () => {
  const source = join(root, "source.wav");
  await createSilentWav(source, 12 * 8000 * 2);
  const original = process.env.AUDIO_CHUNK_SECONDS;
  process.env.AUDIO_CHUNK_SECONDS = "5";
  try {
    const prepared = await prepareAudio(
      source,
      join(root, "prepared"),
      new AbortController().signal,
    );
    assert.equal(prepared.duration, 12);
    const chunks = await createChunks(
      prepared.wav,
      join(root, "prepared"),
      prepared.duration,
      new AbortController().signal,
    );
    assert.deepEqual(
      chunks.map((c) => [c.keepStart, c.keepEnd]),
      [
        [0, 5],
        [5, 10],
        [10, 12],
      ],
    );
    assert.deepEqual(
      chunks.map((c) => c.offset),
      [0, 3, 8],
    );
    for (const chunk of chunks)
      assert.ok((await stat(chunk.path)).size < 24000000);
  } finally {
    if (original === undefined) delete process.env.AUDIO_CHUNK_SECONDS;
    else process.env.AUDIO_CHUNK_SECONDS = original;
  }
});

test("OpenAI multipart requests specify word/segment timestamps and separate full-recording diarization", async (t) => {
  const path = join(root, "fake.mp3");
  await writeFile(path, "synthetic mock payload");
  process.env.OPENAI_API_KEY = "";
  process.env.OpenAI_API_KEY = "unit-test-key";
  const calls = [];
  let count = 0;
  t.mock.method(globalThis, "fetch", async (url, request) => {
    assert.equal(url, "https://api.openai.com/v1/audio/transcriptions");
    assert.equal(request.headers.Authorization, "Bearer unit-test-key");
    calls.push(request.body);
    return Response.json({ text: "test" });
  });
  for (const kind of ["whisper", "diarization"])
    await transcribeFile(path, kind, new AbortController().signal, async () => {
      count++;
    });
  assert.equal(count, 2);
  assert.deepEqual(calls[0].getAll("timestamp_granularities[]"), [
    "segment",
    "word",
  ]);
  assert.equal(calls[1].get("response_format"), "diarized_json");
  assert.equal(calls[1].get("chunking_strategy"), "auto");
});

test("OpenAI auth/quota failures never retry and do not expose provider error text", async (t) => {
  const path = join(root, "fake.mp3");
  for (const [status, code, expected] of [
    [401, "invalid_api_key", "PROVIDER_AUTH_FAILED"],
    [429, "insufficient_quota", "PROVIDER_QUOTA_EXHAUSTED"],
  ]) {
    let calls = 0;
    const mock = t.mock.method(globalThis, "fetch", async () =>
      Response.json(
        { error: { code, message: "private provider text" } },
        { status },
      ),
    );
    await assert.rejects(
      transcribeFile(
        path,
        "whisper",
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

test("transient OpenAI errors retry with a fixed upper bound and count every attempt", async (t) => {
  let calls = 0;
  t.mock.method(globalThis, "fetch", async () =>
    Response.json({}, { status: 503 }),
  );
  await assert.rejects(
    transcribeFile(
      join(root, "fake.mp3"),
      "whisper",
      new AbortController().signal,
      async () => {
        calls++;
      },
    ),
    { code: "PROVIDER_UNAVAILABLE" },
  );
  assert.equal(calls, 3);
});

test("cancellation interrupts retry backoff instead of making another paid call", async (t) => {
  let calls = 0;
  const controller = new AbortController();
  t.mock.method(globalThis, "fetch", async () => {
    controller.abort();
    return Response.json({}, { status: 503 });
  });
  await assert.rejects(
    transcribeFile(
      join(root, "fake.mp3"),
      "whisper",
      controller.signal,
      async () => {
        calls++;
      },
    ),
  );
  assert.equal(calls, 1);
});
