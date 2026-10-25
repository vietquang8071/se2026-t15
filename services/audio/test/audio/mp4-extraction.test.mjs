import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { mkdtemp, mkdir, readFile, readdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, before, test } from "node:test";
import {
  extractAudioFromMp4,
  inspectAudio,
} from "../../dist/audio-test/audio/audio-inspection.js";
import { generateAudioFixtures, writeFakeTool } from "./fixtures.mjs";

let root;
let uploads;
let output;
let fixtures;

before(async () => {
  root = await mkdtemp(join(tmpdir(), "meeting-mp4-"));
  uploads = join(root, "uploads");
  output = join(root, "processed");
  await mkdir(uploads);
  await mkdir(output);
  fixtures = await generateAudioFixtures(uploads);
});

after(async () => {
  await rm(root, { recursive: true, force: true });
});

function input(filePath, originalName = "meeting.mp4", mimeType = "video/mp4") {
  return { filePath, originalName, mimeType };
}

test("accepts MP4 video with one valid audio track", async () => {
  const metadata = await inspectAudio(input(fixtures.mp4), uploads);
  assert.equal(metadata.format, "mp4");
  assert.equal(metadata.mime_type, "video/mp4");
  assert.equal(metadata.codec, "aac");
  assert.equal(metadata.channels, 1);
  assert.equal(metadata.audio_start_sec, 0);
});

test("extracts a separate PCM WAV and leaves original MP4 bytes unchanged", async () => {
  const original = await readFile(fixtures.mp4);
  const result = await extractAudioFromMp4(
    input(fixtures.mp4),
    uploads,
    output,
  );
  assert.notEqual(result.filePath, fixtures.mp4);
  assert.equal(result.source.format, "mp4");
  assert.equal(result.metadata.format, "wav");
  assert.equal(result.metadata.codec, "pcm_s16le");
  assert.equal(result.metadata.sample_rate, 16000);
  assert.equal(result.metadata.channels, 1);
  assert.ok(
    result.metadata.duration_sec >= 0.45 && result.metadata.duration_sec < 0.7,
  );
  assert.deepEqual(await readFile(fixtures.mp4), original);
  const checked = await inspectAudio(
    { filePath: result.filePath, originalName: "extracted.wav" },
    output,
  );
  assert.deepEqual(checked, result.metadata);
});

test("preserves the audio start offset needed to map transcript times to the original video", async () => {
  const result = await extractAudioFromMp4(
    input(fixtures.offsetMp4),
    uploads,
    output,
  );
  const { stdout } = await promisify(execFile)("ffprobe", [
    "-v",
    "error",
    "-show_entries",
    "format=start_time:stream=codec_type,start_time",
    "-of",
    "json",
    fixtures.offsetMp4,
  ]);
  const probe = JSON.parse(stdout);
  const audio = probe.streams.find((stream) => stream.codec_type === "audio");
  const expected = Number(audio.start_time) - Number(probe.format.start_time);
  assert.ok(expected > 0);
  assert.equal(result.source_audio_start_sec, expected);
  assert.equal(result.source_audio_start_sec, result.source.audio_start_sec);
});

test("does not overwrite the output of a previous extraction", async () => {
  const first = await extractAudioFromMp4(input(fixtures.mp4), uploads, output);
  const previous = await readFile(first.filePath);
  const second = await extractAudioFromMp4(
    input(fixtures.mp4),
    uploads,
    output,
  );
  assert.notEqual(first.filePath, second.filePath);
  assert.deepEqual(await readFile(first.filePath), previous);
});

test("rejects MP4 without audio, multiple audio tracks, fake extensions and mismatched MIME", async () => {
  await assert.rejects(inspectAudio(input(fixtures.noAudioMp4), uploads), {
    code: "INVALID_AUDIO",
  });
  await assert.rejects(inspectAudio(input(fixtures.multiAudio), uploads), {
    code: "INVALID_AUDIO",
  });
  await assert.rejects(inspectAudio(input(fixtures.wav), uploads), {
    code: "UNSUPPORTED_AUDIO_FORMAT",
  });
  await assert.rejects(
    inspectAudio(input(fixtures.mp4, "video.mp4", "audio/wav"), uploads),
    { code: "UNSUPPORTED_AUDIO_FORMAT" },
  );
  await assert.rejects(
    inspectAudio(input(fixtures.mp4, "renamed.m4a", "audio/mp4"), uploads),
    { code: "INVALID_AUDIO" },
  );
});

test("supports audio-only MP4 containers without claiming that video is required", async () => {
  const result = await extractAudioFromMp4(
    input(fixtures.m4a),
    uploads,
    output,
  );
  assert.equal(result.source.format, "mp4");
  assert.equal(result.metadata.format, "wav");
});

test("rejects non-MP4 extraction and missing output storage", async () => {
  await assert.rejects(
    extractAudioFromMp4(
      input(fixtures.wav, "audio.wav", "audio/wav"),
      uploads,
      output,
    ),
    { code: "UNSUPPORTED_AUDIO_FORMAT" },
  );
  await assert.rejects(
    extractAudioFromMp4(
      input(fixtures.mp4),
      uploads,
      join(root, "missing-output"),
    ),
    { code: "AUDIO_EXTRACTION_FAILED", statusCode: 500 },
  );
});

test("removes intermediate output on extraction failure or timeout", async () => {
  const tool = join(root, "fake-decoder");
  const before = (await readdir(output)).sort();
  await writeFakeTool(
    tool,
    'process.exit(process.argv.includes("null") ? 0 : 1);',
  );
  await assert.rejects(
    extractAudioFromMp4(input(fixtures.mp4), uploads, output, {
      ffmpegPath: tool,
    }),
    { code: "AUDIO_EXTRACTION_FAILED" },
  );
  assert.deepEqual((await readdir(output)).sort(), before);

  await writeFakeTool(
    tool,
    'if (process.argv.includes("null")) process.exit(0); setInterval(() => {}, 1000);',
  );
  await assert.rejects(
    extractAudioFromMp4(input(fixtures.mp4), uploads, output, {
      ffmpegPath: tool,
      decodeTimeoutMs: 200,
    }),
    { code: "AUDIO_INSPECTION_TIMEOUT" },
  );
  assert.deepEqual((await readdir(output)).sort(), before);
});
