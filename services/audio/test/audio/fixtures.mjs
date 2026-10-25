import { execFile } from "node:child_process";
import { truncate, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { promisify } from "node:util";

const run = promisify(execFile);

export async function generateAudioFixtures(directory) {
  const fixtures = {};
  for (const [format, codec] of [
    ["wav", "pcm_s16le"],
    ["mp3", "libmp3lame"],
    ["m4a", "aac"],
    ["webm", "libopus"],
    ["mkv", "libopus"],
  ]) {
    const filePath = join(directory, `tone.${format}`);
    await ffmpeg([
      "-f",
      "lavfi",
      "-i",
      "sine=frequency=440:sample_rate=16000:duration=0.5",
      "-c:a",
      codec,
      filePath,
    ]);
    fixtures[format] = filePath;
  }

  fixtures.video = join(directory, "video.webm");
  await ffmpeg([
    "-f",
    "lavfi",
    "-i",
    "color=black:size=16x16:rate=10:duration=0.2",
    "-f",
    "lavfi",
    "-i",
    "sine=frequency=440:duration=0.2",
    "-c:v",
    "libvpx-vp9",
    "-c:a",
    "libopus",
    "-shortest",
    fixtures.video,
  ]);
  fixtures.noAudio = join(directory, "silent-video.webm");
  await ffmpeg([
    "-f",
    "lavfi",
    "-i",
    "color=black:size=16x16:rate=10:duration=0.2",
    "-c:v",
    "libvpx-vp9",
    fixtures.noAudio,
  ]);
  fixtures.multiAudio = join(directory, "multi.m4a");
  await ffmpeg([
    "-f",
    "lavfi",
    "-i",
    "sine=frequency=440:sample_rate=16000:duration=0.2",
    "-map",
    "0:a",
    "-map",
    "0:a",
    "-c:a",
    "aac",
    fixtures.multiAudio,
  ]);
  fixtures.mp4 = join(directory, "video.mp4");
  await ffmpeg([
    "-f",
    "lavfi",
    "-i",
    "color=black:size=16x16:rate=10:duration=0.5",
    "-f",
    "lavfi",
    "-i",
    "sine=frequency=440:sample_rate=16000:duration=0.5",
    "-c:v",
    "libx264",
    "-c:a",
    "aac",
    "-shortest",
    fixtures.mp4,
  ]);
  fixtures.noAudioMp4 = join(directory, "no-audio.mp4");
  await ffmpeg([
    "-f",
    "lavfi",
    "-i",
    "color=black:size=16x16:rate=10:duration=0.2",
    "-c:v",
    "libx264",
    fixtures.noAudioMp4,
  ]);
  fixtures.offsetMp4 = join(directory, "offset.mp4");
  await ffmpeg([
    "-f",
    "lavfi",
    "-i",
    "color=black:size=16x16:rate=10:duration=1",
    "-itsoffset",
    "0.25",
    "-f",
    "lavfi",
    "-i",
    "sine=frequency=440:sample_rate=16000:duration=0.5",
    "-c:v",
    "libx264",
    "-c:a",
    "aac",
    "-shortest",
    fixtures.offsetMp4,
  ]);
  return fixtures;
}

async function ffmpeg(args) {
  await run("ffmpeg", ["-nostdin", "-v", "error", "-y", ...args], {
    timeout: 10_000,
    maxBuffer: 256 * 1024,
  });
}

export async function createSilentWav(filePath, dataBytes, sampleRate = 8000) {
  const header = Buffer.alloc(44);
  header.write("RIFF", 0);
  header.writeUInt32LE(dataBytes + 36, 4);
  header.write("WAVEfmt ", 8);
  header.writeUInt32LE(16, 16);
  header.writeUInt16LE(1, 20);
  header.writeUInt16LE(1, 22);
  header.writeUInt32LE(sampleRate, 24);
  header.writeUInt32LE(sampleRate * 2, 28);
  header.writeUInt16LE(2, 32);
  header.writeUInt16LE(16, 34);
  header.write("data", 36);
  header.writeUInt32LE(dataBytes, 40);
  await writeFile(filePath, header);
  await truncate(filePath, dataBytes + header.length);
}

export async function writeFakeTool(filePath, script) {
  await writeFile(filePath, `#!${process.execPath}\n${script}\n`, {
    mode: 0o755,
  });
}
