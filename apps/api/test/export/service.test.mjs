import "reflect-metadata";
import { test } from "node:test";
import assert from "node:assert/strict";
import { ExportService } from "../../dist/export/export.service.js";

await test("unit: fail closed at verifier and persistence boundaries", async (t) => {
  const row = {
    id: "meeting-0",
    title: "CANARY-0",
    anchorDate: new Date("2026-11-13T00:00:00Z"),
  };
  const principal = { id: "user-0", meetingIds: ["meeting-0"] };
  for (const [name, verify, value, expected] of [
    [
      "verifier failure",
      async () => {
        throw new Error("secret");
      },
      row,
      503,
    ],
    ["missing identity", async () => ({ meetingIds: ["meeting-0"] }), row, 401],
    [
      "invalid grants",
      async () => ({ id: "user-0", meetingIds: [1] }),
      row,
      401,
    ],
    ["missing grants", async () => ({ id: "user-0" }), row, 401],
    ["undefined row", async () => principal, undefined, 503],
    ["array row", async () => principal, [row], 503],
    [
      "invalid Date",
      async () => principal,
      { ...row, anchorDate: new Date("invalid") },
      503,
    ],
    [
      "missing id",
      async () => principal,
      { title: row.title, anchorDate: row.anchorDate },
      503,
    ],
    [
      "missing title",
      async () => principal,
      { id: row.id, anchorDate: row.anchorDate },
      503,
    ],
    [
      "missing anchor date",
      async () => principal,
      { id: row.id, title: row.title },
      503,
    ],
  ])
    await t.test(name, async () => {
      const service = new ExportService(
        { verify },
        {
          async findAuthorized() {
            return value;
          },
        },
      );
      await assert.rejects(
        service.download("Bearer valid", "meeting-0"),
        (e) => e.getStatus() === expected,
      );
    });
});
