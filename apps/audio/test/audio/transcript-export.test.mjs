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

test("bridges a short gap between turns of the same speaker and marks inferred words", () => {
  const result = buildTranscript(
    "a",
    10,
    0,
    [
      {
        chunk: { offset: 0, keepStart: 0, keepEnd: 10 },
        result: {
          words: [
            word("hay", 1.2, 1.32),
            word("không", 1.32, 1.44),
            word("ạ", 1.44, 2.18),
            word("tiếp", 2.5, 2.7),
          ],
        },
      },
    ],
    {
      segments: [
        { start: 0, end: 1.374, speaker: "A", text: "" },
        { start: 1.94, end: 4, speaker: "A", text: "" },
      ],
    },
  );
  assert.equal(result.segments.length, 1);
  assert.equal(result.segments[0].text, "hay không ạ tiếp");
  assert.equal(result.segments[0].speaker, "speaker_1");
  assert.deepEqual(
    result.segments[0].words.map((item) => item.speaker_attribution),
    [undefined, "bridged_gap", "bridged_gap", undefined],
  );
  assert.match(result.warnings.join(" "), /nối khoảng trống/);
  assert.match(markdown(result), /speaker\\_1 \(có từ suy ra\)/);
});

test("does not bridge long gaps, different speakers or overlapping speech", () => {
  const cases = [
    [
      { start: 0, end: 1, speaker: "A" },
      { start: 2, end: 4, speaker: "A" },
    ],
    [
      { start: 0, end: 1, speaker: "A" },
      { start: 1.6, end: 4, speaker: "B" },
    ],
    [
      { start: 0, end: 1, speaker: "A" },
      { start: 0.9, end: 1.25, speaker: "B" },
      { start: 1.6, end: 4, speaker: "A" },
    ],
    [
      { start: 0, end: 1, speaker: "A" },
      { start: 0.8, end: 1.1, speaker: "B" },
      { start: 1.6, end: 4, speaker: "A" },
    ],
  ];
  for (const turns of cases) {
    const result = buildTranscript(
      "a",
      10,
      0,
      [
        {
          chunk: { offset: 0, keepStart: 0, keepEnd: 10 },
          result: { words: [word("x", 1.2, 1.4)] },
        },
      ],
      { segments: turns.map((turn) => ({ ...turn, text: "" })) },
    );
    assert.equal(result.segments[0].speaker, "unknown");
    assert.equal(result.segments[0].words[0].speaker_attribution, undefined);
  }
});

test("bridges a zero-duration word in the gap without changing its timestamp", () => {
  const result = buildTranscript(
    "a",
    10,
    0,
    [
      {
        chunk: { offset: 0, keepStart: 0, keepEnd: 10 },
        result: { words: [word("x", 1.3, 1.3)] },
      },
    ],
    {
      segments: [
        { start: 0, end: 1, speaker: "A", text: "" },
        { start: 1.6, end: 4, speaker: "A", text: "" },
      ],
    },
  );
  assert.deepEqual(result.segments[0].words[0], {
    word: "x",
    start: 1.3,
    end: 1.3,
    speaker: "speaker_1",
    speaker_attribution: "bridged_gap",
  });
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
