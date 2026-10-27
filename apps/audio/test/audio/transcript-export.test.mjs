import assert from "node:assert/strict";
import { test } from "node:test";
import ExcelJS from "exceljs";
import {
  buildTranscript,
  validateDiarization,
} from "../../dist/audio-test/audio/audio-transcript.js";
import {
  exportTranscript,
  markdown,
} from "../../dist/audio-test/audio/audio-export.js";

const turns = [
  { start: 3, end: 5, speaker: "speaker_9", text: "Vâng, em báo cáo." },
  { start: 0.5, end: 2, speaker: "speaker_7", text: "Chào mọi người!" },
  { start: 1.5, end: 2.5, speaker: "speaker_9", text: "Xin chào." },
  { start: 6, end: 7, speaker: "speaker_7", text: "Cảm ơn." },
  { start: 8, end: 9, speaker: "unknown", text: "Không rõ." },
];
const fixture = () =>
  buildTranscript("test", 12, 1, validateDiarization({ segments: turns }, 10));

test("preserves provider text, segment boundaries, overlap and deterministic speaker order", () => {
  const result = fixture();
  assert.equal(result.schema_version, 2);
  assert.deepEqual(
    result.segments.map((s) => [s.start, s.end, s.speaker, s.text]),
    [
      [1.5, 3, "speaker_1", "Chào mọi người!"],
      [2.5, 3.5, "speaker_2", "Xin chào."],
      [4, 6, "speaker_2", "Vâng, em báo cáo."],
      [7, 8, "speaker_1", "Cảm ơn."],
      [9, 10, "unknown", "Không rõ."],
    ],
  );
  assert.equal(
    result.text,
    "Chào mọi người!\nXin chào.\nVâng, em báo cáo.\nCảm ơn.\nKhông rõ.",
  );
  assert.ok(result.segments.every((s) => !("words" in s)));
  assert.deepEqual(result.models, {
    transcription_and_diarization: "gpt-4o-transcribe-diarize",
  });
});

test("empty transcript stays empty without inventing a speaker", () => {
  const result = buildTranscript(
    "a",
    10,
    0,
    validateDiarization({ text: "", segments: [] }, 10),
  );
  assert.deepEqual(result.segments, []);
  assert.deepEqual(result.speakers, []);
  assert.equal(result.text, "");
});

test("an explicit unassigned speaker does not consume a numbered speaker ID", () => {
  const data = validateDiarization(
    {
      segments: [
        { start: 0, end: 1, speaker: "unassigned", text: "Không rõ." },
        { start: 1.2, end: 2, speaker: "speaker_42", text: "Tôi đây." },
      ],
    },
    3,
  );
  const result = buildTranscript("a", 3, 0, data);
  assert.deepEqual(
    result.segments.map((segment) => segment.speaker),
    ["unknown", "speaker_1"],
  );
});

test("rejects malformed and out-of-bounds provider response", () => {
  const segment = { start: 0, end: 1, speaker: "A", text: "x" };
  for (const input of [
    null,
    {},
    { text: "speech", segments: [] },
    { segments: [null] },
    { segments: [{ ...segment, start: -1 }] },
    { segments: [{ ...segment, end: Infinity }] },
    { segments: [{ ...segment, start: 2 }] },
    { segments: [{ ...segment, end: 10.1 }] },
    { segments: [{ ...segment, speaker: "" }] },
    { segments: [{ ...segment, speaker: null }] },
    { segments: [{ ...segment, text: null }] },
  ]) {
    assert.throws(() => validateDiarization(input, 10), {
      code: "PROVIDER_INVALID_DIARIZATION",
    });
  }
  assert.throws(
    () =>
      buildTranscript(
        "a",
        10,
        2,
        validateDiarization({ segments: [{ ...segment, end: 9 }] }, 10),
      ),
    { code: "PROVIDER_INVALID_DIARIZATION" },
  );
  const rounded = buildTranscript(
    "a",
    10,
    0,
    validateDiarization({ segments: [{ ...segment, end: 10.01 }] }, 10),
  );
  assert.equal(rounded.segments[0].end, 10);
});

test("all v2 exports preserve Unicode, speaker rename and contain no word sheet", async () => {
  const transcript = fixture();
  transcript.speakers[0].name = "Nguyễn Huy Sơn";
  const json = JSON.parse(
    (await exportTranscript(transcript, "json")).toString(),
  );
  assert.equal(json.schema_version, 2);
  assert.equal(json.speakers[0].name, "Nguyễn Huy Sơn");
  assert.ok(!("words" in json.segments[0]));
  assert.match(
    (await exportTranscript(transcript, "txt")).toString(),
    /Nguyễn Huy Sơn: Chào mọi người!/,
  );
  assert.match(
    (await exportTranscript(transcript, "srt")).toString(),
    /00:00:01,500 --> 00:00:03,000\nNguyễn Huy Sơn/,
  );
  assert.match(markdown(transcript), /Nguyễn Huy Sơn/);
  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.load(await exportTranscript(transcript, "xlsx"));
  assert.deepEqual(
    workbook.worksheets.map((sheet) => sheet.name),
    ["Transcript", "Metadata"],
  );
  assert.equal(
    workbook.getWorksheet("Transcript").getRow(2).getCell(4).value,
    "Nguyễn Huy Sơn",
  );
  assert.equal(
    (await exportTranscript(transcript, "pdf")).subarray(0, 5).toString(),
    "%PDF-",
  );
  await assert.rejects(exportTranscript(transcript, "html"), {
    code: "INVALID_EXPORT_FORMAT",
  });
});

test("historical v1 transcript remains unchanged and exports its original words", async () => {
  const transcript = {
    ...fixture(),
    schema_version: 1,
    models: { transcription: "historical", diarization: "historical" },
    segments: [
      {
        id: "SEG-0001",
        start: 0,
        end: 1,
        speaker: "speaker_1",
        text: "Xin chào",
        words: [
          {
            word: "Xin",
            start: 0,
            end: 0.3,
            speaker: "speaker_1",
            speaker_attribution: "bridged_gap",
          },
        ],
      },
    ],
  };
  transcript.speakers[0].name = "Sơn";
  assert.match(markdown(transcript), /có từ suy ra/);
  for (const format of ["json", "txt", "srt", "md", "xlsx", "pdf"])
    assert.ok((await exportTranscript(transcript, format)).length > 0);
  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.load(await exportTranscript(transcript, "xlsx"));
  assert.deepEqual(
    workbook.worksheets.map((sheet) => sheet.name),
    ["Transcript", "Words", "Metadata"],
  );
  assert.equal(
    workbook.getWorksheet("Words").getRow(2).getCell(5).value,
    "Sơn",
  );
  assert.equal(
    JSON.parse((await exportTranscript(transcript, "json")).toString())
      .schema_version,
    1,
  );
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
