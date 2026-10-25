import ExcelJS from "exceljs";
import PDFDocument from "pdfkit";
import { access } from "node:fs/promises";
import { AudioServiceError } from "./audio-types.js";
import type { AudioTranscript } from "./audio-types.js";

export const exportTypes: Record<string, string> = {
  json: "application/json",
  txt: "text/plain; charset=utf-8",
  srt: "application/x-subrip; charset=utf-8",
  md: "text/markdown; charset=utf-8",
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  pdf: "application/pdf",
};

export function timestamp(seconds: number, srt = false) {
  const ms = Math.round(seconds * 1000);
  return `${String(Math.floor(ms / 3600000)).padStart(2, "0")}:${String(Math.floor(ms / 60000) % 60).padStart(2, "0")}:${String(Math.floor(ms / 1000) % 60).padStart(2, "0")}${srt ? "," : "."}${String(ms % 1000).padStart(3, "0")}`;
}

function speakerName(transcript: AudioTranscript, id: string) {
  return transcript.speakers.find((speaker) => speaker.id === id)?.name ?? id;
}

function escapeMarkdown(text: string) {
  return text.replace(/[\\`*_{}\[\]<>#!|]/g, "\\$&");
}

export function markdown(transcript: AudioTranscript) {
  return [
    "# Bản chép lời",
    "",
    `Audio: ${transcript.audio_id}`,
    "Ngôn ngữ: tiếng Việt",
    "Timeline: file nguồn",
    "",
    "## Người nói",
    "",
    ...transcript.speakers.map(
      (speaker) => `- ${speaker.id}: ${escapeMarkdown(speaker.name)}`,
    ),
    "",
    "## Nội dung",
    "",
    ...transcript.segments.flatMap((segment) => [
      `### ${timestamp(segment.start)} → ${timestamp(segment.end)} — ${escapeMarkdown(speakerName(transcript, segment.speaker))}`,
      "",
      escapeMarkdown(segment.text),
      "",
    ]),
    "## Lưu ý",
    "",
    ...transcript.warnings.map((warning) => `- ${escapeMarkdown(warning)}`),
    "",
  ].join("\n");
}

export async function exportTranscript(
  transcript: AudioTranscript,
  format: string,
): Promise<Buffer> {
  if (!exportTypes[format])
    throw new AudioServiceError("INVALID_EXPORT_FORMAT", 400);
  if (format === "json")
    return Buffer.from(JSON.stringify(transcript, null, 2));
  if (format === "md") return Buffer.from(markdown(transcript));
  if (format === "txt")
    return Buffer.from(
      transcript.segments
        .map(
          (segment) =>
            `[${timestamp(segment.start)}] ${speakerName(transcript, segment.speaker)}: ${segment.text}`,
        )
        .join("\n"),
    );
  if (format === "srt")
    return Buffer.from(
      transcript.segments
        .map(
          (segment, i) =>
            `${i + 1}\n${timestamp(segment.start, true)} --> ${timestamp(segment.end, true)}\n${speakerName(transcript, segment.speaker)}: ${segment.text.replace(/\r?\n/g, " ")}\n`,
        )
        .join("\n"),
    );
  if (format === "xlsx") {
    const workbook = new ExcelJS.Workbook();
    const sheet = workbook.addWorksheet("Transcript");
    sheet.columns = [
      { header: "Segment", key: "id", width: 15 },
      { header: "Bắt đầu (giây)", key: "start", width: 18 },
      { header: "Kết thúc (giây)", key: "end", width: 18 },
      { header: "Người nói", key: "speaker", width: 22 },
      { header: "Nội dung", key: "text", width: 100 },
    ];
    for (const segment of transcript.segments)
      sheet.addRow({
        ...segment,
        speaker: speakerName(transcript, segment.speaker),
      });
    sheet.getRow(1).font = { bold: true };
    sheet.views = [{ state: "frozen", ySplit: 1 }];
    sheet.getColumn("text").alignment = { wrapText: true, vertical: "top" };
    const words = workbook.addWorksheet("Words");
    words.addRow(["Segment", "Từ", "Bắt đầu", "Kết thúc", "Người nói"]);
    for (const segment of transcript.segments)
      for (const word of segment.words)
        words.addRow([
          segment.id,
          word.word,
          word.start,
          word.end,
          speakerName(transcript, word.speaker),
        ]);
    const metadata = workbook.addWorksheet("Metadata");
    metadata.addRows([
      ["audio_id", transcript.audio_id],
      ["timeline", "source"],
      ["duration_sec", transcript.duration_sec],
      ...transcript.warnings.map((warning) => ["warning", warning]),
    ]);
    return Buffer.from(await workbook.xlsx.writeBuffer());
  }
  const font =
    process.env.AUDIO_PDF_FONT ??
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf";
  try {
    await access(font);
  } catch {
    throw new AudioServiceError("PDF_FONT_UNAVAILABLE", 503);
  }
  // Render our generated Markdown, not arbitrary client HTML or shell input.
  const document = new PDFDocument({
    size: "A4",
    margins: { top: 45, bottom: 45, left: 45, right: 45 },
  });
  const buffers: Buffer[] = [];
  const completed = new Promise<Buffer>((resolve, reject) => {
    document.on("data", (buffer: Buffer) => buffers.push(buffer));
    document.on("end", () => resolve(Buffer.concat(buffers)));
    document.on("error", reject);
  });
  document.font(font);
  for (const line of markdown(transcript).split("\n")) {
    const heading = /^(#{1,3}) /.exec(line);
    document
      .fontSize(
        heading
          ? heading[1].length === 1
            ? 20
            : heading[1].length === 2
              ? 15
              : 11
          : 10,
      )
      .text(
        line.replace(/^#{1,3} /, "").replace(/\\([\\`*_{}\[\]<>#!|])/g, "$1"),
        { lineGap: 3 },
      );
  }
  document.end();
  return completed;
}
