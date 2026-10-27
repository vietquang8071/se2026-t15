import "reflect-metadata";
import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { mkdtemp, readFile, readdir, rm, access } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomBytes } from "node:crypto";
import { setTimeout as delay } from "node:timers/promises";
import pg from "pg";
import { NestFactory } from "@nestjs/core";
import { AppModule } from "../../dist/app.module.js";
import { AudioService } from "../../dist/audio/audio.service.js";
import { generateAudioFixtures, createSilentWav } from "../audio/fixtures.mjs";

let app, service, base, root, fixtures, admin;
const database = `audio_test_${process.pid}_${randomBytes(4).toString("hex")}`;
const headers = { "X-API-Key": "audio-http-test-key-at-least-24-characters" };
const fakeProvider = async (_path, signal, beforeCall) => {
  signal.throwIfAborted();
  await beforeCall();
  return {
    segments: [{ speaker: "A", text: "Xin chào", start: 0.05, end: 0.4 }],
  };
};

async function start() {
  app = await NestFactory.create(AppModule, { logger: false });
  await app.listen(0, "127.0.0.1");
  service = app.get(AudioService);
  service.provider = fakeProvider;
  base = await app.getUrl();
}

before(async () => {
  root = await mkdtemp(join(tmpdir(), "audio-http-"));
  fixtures = await generateAudioFixtures(root);
  const url = new URL(
    process.env.AUDIO_DATABASE_URL ?? process.env.DATABASE_URL,
  );
  url.pathname = "/postgres";
  admin = new pg.Client({ connectionString: url.toString() });
  await admin.connect();
  await admin.query(`CREATE DATABASE "${database}"`);
  url.pathname = `/${database}`;
  process.env.AUDIO_DATABASE_URL = url.toString();
  process.env.AUDIO_STORAGE_DIR = join(root, "media");
  process.env.AUDIO_API_KEY = headers["X-API-Key"];
  process.env.OPENAI_API_KEY = "offline-test-no-real-provider";
  const db = new pg.Client({ connectionString: url.toString() });
  await db.connect();
  await db.query(
    await readFile(
      new URL(
        "../../prisma/migrations/20261025113317_init_audio_service/migration.sql",
        import.meta.url,
      ),
      "utf8",
    ),
  );
  await db.end();
  await start();
});

after(async () => {
  if (app) await app.close();
  if (admin) {
    await admin.query(`DROP DATABASE IF EXISTS "${database}" WITH (FORCE)`);
    await admin.end();
  }
  if (root) await rm(root, { recursive: true, force: true });
});

function request(path, options = {}) {
  return fetch(base + path, {
    ...options,
    headers: { ...headers, ...options.headers },
  });
}
async function upload(
  path = fixtures.wav,
  filename = "meeting.wav",
  retention = "30",
) {
  const form = new FormData();
  form.set("file", new Blob([await readFile(path)]), filename);
  if (retention !== undefined) form.set("retention_days", retention);
  return request("/api/audio", { method: "POST", body: form });
}
async function poll(id) {
  for (let i = 0; i < 100; i++) {
    const result = await (await request(`/api/audio/jobs/${id}`)).json();
    if (["completed", "failed"].includes(result.status)) return result;
    await delay(100);
  }
  throw new Error("job polling timeout");
}

test("audio service runs independently and rejects unauthenticated upload/metadata", async () => {
  assert.equal((await (await fetch(base + "/health")).json()).service, "audio");
  assert.equal((await fetch(base + "/api/audio/invalid")).status, 401);
  assert.equal(
    (await fetch(base + "/api/audio", { method: "POST" })).status,
    401,
  );
});

test("HTTP upload supports all five formats and persists UTC 30/60-day metadata without leaking storage paths", async () => {
  for (const extension of ["wav", "mp3", "m4a", "webm", "mp4"]) {
    const response = await upload(
      fixtures[extension],
      `meeting.${extension}`,
      "60",
    );
    assert.equal(response.status, 201);
    const data = await response.json();
    assert.equal(
      new Date(data.expires_at) - new Date(data.created_at),
      60 * 86400000,
    );
    assert.equal(data.source.format, extension);
    assert.ok(!JSON.stringify(data).includes(root));
    assert.equal((await request(`/api/audio/${data.audio_id}`)).status, 200);
    assert.equal(
      (await request(`/api/audio/${data.audio_id}`, { method: "DELETE" }))
        .status,
      204,
    );
  }
});

