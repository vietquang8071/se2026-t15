import assert from "node:assert/strict";
import { test } from "node:test";
import ExcelJS from "exceljs";
import {
  buildTranscript,
  validateWhisper,
  validateDiarization,
} from "../../dist/audio-test/audio/audio-transcript.js";
import {
  exportTranscript,
  markdown,
} from "../../dist/audio-test/audio/audio-export.js";

const word = (word, start, end) => ({ word, start, end });
function fixture() {
  return buildTranscript(
    "00000000-0000-0000-0000-000000000001",
    20,
    2,
    [
      {
        chunk: { offset: 0, keepStart: 0, keepEnd: 10 },
        result: {
          words: [
            word("Xin", 1, 2),
            word("chào", 9, 9.5),
            word("trùng", 10.2, 10.5),
          ],
        },
      },
      {
        chunk: { offset: 8, keepStart: 10, keepEnd: 18 },
        result: {
          words: [
            word("trùng", 1, 1.5),
            word("bạn", 2.2, 2.5),
            word("Sơn", 3, 3.5),
          ],
        },
      },
    ],
    {
      segments: [
        { start: 0, end: 10, speaker: "A", text: "" },
        { start: 10, end: 18, speaker: "B", text: "" },
      ],
    },
  );
}

test("stitches chunk core intervals without duplicate overlap, adds source offset and maps speakers globally", () => {
  const result = fixture();
  assert.equal(
    result.segments.map((s) => s.text).join(" "),
    "Xin chào bạn Sơn",
  );
  assert.equal(result.segments[0].start, 3);
  assert.equal(result.segments.at(-1).speaker, "speaker_2");
  assert.equal(result.segments.at(-1).words.at(-1).end, 13.5);
  assert.equal(result.timeline, "source");
});

test("marks overlapping or uncovered speech unknown rather than guessing a speaker", () => {
  const result = buildTranscript(
    "a",
    10,
    0,
    [
      {
        chunk: { offset: 0, keepStart: 0, keepEnd: 10 },
        result: { words: [word("chồng", 1, 2), word("thiếu", 8, 9)] },
      },
    ],
    {
      segments: [
        { start: 0, end: 3, speaker: "A", text: "" },
        { start: 0, end: 3, speaker: "B", text: "" },
      ],
    },
  );
  assert.ok(result.segments.every((s) => s.speaker === "unknown"));
});

test("rejects missing, unsorted, non-finite or out-of-range timestamps", () => {
  for (const words of [
    [word("x", 2, 1)],
    [word("x", 0, Infinity)],
    [word("x", 0, 50)],
    [word("x", 2, 3), word("y", 1, 2)],
  ])
    assert.throws(() =>
      validateWhisper({ text: "x", segments: [], words }, 10),
    );
  assert.throws(() =>
    validateWhisper({ text: "hello", segments: [], words: [] }, 10),
  );
  assert.throws(() =>
    validateDiarization({ segments: [{ start: 0, end: 3, text: "x" }] }, 10),
  );
});

test("zero-duration word keeps its provider timestamp and gets a speaker only when a unique turn contains it", () => {
  const result = buildTranscript(
    "a",
    10,
    0,
    [
      {
        chunk: { offset: 0, keepStart: 0, keepEnd: 10 },
        result: { words: [word("một", 1, 1), word("hai", 3, 3)] },
      },
    ],
    {
      segments: [
        { start: 0, end: 5, speaker: "A", text: "" },
        { start: 2, end: 5, speaker: "B", text: "" },
      ],
    },
  );
  assert.equal(result.segments[0].speaker, "speaker_1");
  assert.equal(
    result.segments[0].words[0].start,
    result.segments[0].words[0].end,
  );
  assert.equal(result.segments[1].speaker, "unknown");
});

test("exports the same Vietnamese transcript to JSON/TXT/SRT/Markdown/Excel/PDF", async () => {
  const transcript = fixture();
  transcript.speakers[0].name = "Nguyễn Huy Sơn";
  assert.equal(
    JSON.parse((await exportTranscript(transcript, "json")).toString())
      .timeline,
    "source",
  );
  assert.match(
    (await exportTranscript(transcript, "txt")).toString(),
    /Nguyễn Huy Sơn/,
  );
  assert.match(
    (await exportTranscript(transcript, "srt")).toString(),
    /00:00:03,000 -->/,
  );
  assert.match(markdown(transcript), /Nguyễn Huy Sơn/);
  const excel = await exportTranscript(transcript, "xlsx");
  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.load(excel);
  assert.equal(
    workbook.getWorksheet("Transcript").getRow(2).getCell(4).value,
    "Nguyễn Huy Sơn",
  );
  assert.equal(workbook.getWorksheet("Words").rowCount, 5);
  const pdf = await exportTranscript(transcript, "pdf");
  assert.equal(pdf.subarray(0, 5).toString(), "%PDF-");
  await assert.rejects(exportTranscript(transcript, "html"), {
    code: "INVALID_EXPORT_FORMAT",
  });
});

test("Excel stores untrusted transcript text as a string, not a formula", async () => {
  const transcript = fixture();
  transcript.segments[0].text = '=HYPERLINK("http://example.com")';
  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.load(await exportTranscript(transcript, "xlsx"));
  assert.equal(
    typeof workbook.getWorksheet("Transcript").getRow(2).getCell(5).value,
    "string",
  );
});
