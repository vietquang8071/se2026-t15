import "reflect-metadata";
import { test } from "node:test";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import { performance } from "node:perf_hooks";
import { NestFactory } from "@nestjs/core";
import { Module } from "@nestjs/common";
import { createPrismaClient } from "@meeting-minutes/database";
import { PrismaMeetingRepository } from "../../dist/export/prisma-meeting.repository.js";
import {
  ExportController,
  exportProviders,
} from "../../dist/export/export.controller.js";

const connection = process.env.VT059_DATABASE_URL;
await test(
  "T07 real Prisma/PostgreSQL contract and 100-task HTTP batch",
  { skip: !connection, timeout: 30000 },
  async () => {
    // Never default to DATABASE_URL or mutate an existing development database.
    const target = new URL(connection);
    assert.equal(target.hostname, "127.0.0.1");
    assert.equal(target.pathname, "/vt059");
    assert.ok(
      target.port && target.port !== "5432",
      "use an isolated ephemeral test port",
    );
    const client = createPrismaClient(connection);
    const prefix = `vt059-${randomUUID()}`;
    const fixtures = Array.from({ length: 60 }, (_, i) => ({
      id: `${prefix}-${i}`,
      title: `DB-CANARY-${i}`,
      anchorDate: new Date("2026-11-13T00:00:00Z"),
    }));
    let app;
    try {
      const migration = await readFile(
        new URL(
          "../../../../packages/database/prisma/migrations/20261025093739_init/migration.sql",
          import.meta.url,
        ),
        "utf8",
      );
      await client.$executeRawUnsafe(
        migration.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS "),
      );
      await client.meeting.createMany({ data: fixtures });
      const repository = new PrismaMeetingRepository(client);
      const row = await repository.findAuthorized(fixtures[0].id, [
        fixtures[0].id,
      ]);
      assert.deepEqual(row, {
        id: fixtures[0].id,
        title: "DB-CANARY-0",
        anchorDate: new Date("2026-11-13T00:00:00Z"),
      });
      assert.equal(
        await repository.findAuthorized(fixtures[0].id, [fixtures[1].id]),
        null,
      );
      assert.equal(await repository.findAuthorized(fixtures[0].id, []), null);
      assert.equal(
        await repository.findAuthorized(`${prefix}-absent`, [
          `${prefix}-absent`,
        ]),
        null,
      );
      // Multiple allowed rows must not broaden requested-ID scope.
      assert.deepEqual(
        await repository.findAuthorized(
          fixtures[0].id,
          fixtures.slice(0, 3).map((f) => f.id),
        ),
        row,
      );
      const verifier = {
        async verify(token) {
          const match = /^db-token-(\d+)$/.exec(token);
          const owner = Number(match?.[1]);
          if (!match || owner < 0 || owner >= 20) return null;
          return {
            id: `db-user-${owner}`,
            meetingIds: [
              ...fixtures.slice(owner * 3, owner * 3 + 3).map((f) => f.id),
              `${prefix}-absent`,
            ],
          };
        },
      };
      class DatabaseHarness {}
      Module({
        controllers: [ExportController],
        providers: exportProviders(verifier, repository),
      })(DatabaseHarness);
      app = await NestFactory.create(DatabaseHarness, { logger: false });
      await app.listen(0, "127.0.0.1");
      const url = await app.getUrl();
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
          const owner = i % 20;
          const kind = Math.floor(i / 20);
          const index = owner * 3 + (i % 3);
          const id = kind === 0 ? `${prefix}-absent` : fixtures[index].id;
          const principal = kind === 1 ? (owner + 1) % 20 : owner;
          const r = await fetch(`${url}/meetings/${id}/export`, {
            headers: { authorization: `Bearer db-token-${principal}` },
            signal: AbortSignal.timeout(10000),
          });
          const body = await r.json();
          const duration = performance.now() - start;
          const expected = kind < 2 ? 404 : 200;
          assert.equal(r.status, expected);
          if (expected === 200)
            assert.deepEqual(body, {
              id,
              title: `DB-CANARY-${index}`,
              anchor_date: "2026-11-13",
            });
          else assert.ok(!JSON.stringify(body).includes("DB-CANARY"));
          return {
            task: i,
            principal,
            expectedId: id,
            actualId: body.id ?? null,
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
          mode: "loopback Nest HTTP + real Prisma/PostgreSQL; synthetic verifier/grants",
          n: 100,
          ready,
          p95,
          successes: 60,
          expectedDenials: 40,
          samples,
        }),
      );
      assert.ok(p95 <= 3000, `p95 ${p95} > 3000ms`);
    } finally {
      if (app) await app.close();
      await client.meeting.deleteMany({
        where: { id: { in: fixtures.map((f) => f.id) } },
      });
      await client.$disconnect();
    }
  },
);