test("invalid retention, malformed media, missing file and invalid IDs have stable errors and no incoming leftovers", async () => {
  const beforeCount = await service.db.audioAsset.count();
  for (const retention of ["", "31", "30.0", "-1"])
    assert.equal((await upload(fixtures.wav, "x.wav", retention)).status, 400);
  assert.equal((await upload(fixtures.wav, "fake.mp3")).status, 415);
  assert.equal((await upload(fixtures.noAudioMp4, "silent.mp4")).status, 422);
  assert.equal((await request("/api/audio", { method: "POST" })).status, 400);
  assert.equal((await request("/api/audio/invalid")).status, 404);
  assert.equal(await service.db.audioAsset.count(), beforeCount);
  assert.deepEqual(await readdir(service.incoming), []);
});

test("MP4 audio start offset is applied exactly once to v2 segments", async () => {
  const uploaded = await (
    await upload(fixtures.offsetMp4, "offset.mp4")
  ).json();
  assert.ok(uploaded.source.audio_start_sec > 0);
  const path = `/api/audio/${uploaded.audio_id}`;
  const started = await (
    await request(path + "/process", { method: "POST" })
  ).json();
  const job = await poll(started.job_id);
  assert.equal(job.status, "completed", job.error);
  const transcript = await (await request(path + "/transcript")).json();
  assert.equal(transcript.schema_version, 2);
  assert.equal(
    transcript.source_audio_start_sec,
    uploaded.source.audio_start_sec,
  );
  assert.ok(
    Math.abs(
      transcript.segments[0].start - (0.05 + uploaded.source.audio_start_sec),
    ) < 1e-9,
  );
  assert.ok(
    Math.abs(
      transcript.segments[0].end - (0.4 + uploaded.source.audio_start_sec),
    ) < 1e-9,
  );
  await request(path, { method: "DELETE" });
});

test("HTTP honors the inclusive 100 MB limit and removes oversized temporary uploads", async () => {
  const source = join(root, "limit.wav");
  await createSilentWav(source, 100_000_000 - 44, 25000);
  const response = await upload(source, "limit.wav");
  assert.equal(response.status, 201);
  const asset = await response.json();
  assert.equal(asset.source.size_bytes, 100_000_000);
  await request(`/api/audio/${asset.audio_id}`, { method: "DELETE" });
  await createSilentWav(source, 100_000_002 - 44, 25000);
  assert.equal((await upload(source, "limit.wav")).status, 413);
  assert.deepEqual(await readdir(service.incoming), []);
  await rm(source);
});

test("process is idempotent, job completes, speaker edits persist and every export downloads", async () => {
  const uploaded = await (await upload()).json();
  const path = `/api/audio/${uploaded.audio_id}`;
  assert.equal((await request(path + "/transcript")).status, 409);
  const results = await Promise.all(
    Array.from({ length: 3 }, () =>
      request(path + "/process", { method: "POST" }).then((r) => r.json()),
    ),
  );
  assert.ok(results.every((r) => r.job_id === results[0].job_id));
  const job = await poll(results[0].job_id);
  assert.equal(job.status, "completed", job.error);
  assert.equal(job.provider_calls, 1);
  const transcript = await (await request(path + "/transcript")).json();
  assert.equal(transcript.text, "Xin chào");
  assert.equal(transcript.schema_version, 2);
  assert.equal("words" in transcript.segments[0], false);
  assert.equal(transcript.segments[0].speaker, "speaker_1");
  assert.equal(
    (
      await request(path + "/speakers/speaker_1", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "Sơn" }),
      })
    ).status,
    200,
  );
  assert.equal(
    (
      await request(path + "/speakers/speaker_1", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "\n" }),
      })
    ).status,
    400,
  );
  assert.equal(
    (await (await request(path + "/transcript")).json()).speakers[0].name,
    "Sơn",
  );
  for (const format of ["json", "txt", "srt", "md", "xlsx", "pdf"]) {
    const response = await request(path + `/export?format=${format}`);
    assert.equal(response.status, 200);
    assert.ok((await response.arrayBuffer()).byteLength > 0);
  }
  const range = await request(path + "/media", {
    headers: { Range: "bytes=0-15" },
  });
  assert.equal(range.status, 206);
  assert.equal((await range.arrayBuffer()).byteLength, 16);
  assert.equal((await request(path + "/media?variant=normalized")).status, 200);
  assert.equal(
    (
      await request(path + "/media", {
        headers: { Range: "bytes=1000000000-" },
      })
    ).status,
    416,
  );
  await app.close();
  app = undefined;
  await start();
  assert.equal(
    (await (await request(path + "/transcript")).json()).speakers[0].name,
    "Sơn",
  );
  assert.equal((await request(path, { method: "DELETE" })).status, 204);
  assert.equal(
    await service.db.audioJob.count({ where: { audioId: uploaded.audio_id } }),
    0,
  );
  await assert.rejects(access(join(service.root, uploaded.audio_id)));
});

