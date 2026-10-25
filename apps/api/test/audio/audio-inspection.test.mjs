import assert from "node:assert/strict";
import {
  mkdtemp,
  mkdir,
  rm,
  symlink,
  truncate,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, before, test } from "node:test";
import {
  AudioInspectionError,
  inspectAudio,
  MAX_AUDIO_BYTES,
} from "../../dist/audio-test/audio/audio-inspection.js";

let root;
let uploadDirectory;

before(async () => {
  root = await mkdtemp(join(tmpdir(), "meeting-audio-unit-"));
  uploadDirectory = join(root, "uploads");
  await mkdir(uploadDirectory);
});

after(async () => {
  await rm(root, { recursive: true, force: true });
});

function expectCode(code, statusCode) {
  return (error) => {
    assert.ok(error instanceof AudioInspectionError);
    assert.equal(error.code, code);
    assert.equal(error.statusCode, statusCode);
    assert.ok(!error.message.includes(root));
    return true;
  };
}

test("rejects a missing file without leaking the path", async () => {
  await assert.rejects(
    inspectAudio(
      { filePath: join(uploadDirectory, "missing"), originalName: "test.wav" },
      uploadDirectory,
    ),
    expectCode("INVALID_AUDIO_PATH", 400),
  );
});

test("rejects a directory", async () => {
  const filePath = join(uploadDirectory, "directory");
  await mkdir(filePath);
  await assert.rejects(
    inspectAudio({ filePath, originalName: "test.wav" }, uploadDirectory),
    expectCode("INVALID_AUDIO_PATH", 400),
  );
});

test("rejects a file outside upload root and a symlink pointing outside", async () => {
  const outside = join(root, "outside.wav");
  await writeFile(outside, "not audio");
  const link = join(uploadDirectory, "linked.wav");
  await symlink(outside, link);
  for (const filePath of [outside, link]) {
    await assert.rejects(
      inspectAudio({ filePath, originalName: "test.wav" }, uploadDirectory),
      expectCode("INVALID_AUDIO_PATH", 400),
    );
  }
});

test("rejects empty and oversized files before running audio tools", async () => {
  const filePath = join(uploadDirectory, "size.wav");
  await writeFile(filePath, "");
  await assert.rejects(
    inspectAudio({ filePath, originalName: "test.wav" }, uploadDirectory),
    expectCode("EMPTY_AUDIO", 400),
  );
  await truncate(filePath, MAX_AUDIO_BYTES + 1);
  await assert.rejects(
    inspectAudio({ filePath, originalName: "test.wav" }, uploadDirectory),
    expectCode("AUDIO_TOO_LARGE", 413),
  );
});

test("rejects unsupported extensions and specific MIME mismatches", async () => {
  const filePath = join(uploadDirectory, "payload");
  await writeFile(filePath, "not audio");
  for (const [originalName, mimeType] of [
    ["test.exe", "audio/wav"],
    ["test.wav", "video/mp4"],
  ]) {
    await assert.rejects(
      inspectAudio({ filePath, originalName, mimeType }, uploadDirectory),
      expectCode("UNSUPPORTED_AUDIO_FORMAT", 415),
    );
  }
});

test("reports missing FFprobe as an infrastructure error", async () => {
  const filePath = join(uploadDirectory, "tool.wav");
  await writeFile(filePath, "not audio");
  await assert.rejects(
    inspectAudio({ filePath, originalName: "test.wav" }, uploadDirectory, {
      ffprobePath: join(root, "nonexistent-ffprobe"),
    }),
    expectCode("AUDIO_TOOL_UNAVAILABLE", 503),
  );
});
