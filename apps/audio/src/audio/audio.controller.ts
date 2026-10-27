import {
  ArgumentsHost,
  Body,
  CanActivate,
  Catch,
  Controller,
  Delete,
  ExceptionFilter,
  ExecutionContext,
  Get,
  HttpCode,
  Injectable,
  Param,
  Patch,
  Post,
  Query,
  Req,
  Res,
  UnauthorizedException,
  UseFilters,
  UseGuards,
  ServiceUnavailableException,
} from "@nestjs/common";
import type { Request, Response } from "express";
import { timingSafeEqual, randomUUID } from "node:crypto";
import { createReadStream } from "node:fs";
import { rm, stat } from "node:fs/promises";
import { join } from "node:path";
import multer from "multer";
import { AudioService } from "./audio.service.js";
import { AudioInspectionError, MAX_AUDIO_BYTES } from "./audio-inspection.js";
import type { AudioMetadata } from "./audio-inspection.js";
import { AudioServiceError } from "./audio-types.js";
import { exportTranscript, exportTypes } from "./audio-export.js";

@Injectable()
export class AudioAuthGuard implements CanActivate {
  constructor(private readonly audio: AudioService) {}
  canActivate(context: ExecutionContext) {
    const request = context.switchToHttp().getRequest<Request>();
    const expected = Buffer.from(process.env.AUDIO_API_KEY ?? "");
    const actual = Buffer.from(request.header("x-api-key") ?? "");
    if (
      !expected.length ||
      actual.length !== expected.length ||
      !timingSafeEqual(actual, expected)
    )
      throw new UnauthorizedException("Invalid audio service API key");
    if (!this.audio.available)
      throw new ServiceUnavailableException("Audio service requires restart");
    return true;
  }
}

@Catch(AudioServiceError, AudioInspectionError, multer.MulterError)
export class AudioErrorFilter implements ExceptionFilter {
  catch(
    error: AudioServiceError | AudioInspectionError | multer.MulterError,
    host: ArgumentsHost,
  ) {
    let code = error.code;
    let status =
      error instanceof AudioServiceError
        ? error.status
        : error instanceof AudioInspectionError
          ? error.statusCode
          : 400;
    if (
      error instanceof multer.MulterError &&
      error.code === "LIMIT_FILE_SIZE"
    ) {
      code = "AUDIO_TOO_LARGE";
      status = 413;
    }
    host
      .switchToHttp()
      .getResponse<Response>()
      .status(status)
      .json({ error: { code } });
  }
}

@Controller("api/audio")
@UseGuards(AudioAuthGuard)
@UseFilters(AudioErrorFilter)
export class AudioController {
  constructor(private readonly audio: AudioService) {}

  @Post()
  async upload(@Req() request: Request, @Res() response: Response) {
    if (this.audio.uploads >= 2)
      throw new AudioServiceError("UPLOAD_BUSY", 429);
    this.audio.uploads++;
    try {
      const handler = multer({
        storage: multer.diskStorage({
          destination: this.audio.incoming,
          filename: (_request, _file, callback) => callback(null, randomUUID()),
        }),
        // Busboy marks a stream truncated when it reaches fileSize exactly.
        // Allow one sentinel byte here; inspectAudio enforces the inclusive cap.
        limits: {
          fileSize: MAX_AUDIO_BYTES + 1,
          files: 1,
          fields: 1,
          parts: 2,
          fieldSize: 100,
        },
      }).single("file");
      await new Promise<void>((resolve, reject) =>
        handler(request, response, (error) =>
          error ? reject(error) : resolve(),
        ),
      );
      if (!request.file) throw new AudioServiceError("FILE_REQUIRED", 400);
      const result = await this.audio.upload(
        request.file,
        request.body?.retention_days,
      );
      response.status(201).json(result);
    } finally {
      this.audio.uploads--;
      if (request.file) await rm(request.file.path, { force: true });
    }
  }

  @Get("jobs/:jobId")
  job(@Param("jobId") id: string) {
    return this.audio.job(id);
  }

  @Get(":id")
  metadata(@Param("id") id: string) {
    return this.audio.publicMetadata(id);
  }

  @Post(":id/process")
  @HttpCode(202)
  process(@Param("id") id: string) {
    return this.audio.process(id);
  }

  @Get(":id/transcript")
  transcript(@Param("id") id: string) {
    return this.audio.transcript(id);
  }

  @Patch(":id/speakers/:speakerId")
  speaker(
    @Param("id") id: string,
    @Param("speakerId") speaker: string,
    @Body() body: { name?: unknown },
  ) {
    return this.audio.renameSpeaker(id, speaker, body?.name);
  }

  @Get(":id/export")
  async download(
    @Param("id") id: string,
    @Query("format") format: string,
    @Res() response: Response,
  ) {
    const transcript = await this.audio.transcript(id);
    const buffer = await exportTranscript(transcript, format ?? "json");
    await this.audio.get(id);
    response
      .set({
        "Content-Type": exportTypes[format ?? "json"],
        "Content-Disposition": `attachment; filename="transcript-${id}.${format ?? "json"}"`,
        "Cache-Control": "no-store",
      })
      .send(buffer);
  }

  @Get(":id/media")
  async media(
    @Param("id") id: string,
    @Query("variant") variant: string | undefined,
    @Req() request: Request,
    @Res() response: Response,
  ) {
    const asset = await this.audio.get(id);
    if (variant && variant !== "source" && variant !== "normalized")
      throw new AudioServiceError("INVALID_MEDIA_VARIANT", 400);
    const normalized = variant === "normalized";
    // Files being written by a job are never exposed as finished playback media.
    if (normalized && asset.status !== "completed")
      throw new AudioServiceError("MEDIA_NOT_READY", 409);
    const path = normalized
      ? join(this.audio.root, id, "processed", "normalized.wav")
      : join(this.audio.root, asset.sourceKey);
    let size: number;
    try {
      size = (await stat(path)).size;
    } catch {
      throw new AudioServiceError("MEDIA_NOT_FOUND", 404);
    }
    const metadata = asset.metadata as unknown as AudioMetadata;
    response.set({
      "Accept-Ranges": "bytes",
      "Content-Type": normalized ? "audio/wav" : metadata.mime_type,
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    });
    let start = 0;
    let end = size - 1;
    if (request.headers.range) {
      const range = /^bytes=(\d*)-(\d*)$/.exec(request.headers.range);
      if (!range || (!range[1] && !range[2])) {
        response.set("Content-Range", `bytes */${size}`).status(416).end();
        return;
      }
      if (!range[1]) start = Math.max(0, size - Number(range[2]));
      else {
        start = Number(range[1]);
        end = range[2] ? Math.min(size - 1, Number(range[2])) : size - 1;
      }
      if (
        !Number.isSafeInteger(start) ||
        !Number.isSafeInteger(end) ||
        start > end ||
        start >= size
      ) {
        response.set("Content-Range", `bytes */${size}`).status(416).end();
        return;
      }
      response
        .status(206)
        .set("Content-Range", `bytes ${start}-${end}/${size}`);
    }
    response.set("Content-Length", String(end - start + 1));
    const stream = createReadStream(path, { start, end });
    stream.on("error", () => {
      if (!response.headersSent) response.status(404).end();
      else response.destroy();
    });
    response.on("close", () => stream.destroy());
    stream.pipe(response);
  }

  @Delete(":id")
  @HttpCode(204)
  async remove(@Param("id") id: string) {
    await this.audio.remove(id);
  }
}