test("retry reuses a persisted diarization checkpoint without another provider call", async () => {
  const uploaded = await (await upload()).json();
  const path = `/api/audio/${uploaded.audio_id}`;
  const asset = await service.db.audioAsset.findUniqueOrThrow({
    where: { id: uploaded.audio_id },
  });
  await service.db.audioAsset.update({
    where: { id: uploaded.audio_id },
    data: { metadata: { ...asset.metadata, audio_start_sec: 999 } },
  });
  const started = await (
    await request(path + "/process", { method: "POST" })
  ).json();
  const failed = await poll(started.job_id);
  assert.equal(failed.status, "failed");
  const checkpoint = await service.db.audioJob.findUnique({
    where: { id: started.job_id },
  });
  assert.ok(checkpoint.checkpoints.diarization);
  assert.equal(checkpoint.providerCalls, 1);
  await service.db.audioAsset.update({
    where: { id: uploaded.audio_id },
    data: { metadata: asset.metadata },
  });
  service.provider = async () => {
    throw new Error("provider must not be called");
  };
  await request(path + "/process", { method: "POST" });
  const job = await poll(started.job_id);
  assert.equal(job.status, "completed", job.error);
  assert.equal(job.provider_calls, 1);
  assert.equal(job.attempts, 2);
  service.provider = fakeProvider;
  await request(path, { method: "DELETE" });
});

test("expiry refuses transcript/media immediately and cleanup deletes transcript, jobs and files", async () => {
  const uploaded = await (await upload()).json();
  const path = `/api/audio/${uploaded.audio_id}`;
  await service.db.audioAsset.update({
    where: { id: uploaded.audio_id },
    data: {
      expiresAt: new Date(Date.now() - 1000),
      transcript: { private: "must disappear" },
    },
  });
  for (const suffix of ["", "/transcript", "/media", "/export?format=json"])
    assert.equal((await request(path + suffix)).status, 410);
  await service.cleanup();
  assert.equal(
    await service.db.audioAsset.count({ where: { id: uploaded.audio_id } }),
    0,
  );
  await assert.rejects(access(join(service.root, uploaded.audio_id)));
});

test("DELETE aborts active provider work and no output is resurrected", async () => {
  const uploaded = await (await upload()).json();
  const path = `/api/audio/${uploaded.audio_id}`;
  let entered;
  const running = new Promise((resolve) => {
    entered = resolve;
  });
  service.provider = async (_path, signal, beforeCall) => {
    await beforeCall();
    entered();
    await delay(60000, undefined, { signal });
  };
  await request(path + "/process", { method: "POST" });
  await Promise.race([
    running,
    delay(5000).then(() => {
      throw new Error("provider never started");
    }),
  ]);
  assert.equal((await request(path, { method: "DELETE" })).status, 204);
  service.provider = fakeProvider;
  await delay(100);
  assert.equal((await request(path + "/transcript")).status, 404);
  await assert.rejects(access(join(service.root, uploaded.audio_id)));
});

test("startup recovers an interrupted v2 job using its checkpoint", async () => {
  const uploaded = await (await upload()).json();
  const assetId = uploaded.audio_id;
  const job = await service.db.audioJob.create({
    data: {
      audioId: assetId,
      status: "running",
      stage: "building_transcript",
      attempts: 1,
      providerCalls: 1,
      checkpoints: {
        _configuration: JSON.stringify({
          version: 2,
          model: "gpt-4o-transcribe-diarize",
        }),
        diarization: {
          segments: [{ speaker: "A", text: "Xin chào", start: 0.05, end: 0.4 }],
        },
      },
    },
  });
  await app.close();
  app = undefined;
  await start();
  service.provider = async () => {
    throw new Error("checkpoint should be reused");
  };
  const result = await poll(job.id);
  assert.equal(result.status, "completed", result.error);
  assert.equal(result.provider_calls, 1);
  service.provider = fakeProvider;
  await request(`/api/audio/${assetId}`, { method: "DELETE" });
});

test("legacy unfinished checkpoints fail explicitly and preserve existing media and checkpoint", async () => {
  const uploaded = await (await upload()).json();
  const job = await service.db.audioJob.create({
    data: {
      audioId: uploaded.audio_id,
      status: "queued",
      checkpoints: { whisper_0: { text: "legacy" } },
    },
  });
  const result = await poll(job.id);
  assert.equal(result.status, "failed");
  assert.equal(result.error, "LEGACY_PIPELINE_CHECKPOINT");
  assert.equal(result.provider_calls, 0);
  const saved = await service.db.audioJob.findUnique({ where: { id: job.id } });
  assert.deepEqual(saved.checkpoints, { whisper_0: { text: "legacy" } });
  assert.equal(
    (await request(`/api/audio/${uploaded.audio_id}/media`)).status,
    200,
  );
  await request(`/api/audio/${uploaded.audio_id}`, { method: "DELETE" });
});

