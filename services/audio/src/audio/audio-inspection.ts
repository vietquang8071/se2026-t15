import { execFile } from "node:child_process";
import { mkdtemp, open, realpath, rm, stat } from "node:fs/promises";
import { extname, isAbsolute, join, relative } from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

export const MAX_AUDIO_BYTES = 100_000_000;
export const MAX_AUDIO_DURATION_SEC = 3_600;
const MAX_EXTRACTED_BYTES = MAX_AUDIO_DURATION_SEC * 16_000 * 2 + 4096;

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
  mp4: {
    mimeType: "video/mp4",
    aliases: ["video/mp4", "audio/mp4", "application/mp4"],
    container: "mp4",
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
  audio_start_sec?: number;
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
  | "AUDIO_TOOL_UNAVAILABLE"
  | "AUDIO_EXTRACTION_FAILED";

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
  format?: { format_name?: string; duration?: string; start_time?: string };
  streams?: {
    codec_type?: string;
    codec_name?: string;
    sample_rate?: string;
    channels?: number;
    duration?: string;
    start_time?: string;
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

async function probeAudio(
  filePath: string,
  options: AudioInspectionOptions,
): Promise<ProbeOutput> {
  const { stdout } = await runTool(
    options.ffprobePath ?? "ffprobe",
    [
      "-v",
      "error",
      "-protocol_whitelist",
      "file,pipe",
      "-show_entries",
      "format=format_name,duration,start_time:stream=codec_type,codec_name,sample_rate,channels,duration,start_time",
      "-of",
      "json",
      filePath,
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
  return probe;
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
      "Chỉ nhận WAV, MP3, M4A, WebM hoặc MP4.",
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

  const probe = await probeAudio(resolvedPath, options);
  const audioStreams = probe.streams!.filter(
    (stream) => stream.codec_type === "audio",
  );
  if (
    audioStreams.length !== 1 ||
    (format !== "mp4" &&
      probe.streams!.some((stream) => stream.codec_type === "video"))
  ) {
    throw new AudioInspectionError(
      "INVALID_AUDIO",
      422,
      "File phải có một audio stream; chỉ định dạng MP4 được chứa video.",
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

  const audioStart = Number(audio.start_time ?? probe.format?.start_time ?? 0);
  const containerStart = Number(probe.format?.start_time ?? 0);
  if (
    format === "mp4" &&
    (!Number.isFinite(audioStart) || !Number.isFinite(containerStart))
  ) {
    throw new AudioInspectionError(
      "INVALID_AUDIO",
      422,
      "Timestamp audio trong MP4 không hợp lệ.",
    );
  }

  return {
    format,
    mime_type: specification.mimeType,
    size_bytes: size,
    duration_sec: duration,
    codec,
    sample_rate: sampleRate,
    channels,
    ...(format === "mp4"
      ? { audio_start_sec: Math.max(0, audioStart - containerStart) }
      : {}),
  };
}

export interface ExtractedAudio {
  filePath: string;
  metadata: AudioMetadata;
  source: AudioMetadata;
  source_audio_start_sec: number;
}

export async function extractAudioFromMp4(
  input: AudioInspectionInput,
  uploadDirectory: string,
  outputDirectory: string,
  options: AudioInspectionOptions = {},
): Promise<ExtractedAudio> {
  const source = await inspectAudio(input, uploadDirectory, options);
  if (source.format !== "mp4") {
    throw new AudioInspectionError(
      "UNSUPPORTED_AUDIO_FORMAT",
      415,
      "Bước tách audio này chỉ nhận MP4.",
    );
  }
  const { resolvedPath } = await getLocalFile(input.filePath, uploadDirectory);
  let workDirectory: string;
  try {
    const outputRoot = await realpath(outputDirectory);
    if (!(await stat(outputRoot)).isDirectory())
      throw new Error("Invalid output directory");
    workDirectory = await mkdtemp(join(outputRoot, "audio-"));
  } catch {
    throw new AudioInspectionError(
      "AUDIO_EXTRACTION_FAILED",
      500,
      "Không tạo được thư mục audio đầu ra.",
    );
  }

  const filePath = join(workDirectory, "extracted.wav");
  try {
    await runTool(
      options.ffmpegPath ?? "ffmpeg",
      [
        "-nostdin",
        "-v",
        "error",
        "-xerror",
        "-err_detect",
        "explode",
        "-n",
        "-protocol_whitelist",
        "file,pipe",
        "-threads",
        "1",
        "-i",
        resolvedPath,
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        "-fs",
        String(MAX_EXTRACTED_BYTES),
        "-f",
        "wav",
        filePath,
      ],
      options.decodeTimeoutMs ?? 60_000,
    );

    const outputSize = (await stat(filePath)).size;
    const output = await probeAudio(filePath, options);
    const audio = output.streams?.find(
      (stream) => stream.codec_type === "audio",
    );
    const duration = Number(output.format?.duration);
    if (
      !audio ||
      audio.codec_name !== "pcm_s16le" ||
      Number(audio.sample_rate) !== 16000 ||
      audio.channels !== 1 ||
      !Number.isFinite(duration) ||
      duration <= 0 ||
      duration > MAX_AUDIO_DURATION_SEC ||
      outputSize >= MAX_EXTRACTED_BYTES
    ) {
      throw new AudioInspectionError(
        "AUDIO_EXTRACTION_FAILED",
        500,
        "Audio đầu ra không đáp ứng điều kiện xử lý.",
      );
    }
    return {
      filePath,
      metadata: {
        format: "wav",
        mime_type: "audio/wav",
        size_bytes: outputSize,
        duration_sec: duration,
        codec: audio.codec_name,
        sample_rate: 16000,
        channels: 1,
      },
      source,
      source_audio_start_sec: source.audio_start_sec ?? 0,
    };
  } catch (error) {
    await rm(workDirectory, { recursive: true, force: true });
    if (error instanceof AudioInspectionError && error.code !== "INVALID_AUDIO")
      throw error;
    throw new AudioInspectionError(
      "AUDIO_EXTRACTION_FAILED",
      500,
      "Không thể tách audio từ MP4.",
    );
  }
}
