import "reflect-metadata";
import { test } from "node:test";
import assert from "node:assert/strict";
import { performance } from "node:perf_hooks";
import { NestFactory } from "@nestjs/core";
import { Module } from "@nestjs/common";
import { AppController } from "../../dist/app.controller.js";

// Before the slice exists, exercise the real baseline router: assertions fail on 404.
let slice;
try {
  slice = await import("../../dist/export/export.controller.js");
} catch (error) {
  if (error.code !== "ERR_MODULE_NOT_FOUND") throw error;
}
const rows = Array.from({ length: 10 }, (_, i) => ({
  id: `meeting-${i}`,
  title: `CANARY-${i}`,
  anchorDate: new Date("2026-11-13T00:00:00Z"),
}));
const verifier = {
  async verify(token) {
    const match = /^token-(\d)$/.exec(token);
    return match
      ? {
          id: `user-${match[1]}`,
          meetingIds: [`meeting-${match[1]}`, "missing"],
        }
      : null;
  },
};
async function serve(
  repository = {
    async findAuthorized(id, grants) {
      return grants.includes(id)
        ? (rows.find((row) => row.id === id) ?? null)
        : null;
    },
  },
) {
  class HarnessModule {}
  const providers = slice ? slice.exportProviders(verifier, repository) : [];
  Module({
    controllers: [slice?.ExportController ?? AppController],
    providers,
  })(HarnessModule);
  const app = await NestFactory.create(HarnessModule, { logger: false });
  await app.listen(0, "127.0.0.1");
  return { app, url: await app.getUrl() };
}
async function request(url, id = "meeting-0", token = "token-0") {
  const headers = token === null ? {} : { authorization: `Bearer ${token}` };
  const response = await fetch(`${url}/meetings/${id}/export`, {
    headers,
    signal: AbortSignal.timeout(10000),
  });
  return {
    status: response.status,
    headers: response.headers,
    body: await response.json(),
  };
}
await test("VT-059 HTTP export contract", async (t) => {
  const { app, url } = await serve();
  try {
    await t.test(
      "T01 authorized export, T04 excludes another meeting",
      async () => {
        const r = await request(url);
        assert.equal(r.status, 200);
        assert.deepEqual(r.body, {
          id: "meeting-0",
          title: "CANARY-0",
          anchor_date: "2026-11-13",
        });
        assert.ok(!JSON.stringify(r.body).includes("CANARY-1"));
      },
    );
    await t.test("T02 missing or invalid authentication", async () => {
      for (const token of [null, "invalid", ""])
        assert.equal((await request(url, "meeting-0", token)).status, 401);
    });
    await t.test(
      "T03/T08 denies another principal even with forged ownerId",
      async () => {
        const r = await request(url, "meeting-0?ownerId=user-0", "token-1");
        // Query strings belong after /export, so use a direct forged request too.
        const forged = await fetch(
          `${url}/meetings/meeting-0/export?ownerId=user-0`,
          { headers: { authorization: "Bearer token-1" } },
        );
        assert.equal(forged.status, 404);
        assert.ok(!(await forged.text()).includes("CANARY-0"));
        assert.equal((await request(url, "meeting-0", "token-1")).status, 404);
        assert.equal(r.status, 404);
      },
    );
    await t.test("T05 missing permitted record", async () =>
      assert.equal((await request(url, "missing")).status, 404),
    );
    await t.test("T11 rejects malformed ID", async () =>
      assert.equal((await request(url, "bad%20id")).status, 400),
    );
    await t.test(
      "T12 deterministic JSON and safe download headers",
      async () => {
        const a = await request(url);
        const b = await request(url);
        assert.equal(a.status, 200);
        assert.deepEqual(a.body, b.body);
        assert.match(a.headers.get("content-type"), /application\/json/);
        assert.equal(a.headers.get("cache-control"), "private, no-store");
        assert.equal(a.headers.get("x-content-type-options"), "nosniff");
        assert.equal(
          a.headers.get("content-disposition"),
          'attachment; filename="meeting-meeting-0.json"',
        );
      },
    );
    await t.test(
      "T09/T10 100 barrier-released mixed HTTP requests",
      async () => {
        let release;
        const barrier = new Promise((resolve) => {
          release = resolve;
        });
        let ready = 0;
        const tasks = Array.from({ length: 100 }, (_, i) =>
          (async () => {
            ready++;
            await barrier;
            const start = performance.now();
            const owner = i % 10;
            const kind = Math.floor(i / 10) % 5;
            const id = kind === 0 ? "missing" : `meeting-${owner}`;
            const token =
              kind === 1 ? `token-${(owner + 1) % 10}` : `token-${owner}`;
            const r = await request(url, id, token);
            const duration = performance.now() - start;
            const expected = kind < 2 ? 404 : 200;
            assert.equal(r.status, expected);
            if (expected === 200)
              assert.deepEqual(r.body, {
                id,
                title: `CANARY-${owner}`,
                anchor_date: "2026-11-13",
              });
            else assert.ok(!JSON.stringify(r.body).includes("CANARY"));
            return {
              task: i,
              expected,
              actual: r.status,
              duration,
              scopeMatch: true,
            };
          })(),
        );
        assert.equal(ready, 100);
        release();
        const samples = await Promise.all(tasks);
        const durations = samples.map((s) => s.duration).sort((a, b) => a - b);
        const p95 = durations[Math.ceil(0.95 * samples.length) - 1];
        console.log(
          JSON.stringify({
            mode: "loopback HTTP / contract fake, NOT production DB",
            n: 100,
            ready,
            p95,
            successes: samples.filter((s) => s.actual === 200).length,
            expectedDenials: samples.filter((s) => s.actual === 404).length,
            samples,
          }),
        );
        assert.ok(p95 <= 3000, `p95 ${p95} > 3000ms`);
      },
    );
  } finally {
    await app.close();
  }
});
await test("T06/T07 invalid adapter contracts and failures fail closed", async (t) => {
  for (const [name, repository] of [
    [
      "dependency throws",
      {
        async findAuthorized() {
          throw new Error("private dependency detail");
        },
      },
    ],
    [
      "wrong row",
      {
        async findAuthorized() {
          return rows[1];
        },
      },
    ],
    [
      "invalid date",
      {
        async findAuthorized() {
          return { ...rows[0], anchorDate: "2026-11-13" };
        },
      },
    ],
    [
      "invalid title",
      {
        async findAuthorized() {
          return { ...rows[0], title: null };
        },
      },
    ],
  ])
    await t.test(name, async () => {
      const { app, url } = await serve(repository);
      try {
        const r = await request(url);
        assert.equal(r.status, 503);
        assert.ok(!JSON.stringify(r.body).includes("CANARY"));
      } finally {
        await app.close();
      }
    });
  await t.test(
    "T08 grant validation independent of permissive adapter",
    async () => {
      const { app, url } = await serve({
        async findAuthorized() {
          return rows[0];
        },
      });
      try {
        assert.equal((await request(url, "meeting-0", "token-1")).status, 404);
      } finally {
        await app.close();
      }
    },
  );
});
