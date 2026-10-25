import assert from "node:assert/strict";
import {
  access,
  copyFile,
  mkdtemp,
  readFile,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, join } from "node:path";
import { after, before, test } from "node:test";
import {
  inspectAudio,
  MAX_AUDIO_BYTES,
} from "../../dist/audio-test/audio/audio-inspection.js";
import {
  createSilentWav,
  generateAudioFixtures,
  writeFakeTool,
} from "./fixtures.mjs";

let directory;
let fixtures;

before(async () => {
  directory = await mkdtemp(join(tmpdir(), "meeting-audio-integration-"));
  fixtures = await generateAudioFixtures(directory);
});

after(async () => {
  await rm(directory, { recursive: true, force: true });
});

function inspect(filePath, originalName, mimeType, options) {
  return inspectAudio({ filePath, originalName, mimeType }, directory, options);
}

for (const [format, codec, sampleRate, mime] of [
  ["wav", "pcm_s16le", 16000, "audio/wav"],
  ["mp3", "mp3", 16000, "audio/mpeg"],
  ["m4a", "aac", 16000, "audio/mp4"],
  ["webm", "opus", 48000, "audio/webm"],
]) {
  test(`probes and fully decodes a real ${format} fixture`, async () => {
    const metadata = await inspect(fixtures[format], `sample.${format}`, mime);
    assert.equal(metadata.format, format);
    assert.equal(metadata.codec, codec);
    assert.equal(metadata.sample_rate, sampleRate);
    assert.equal(metadata.channels, 1);
    assert.equal(metadata.mime_type, mime);
    assert.equal(metadata.size_bytes, (await stat(fixtures[format])).size);
    assert.ok(metadata.duration_sec >= 0.45 && metadata.duration_sec < 0.7);
    assert.ok(!("filePath" in metadata));
  });
}

test("accepts missing/generic MIME, a WAV alias and uppercase extensions after checking content", async () => {
  for (const mime of [
    undefined,
    "application/octet-stream",
    "audio/x-wav; charset=utf-8",
  ]) {
    const metadata = await inspect(fixtures.wav, "recording.WAV", mime);
    assert.equal(metadata.mime_type, "audio/wav");
  }
});

test("rejects a renamed WAV and a renamed Matroska/Opus container", async () => {
  await assert.rejects(inspect(fixtures.wav, "fake.mp3"), {
    code: "UNSUPPORTED_AUDIO_FORMAT",
  });
  await assert.rejects(inspect(fixtures.mkv, "fake.webm"), {
    code: "UNSUPPORTED_AUDIO_FORMAT",
  });
});

test("rejects malformed bytes", async () => {
  const filePath = join(directory, "corrupt.wav");
  await writeFile(filePath, "this is not an audio file");
  await assert.rejects(inspect(filePath, "corrupt.wav"), {
    code: "INVALID_AUDIO",
  });
});

test("rejects a damaged AAC payload in an otherwise intact M4A container", async () => {
  const filePath = join(directory, "bad-aac.m4a");
  const data = await readFile(fixtures.m4a);
  const atom = data.indexOf(Buffer.from("mdat"));
  assert.ok(atom > 3);
  const atomSize = data.readUInt32BE(atom - 4);
  assert.ok(atomSize > 8 && atom - 4 + atomSize <= data.length);
  data.fill(0, atom + 4, atom - 4 + atomSize);
  await writeFile(filePath, data);
  await assert.rejects(inspect(filePath, "bad-aac.m4a"), {
    code: "INVALID_AUDIO",
  });
});

test("rejects video with audio, video without audio and multiple audio tracks", async () => {
  for (const [filePath, name] of [
    [fixtures.video, "video.webm"],
    [fixtures.noAudio, "no-audio.webm"],
    [fixtures.multiAudio, "multi.m4a"],
  ]) {
    await assert.rejects(inspect(filePath, name), { code: "INVALID_AUDIO" });
  }
});

test("accepts exactly 60 minutes and rejects a file over 60 minutes", async () => {
  const filePath = join(directory, "duration-boundary.wav");
  await createSilentWav(filePath, 3600 * 8000 * 2);
  assert.equal((await inspect(filePath, "limit.wav")).duration_sec, 3600);
  await createSilentWav(filePath, 3601 * 8000 * 2);
  await assert.rejects(inspect(filePath, "over-limit.wav"), {
    code: "AUDIO_TOO_LONG",
  });
});

test("accepts a valid file exactly at 100 MB", async () => {
  const filePath = join(directory, "size-boundary.wav");
  await createSilentWav(filePath, MAX_AUDIO_BYTES - 44, 25000);
  assert.equal(
    (await inspect(filePath, "limit.wav")).size_bytes,
    MAX_AUDIO_BYTES,
  );
});

test("does not interpret shell syntax in a server file path", async () => {
  const markerName = `${basename(directory)}-injected`;
  const marker = join(process.cwd(), markerName);
  const filePath = join(directory, `audio;$(touch ${markerName}).wav`);
  await copyFile(fixtures.wav, filePath);
  try {
    assert.equal((await inspect(filePath, "recording.wav")).format, "wav");
    await assert.rejects(access(marker), { code: "ENOENT" });
  } finally {
    await rm(marker, { force: true });
  }
});

test("reports missing decoder separately from invalid audio", async () => {
  await assert.rejects(
    inspect(fixtures.wav, "sample.wav", undefined, {
      ffmpegPath: join(directory, "nonexistent-ffmpeg"),
    }),
    { code: "AUDIO_TOOL_UNAVAILABLE", statusCode: 503 },
  );
});

test("bounds probing and decoding time instead of hanging a worker", async () => {
  const tool = join(directory, "slow-tool");
  await writeFakeTool(tool, "setInterval(() => {}, 1000);");
  await assert.rejects(
    inspect(fixtures.wav, "sample.wav", undefined, {
      ffprobePath: tool,
      probeTimeoutMs: 50,
    }),
    { code: "AUDIO_INSPECTION_TIMEOUT", statusCode: 503 },
  );
  await assert.rejects(
    inspect(fixtures.wav, "sample.wav", undefined, {
      ffmpegPath: tool,
      decodeTimeoutMs: 50,
    }),
    { code: "AUDIO_INSPECTION_TIMEOUT", statusCode: 503 },
  );
});

test("rejects missing duration and malformed probe output", async () => {
  const tool = join(directory, "fake-probe");
  await writeFakeTool(tool, 'console.log("not-json");');
  await assert.rejects(
    inspect(fixtures.wav, "sample.wav", undefined, { ffprobePath: tool }),
    {
      code: "INVALID_AUDIO",
    },
  );
  const output = {
    format: { format_name: "wav" },
    streams: [
      {
        codec_type: "audio",
        codec_name: "pcm_s16le",
        sample_rate: "16000",
        channels: 1,
      },
    ],
  };
  await writeFakeTool(
    tool,
    `console.log(${JSON.stringify(JSON.stringify(output))});`,
  );
  await assert.rejects(
    inspect(fixtures.wav, "sample.wav", undefined, { ffprobePath: tool }),
    {
      code: "INVALID_AUDIO",
    },
  );
});