test("legacy failed and interrupted jobs keep their checkpoints when retried or recovered", async () => {
  for (const status of ["failed", "running"]) {
    const uploaded = await (await upload()).json();
    const path = `/api/audio/${uploaded.audio_id}`;
    const checkpoints = {
      _configuration: JSON.stringify({
        transcription: "whisper-1",
        diarization: "gpt-4o-transcribe-diarize",
        chunkSeconds: 600,
        overlapSeconds: 2,
      }),
      diarization: { segments: [] },
    };
    const job = await service.db.audioJob.create({
      data: {
        audioId: uploaded.audio_id,
        status,
        stage: "diarizing",
        attempts: 1,
        providerCalls: 2,
        checkpoints,
      },
    });
    if (status === "failed") {
      await request(path + "/process", { method: "POST" });
    } else {
      await app.close();
      app = undefined;
      await start();
    }
    const result = await poll(job.id);
    assert.equal(result.status, "failed");
    assert.equal(result.error, "LEGACY_PIPELINE_CHECKPOINT");
    assert.equal(result.provider_calls, 2);
    assert.deepEqual(
      (await service.db.audioJob.findUnique({ where: { id: job.id } }))
        .checkpoints,
      checkpoints,
    );
    assert.equal((await request(path + "/media")).status, 200);
    await request(path, { method: "DELETE" });
  }
});

test("historical completed version-1 transcript remains retrievable, renameable and exportable", async () => {
  const uploaded = await (await upload()).json();
  const path = `/api/audio/${uploaded.audio_id}`;
  const legacy = {
    schema_version: 1,
    audio_id: uploaded.audio_id,
    language: "vi",
    timeline: "source",
    source_audio_start_sec: 0,
    duration_sec: 1,
    text: "Xin chào",
    speakers: [{ id: "speaker_1", name: "speaker_1" }],
    segments: [
      {
        id: "SEG-0001",
        start: 0,
        end: 0.5,
        speaker: "speaker_1",
        text: "Xin chào",
        words: [{ word: "Xin", start: 0, end: 0.2, speaker: "speaker_1" }],
      },
    ],
    warnings: [],
    models: { transcription: "legacy", diarization: "legacy" },
  };
  await service.db.audioAsset.update({
    where: { id: uploaded.audio_id },
    data: { status: "completed", transcript: legacy },
  });
  await service.db.audioJob.create({
    data: {
      audioId: uploaded.audio_id,
      status: "completed",
      stage: "completed",
      checkpoints: { whisper_0: { text: "legacy" } },
    },
  });
  assert.deepEqual(await (await request(path + "/transcript")).json(), legacy);
  assert.equal(
    (
      await request(path + "/speakers/speaker_1", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "Sơn" }),
      })
    ).status,
    200,
  );
  for (const format of ["json", "txt", "srt", "md", "xlsx", "pdf"])
    assert.equal(
      (await request(path + `/export?format=${format}`)).status,
      200,
    );
  assert.equal(
    (await (await request(path + "/transcript")).json()).schema_version,
    1,
  );
  assert.equal(
    (await (await request(path + "/process", { method: "POST" })).json())
      .status,
    "completed",
  );
  await request(path, { method: "DELETE" });
});

test("configuration changes never reuse checkpoints from a different chunk/model layout", async () => {
  const uploaded = await (await upload()).json();
  const job = await service.db.audioJob.create({
    data: {
      audioId: uploaded.audio_id,
      status: "queued",
      checkpoints: { _configuration: "different-configuration" },
    },
  });
  const result = await poll(job.id);
  assert.equal(result.status, "failed");
  assert.equal(result.error, "JOB_CONFIGURATION_CHANGED");
  assert.equal(result.provider_calls, 0);
  await request(`/api/audio/${uploaded.audio_id}`, { method: "DELETE" });
});

test("job retry cap stops repeated paid processing", async () => {
  const uploaded = await (await upload()).json();
  await service.db.audioJob.create({
    data: { audioId: uploaded.audio_id, status: "failed", attempts: 3 },
  });
  const response = await request(`/api/audio/${uploaded.audio_id}/process`, {
    method: "POST",
  });
  assert.equal(response.status, 409);
  assert.equal((await response.json()).error.code, "JOB_RETRY_LIMIT");
  await request(`/api/audio/${uploaded.audio_id}`, { method: "DELETE" });
});

test("database session lock prevents two audio workers owning the same storage", async () => {
  const other = new pg.Client({
    connectionString: process.env.AUDIO_DATABASE_URL,
  });
  await other.connect();
  try {
    const result = await other.query(
      "SELECT pg_try_advisory_lock(202615,1) AS acquired",
    );
    assert.equal(result.rows[0].acquired, false);
  } finally {
    await other.end();
  }
});
