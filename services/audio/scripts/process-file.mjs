import { mkdir, readFile, writeFile } from "node:fs/promises";
import { basename, resolve, join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const [file, destination = "artifacts/private/audio-result", retention = "30"] =
  process.argv.slice(2);
if (!file)
  throw new Error(
    "Usage: pnpm audio:file /path/to/audio [output-directory] [30|60]",
  );
const base =
  process.env.AUDIO_BASE_URL ??
  `http://127.0.0.1:${process.env.AUDIO_PORT ?? 3002}`;
const headers = { "X-API-Key": process.env.AUDIO_API_KEY ?? "" };
async function request(path, options = {}) {
  const response = await fetch(base + path, {
    ...options,
    headers: { ...headers, ...options.headers },
    signal: AbortSignal.timeout(180_000),
  });
  if (!response.ok)
    throw new Error(`HTTP ${response.status}: ${await response.text()}`);
  return response;
}
let uploaded;
if (file.startsWith("audio:")) {
  uploaded = await (await request(`/api/audio/${file.slice(6)}`)).json();
} else {
  const form = new FormData();
  form.set("file", new Blob([await readFile(file)]), basename(file));
  form.set("retention_days", retention);
  uploaded = await (
    await request("/api/audio", { method: "POST", body: form })
  ).json();
}
console.log(`audio_id: ${uploaded.audio_id}`);
const started = await (
  await request(`/api/audio/${uploaded.audio_id}/process`, { method: "POST" })
).json();
let job;
const deadline = Date.now() + 30 * 60_000;
let lastStage;
do {
  if (Date.now() > deadline)
    throw new Error(
      `Polling timed out; job ${started.job_id} continues on the server`,
    );
  await delay(2000);
  job = await (await request(`/api/audio/jobs/${started.job_id}`)).json();
  if (job.stage !== lastStage) console.log(`${job.stage}: ${job.progress}%`);
  lastStage = job.stage;
  if (job.status === "failed")
    throw new Error(`Job failed: ${job.error}; audio_id=${uploaded.audio_id}`);
} while (job.status !== "completed");
const output = resolve(destination);
await mkdir(output, { recursive: true });
for (const format of ["json", "txt", "srt", "md", "xlsx", "pdf"]) {
  const response = await request(
    `/api/audio/${uploaded.audio_id}/export?format=${format}`,
  );
  await writeFile(
    join(output, `transcript.${format}`),
    Buffer.from(await response.arrayBuffer()),
  );
}
await writeFile(
  join(output, "metadata.json"),
  JSON.stringify({ uploaded, job }, null, 2),
);
console.log(`Completed: ${output}; provider calls: ${job.provider_calls}`);
