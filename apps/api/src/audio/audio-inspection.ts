import { execFile } from "node:child_process";
import { open, realpath, stat } from "node:fs/promises";
import { extname, isAbsolute, relative } from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

export const MAX_AUDIO_BYTES = 100_000_000;
export const MAX_AUDIO_DURATION_SEC = 3_600;

const formats = {
  wav: {
    mimeType: "audio/wav",
    aliases: ["audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"],
    container: "wav",
  },
  mp3: {
    mimeType: "audio/mpeg",
    aliases: ["audio/mpeg", "audio/mp3"],
    container: "mp3",
  },
  m4a: {
    mimeType: "audio/mp4",
    aliases: ["audio/mp4", "audio/x-m4a", "audio/m4a"],
    container: "m4a",
  },
  webm: {
    mimeType: "audio/webm",
    aliases: ["audio/webm"],
    container: "webm",
  },
} as const;

type AudioFormat = keyof typeof formats;

export interface AudioInspectionInput {
  filePath: string;
  originalName: string;
  mimeType?: string;
}

export interface AudioMetadata {
  format: AudioFormat;
  mime_type: string;
  size_bytes: number;
  duration_sec: number;
  codec: string;
  sample_rate: number;
  channels: number;
}

export interface AudioInspectionOptions {
  ffprobePath?: string;
  ffmpegPath?: string;
  probeTimeoutMs?: number;
  decodeTimeoutMs?: number;
}

export type AudioInspectionCode =
  | "INVALID_AUDIO_PATH"
  | "EMPTY_AUDIO"
  | "AUDIO_TOO_LARGE"
  | "UNSUPPORTED_AUDIO_FORMAT"
  | "INVALID_AUDIO"
  | "AUDIO_TOO_LONG"
  | "AUDIO_INSPECTION_TIMEOUT"
  | "AUDIO_TOOL_UNAVAILABLE";

export class AudioInspectionError extends Error {
  constructor(
    readonly code: AudioInspectionCode,
    readonly statusCode: number,
    message: string,
  ) {
    super(message);
    this.name = "AudioInspectionError";
  }
}

interface ProbeOutput {
  format?: { format_name?: string; duration?: string };
  streams?: {
    codec_type?: string;
    codec_name?: string;
    sample_rate?: string;
    channels?: number;
    duration?: string;
  }[];
}

async function runTool(tool: string, args: string[], timeout: number) {
  try {
    return await execFileAsync(tool, args, {
      timeout,
      maxBuffer: 256 * 1024,
      killSignal: "SIGKILL",
      windowsHide: true,
    });
  } catch (error) {
    const failure = error as NodeJS.ErrnoException & { killed?: boolean };
    if (failure.code === "ENOENT" || failure.code === "EACCES") {
      throw new AudioInspectionError(
        "AUDIO_TOOL_UNAVAILABLE",
        503,
        "Công cụ kiểm tra audio chưa sẵn sàng.",
      );
    }
    if (failure.killed) {
      throw new AudioInspectionError(
        "AUDIO_INSPECTION_TIMEOUT",
        503,
        "Kiểm tra audio vượt thời gian cho phép.",
      );
    }
    throw new AudioInspectionError(
      "INVALID_AUDIO",
      422,
      "Không thể đọc hoặc giải mã audio.",
    );
  }
}

async function getLocalFile(filePath: string, uploadDirectory: string) {
  try {
    const root = await realpath(uploadDirectory);
    const resolvedPath = await realpath(filePath);
    const childPath = relative(root, resolvedPath);
    if (
      !childPath ||
      childPath === ".." ||
      childPath.startsWith("../") ||
      childPath.startsWith("..\\") ||
      isAbsolute(childPath)
    ) {
      throw new Error("File is outside upload directory");
    }
    const file = await stat(resolvedPath);
    if (!file.isFile()) throw new Error("Not a regular file");
    return { resolvedPath, size: file.size };
  } catch {
    throw new AudioInspectionError(
      "INVALID_AUDIO_PATH",
      400,
      "Không tìm thấy file audio hợp lệ trong thư mục upload.",
    );
  }
}

async function hasWebmDocType(filePath: string) {
  const file = await open(filePath, "r");
  try {
    const header = Buffer.alloc(4096);
    const { bytesRead } = await file.read(header, 0, header.length, 0);
    const docTypeIndex = header
      .subarray(0, bytesRead)
      .indexOf(Buffer.from([0x42, 0x82]));
    if (docTypeIndex < 0 || docTypeIndex + 2 >= bytesRead) return false;

    // FFprobe reports both Matroska and WebM as "matroska,webm".
    // Read the EBML DocType length to distinguish a renamed Matroska file.
    let mask = 0x80;
    let lengthBytes = 1;
    const lengthStart = docTypeIndex + 2;
    while (lengthBytes <= 8 && !(header[lengthStart] & mask)) {
      mask >>= 1;
      lengthBytes++;
    }
    if (lengthBytes > 8 || lengthStart + lengthBytes + 4 > bytesRead)
      return false;
    let length = header[lengthStart] & (mask - 1);
    for (let i = 1; i < lengthBytes; i++) {
      length = length * 256 + header[lengthStart + i];
    }
    const valueStart = lengthStart + lengthBytes;
    return (
      length === 4 &&
      header.toString("ascii", valueStart, valueStart + 4) === "webm"
    );
  } finally {
    await file.close();
  }
}

export async function inspectAudio(
  input: AudioInspectionInput,
  uploadDirectory: string,
  options: AudioInspectionOptions = {},
): Promise<AudioMetadata> {
  const { resolvedPath, size } = await getLocalFile(
    input.filePath,
    uploadDirectory,
  );
  if (size === 0) {
    throw new AudioInspectionError("EMPTY_AUDIO", 400, "File audio rỗng.");
  }
  if (size > MAX_AUDIO_BYTES) {
    throw new AudioInspectionError(
      "AUDIO_TOO_LARGE",
      413,
      "File audio vượt 100 MB.",
    );
  }

  const extension = extname(input.originalName).slice(1).toLowerCase();
  if (!Object.hasOwn(formats, extension)) {
    throw new AudioInspectionError(
      "UNSUPPORTED_AUDIO_FORMAT",
      415,
      "Chỉ nhận WAV, MP3, M4A hoặc WebM.",
    );
  }
  const format = extension as AudioFormat;
  const specification = formats[format];
  const mime = input.mimeType?.split(";")[0].trim().toLowerCase();
  if (
    mime &&
    mime !== "application/octet-stream" &&
    !(specification.aliases as readonly string[]).includes(mime)
  ) {
    throw new AudioInspectionError(
      "UNSUPPORTED_AUDIO_FORMAT",
      415,
      "MIME không phù hợp với định dạng audio.",
    );
  }

  const { stdout } = await runTool(
    options.ffprobePath ?? "ffprobe",
    [
      "-v",
      "error",
      "-protocol_whitelist",
      "file,pipe",
      "-show_entries",
      "format=format_name,duration:stream=codec_type,codec_name,sample_rate,channels,duration",
      "-of",
      "json",
      resolvedPath,
    ],
    options.probeTimeoutMs ?? 10_000,
  );

  let probe: ProbeOutput;
  try {
    probe = JSON.parse(stdout) as ProbeOutput;
    if (!probe || !Array.isArray(probe.streams))
      throw new Error("Invalid probe output");
  } catch {
    throw new AudioInspectionError(
      "INVALID_AUDIO",
      422,
      "Không đọc được metadata audio.",
    );
  }
  const audioStreams = probe.streams!.filter(
    (stream) => stream.codec_type === "audio",
  );
  if (
    audioStreams.length !== 1 ||
    probe.streams!.some((stream) => stream.codec_type === "video")
  ) {
    throw new AudioInspectionError(
      "INVALID_AUDIO",
      422,
      "File phải có một audio stream và không chứa video.",
    );
  }
  const audio = audioStreams[0];
  const containerNames = probe.format?.format_name?.split(",") ?? [];
  const codec = audio.codec_name ?? "";
  let matchesFormat = containerNames.includes(specification.container);
  if (format === "mp3") matchesFormat &&= codec === "mp3";
  if (format === "m4a") matchesFormat &&= ["aac", "alac"].includes(codec);
  if (format === "webm") {
    matchesFormat &&=
      ["opus", "vorbis"].includes(codec) &&
      (await hasWebmDocType(resolvedPath));
  }
  if (!matchesFormat) {
    throw new AudioInspectionError(
      "UNSUPPORTED_AUDIO_FORMAT",
      415,
      "Nội dung file không khớp định dạng audio.",
    );
  }

  const duration = Number(probe.format?.duration ?? audio.duration);
  const sampleRate = Number(audio.sample_rate);
  const channels = audio.channels ?? 0;
  if (
    !Number.isFinite(duration) ||
    duration <= 0 ||
    !codec ||
    !Number.isInteger(sampleRate) ||
    sampleRate <= 0 ||
    !Number.isInteger(channels) ||
    channels <= 0
  ) {
    throw new AudioInspectionError(
      "INVALID_AUDIO",
      422,
      "Metadata audio không hợp lệ.",
    );
  }
  if (duration > MAX_AUDIO_DURATION_SEC) {
    throw new AudioInspectionError(
      "AUDIO_TOO_LONG",
      422,
      "Audio vượt 60 phút.",
    );
  }

  await runTool(
    options.ffmpegPath ?? "ffmpeg",
    [
      "-nostdin",
      "-v",
      "error",
      "-xerror",
      "-err_detect",
      "explode",
      "-protocol_whitelist",
      "file,pipe",
      "-threads",
      "1",
      "-i",
      resolvedPath,
      "-map",
      "0:a:0",
      "-vn",
      "-f",
      "null",
      "-",
    ],
    options.decodeTimeoutMs ?? 60_000,
  );

  return {
    format,
    mime_type: specification.mimeType,
    size_bytes: size,
    duration_sec: duration,
    codec,
    sample_rate: sampleRate,
    channels,
  };
}
