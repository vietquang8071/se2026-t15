import {
  Injectable,
  Logger,
  OnModuleDestroy,
  OnModuleInit,
} from "@nestjs/common";
import { randomUUID } from "node:crypto";
import { mkdir, readdir, rename, rm } from "node:fs/promises";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import pg from "pg";
import { Prisma } from "../generated/prisma/client.js";
import { PrismaService } from "../prisma.service.js";
import { inspectAudio } from "./audio-inspection.js";
import type { AudioMetadata } from "./audio-inspection.js";
import { AudioServiceError } from "./audio-types.js";
import type { AudioTranscript, Chunk, WhisperResult } from "./audio-types.js";
import { createChunks, prepareAudio } from "./audio-media.js";
import { openAIKey, transcribeFile } from "./audio-provider.js";
import {
  buildTranscript,
  validateDiarization,
  validateWhisper,
} from "./audio-transcript.js";

function json(value: unknown): Prisma.InputJsonValue {
  return JSON.parse(JSON.stringify(value));
}

@Injectable()
export class AudioService implements OnModuleInit, OnModuleDestroy {
  readonly root = resolve(
    process.env.AUDIO_STORAGE_DIR ??
      fileURLToPath(new URL("../../../../data/audio", import.meta.url)),
  );
  readonly incoming = join(this.root, "incoming");
  private readonly logger = new Logger(AudioService.name);
  private lock?: pg.Client;
  private timer?: NodeJS.Timeout;
  private tickPromise?: Promise<void>;
  private stopping = false;
  private active?: {
    audioId: string;
    controller: AbortController;
    done: Promise<void>;
  };
  provider = transcribeFile;
  uploads = 0;

  constructor(private readonly prisma: PrismaService) {}
  get db() {
    return this.prisma.client;
  }
  get available() {
    return !this.stopping && Boolean(this.lock);
  }

  async onModuleInit() {
    if (!process.env.AUDIO_API_KEY || process.env.AUDIO_API_KEY.length < 24)
      throw new Error("AUDIO_API_KEY must contain at least 24 characters");
    // One service instance owns this database/storage. Holding a session lock
    // makes restart recovery and delete-vs-worker ordering explicit and safe.
    this.lock = new pg.Client({
      connectionString: process.env.AUDIO_DATABASE_URL,
    });
    await this.lock.connect();
    const result = await this.lock.query(
      "SELECT pg_try_advisory_lock(202615, 1) AS acquired",
    );
    if (!result.rows[0].acquired) {
      await this.lock.end();
      throw new Error(
        "Another audio service instance already owns this database",
      );
    }
    this.lock.on("error", () => {
      this.stopping = true;
      this.active?.controller.abort();
      this.logger.error("Audio worker database lock lost; restart the service");
    });
    await mkdir(this.incoming, { recursive: true });
    for (const file of await readdir(this.incoming))
      await rm(join(this.incoming, file), { recursive: true, force: true });
    await this.db.audioJob.updateMany({
      where: { status: "running" },
      data: { status: "queued", stage: "recovered" },
    });
    this.timer = setInterval(() => {
      if (!this.tickPromise)
        this.tickPromise = this.tick().finally(() => {
          this.tickPromise = undefined;
        });
    }, 1000);
    this.timer.unref();
    await this.cleanup();
    // Reconcile files written before a crash but never committed to the DB.
    for (const id of await readdir(this.root)) {
      if (
        this.isId(id) &&
        !(await this.db.audioAsset.findUnique({
          where: { id },
          select: { id: true },
        }))
      )
        await rm(join(this.root, id), { recursive: true, force: true });
    }
  }

  async onModuleDestroy() {
    this.stopping = true;
    if (this.timer) clearInterval(this.timer);
    this.active?.controller.abort();
    await this.tickPromise;
    await this.active?.done;
    await this.lock?.end();
  }

  private isId(id: string) {
    return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      id,
    );
  }

  async get(id: string) {
    if (!this.isId(id)) throw new AudioServiceError("AUDIO_NOT_FOUND", 404);
    const asset = await this.db.audioAsset.findUnique({ where: { id } });
    if (!asset || asset.status === "deleted")
      throw new AudioServiceError("AUDIO_NOT_FOUND", 404);
    if (asset.expiresAt <= new Date())
      throw new AudioServiceError("AUDIO_EXPIRED", 410);
    return asset;
  }

  async upload(file: Express.Multer.File, retention: unknown) {
    try {
      if (retention !== "30" && retention !== "60")
        throw new AudioServiceError("INVALID_RETENTION_DAYS", 400);
      const metadata = await inspectAudio(
        {
          filePath: file.path,
          originalName: file.originalname,
          mimeType: file.mimetype,
        },
        this.incoming,
        {
          ffmpegPath: process.env.FFMPEG_PATH,
          ffprobePath: process.env.FFPROBE_PATH,
        },
      );
      const id = randomUUID();
      const directory = join(this.root, id);
      await mkdir(directory);
      try {
        await rename(file.path, join(directory, "source"));
        const createdAt = new Date();
        const asset = await this.db.audioAsset.create({
          data: {
            id,
            originalName: file.originalname.slice(0, 255),
            sourceKey: `${id}/source`,
            metadata: json(metadata),
            retentionDays: Number(retention),
            createdAt,
            expiresAt: new Date(
              createdAt.getTime() + Number(retention) * 86400_000,
            ),
          },
        });
        return this.publicMetadata(asset.id);
      } catch (error) {
        await rm(directory, { recursive: true, force: true });
        throw error;
      }
    } finally {
      await rm(file.path, { force: true });
    }
  }

  async publicMetadata(id: string) {
    const asset = await this.get(id);
    const job = await this.db.audioJob.findUnique({ where: { audioId: id } });
    return {
      audio_id: id,
      status: asset.status,
      source: asset.metadata,
      retention_days: asset.retentionDays,
      created_at: asset.createdAt,
      expires_at: asset.expiresAt,
      job_id: job?.id ?? null,
    };
  }

  async process(id: string) {
    await this.get(id);
    if (!openAIKey()) throw new AudioServiceError("OPENAI_KEY_MISSING", 503);
    return this.db.$transaction(async (tx) => {
      // Lock the asset so DELETE and concurrent process requests serialize.
      await tx.$queryRaw`SELECT id FROM "AudioAsset" WHERE id = ${id}::uuid FOR UPDATE`;
      const asset = await tx.audioAsset.findUnique({ where: { id } });
      if (!asset || asset.status === "deleted" || asset.expiresAt <= new Date())
        throw new AudioServiceError("AUDIO_NOT_FOUND", 404);
      let job = await tx.audioJob.findUnique({ where: { audioId: id } });
      if (job?.status === "failed") {
        if (job.attempts >= 3)
          throw new AudioServiceError("JOB_RETRY_LIMIT", 409);
        job = await tx.audioJob.update({
          where: { id: job.id },
          data: { status: "queued", stage: "queued", errorCode: null },
        });
      }
      if (!job) job = await tx.audioJob.create({ data: { audioId: id } });
      return { job_id: job.id, audio_id: id, status: job.status };
    });
  }

  async job(id: string) {
    if (!this.isId(id)) throw new AudioServiceError("JOB_NOT_FOUND", 404);
    const job = await this.db.audioJob.findUnique({ where: { id } });
    if (!job) throw new AudioServiceError("JOB_NOT_FOUND", 404);
    await this.get(job.audioId);
    return {
      job_id: id,
      audio_id: job.audioId,
      status: job.status,
      stage: job.stage,
      progress: job.progress,
      attempts: job.attempts,
      provider_calls: job.providerCalls,
      error: job.errorCode,
      created_at: job.createdAt,
      updated_at: job.updatedAt,
      transcript_url:
        job.status === "completed"
          ? `/api/audio/${job.audioId}/transcript`
          : null,
    };
  }

  async transcript(id: string): Promise<AudioTranscript> {
    const asset = await this.get(id);
    if (!asset.transcript)
      throw new AudioServiceError("TRANSCRIPT_NOT_READY", 409);
    return asset.transcript as unknown as AudioTranscript;
  }

  async renameSpeaker(id: string, speakerId: string, name: unknown) {
    await this.get(id);
    if (
      typeof name !== "string" ||
      !name.trim() ||
      name.length > 100 ||
      /[\r\n\x00-\x1f]/.test(name)
    )
      throw new AudioServiceError("INVALID_SPEAKER_NAME", 400);
    return this.db.$transaction(async (tx) => {
      await tx.$queryRaw`SELECT id FROM "AudioAsset" WHERE id = ${id}::uuid FOR UPDATE`;
      const asset = await tx.audioAsset.findUnique({ where: { id } });
      if (!asset || asset.status === "deleted" || asset.expiresAt <= new Date())
        throw new AudioServiceError("AUDIO_NOT_FOUND", 404);
      if (!asset.transcript)
        throw new AudioServiceError("TRANSCRIPT_NOT_READY", 409);
      const transcript = asset.transcript as unknown as AudioTranscript;
      const speaker = transcript.speakers.find((item) => item.id === speakerId);
      if (!speaker) throw new AudioServiceError("SPEAKER_NOT_FOUND", 404);
      speaker.name = name.trim();
      await tx.audioAsset.update({
        where: { id },
        data: { transcript: json(transcript) },
      });
      return transcript.speakers;
    });
  }

  async remove(id: string) {
    if (!this.isId(id)) throw new AudioServiceError("AUDIO_NOT_FOUND", 404);
    await this.db.$transaction(async (tx) => {
      await tx.$queryRaw`SELECT id FROM "AudioAsset" WHERE id = ${id}::uuid FOR UPDATE`;
      const asset = await tx.audioAsset.findUnique({ where: { id } });
      if (!asset) throw new AudioServiceError("AUDIO_NOT_FOUND", 404);
      await tx.audioAsset.update({
        where: { id },
        data: { status: "deleted", transcript: Prisma.DbNull },
      });
    });
    if (this.active?.audioId === id) {
      this.active.controller.abort();
      await this.active.done;
    }
    await rm(join(this.root, id), { recursive: true, force: true });
    await this.db.audioAsset.deleteMany({ where: { id, status: "deleted" } });
  }

  async cleanup() {
    const assets = await this.db.audioAsset.findMany({
      where: {
        OR: [{ expiresAt: { lte: new Date() } }, { status: "deleted" }],
      },
      select: { id: true },
    });
    for (const asset of assets) {
      try {
        await this.remove(asset.id);
      } catch (error) {
        if (!(error instanceof AudioServiceError && error.status === 404))
          this.logger.error("Audio cleanup failed; will retry");
      }
    }
  }

  private async tick() {
    if (this.stopping) return;
    try {
      // Expiry must run even while a long provider request is in flight.
      await this.cleanup();
      if (this.stopping || this.active) return;
      const job = await this.db.audioJob.findFirst({
        where: { status: "queued" },
        orderBy: { createdAt: "asc" },
      });
      if (!job || this.stopping) return;
      const controller = new AbortController();
      const done = this.run(job.id, job.audioId, controller.signal);
      this.active = { audioId: job.audioId, controller, done };
      void done.finally(() => {
        if (this.active?.done === done) this.active = undefined;
      });
    } catch {
      this.logger.error("Audio worker tick failed; will retry");
    }
  }

  private async run(jobId: string, audioId: string, signal: AbortSignal) {
    try {
      const asset = await this.get(audioId);
      const metadata = asset.metadata as unknown as AudioMetadata;
      const previous = await this.db.audioJob.findUniqueOrThrow({
        where: { id: jobId },
      });
      if (previous.attempts >= 3)
        throw new AudioServiceError("JOB_RETRY_LIMIT", 409);
      await this.db.audioAsset.updateMany({
        where: { id: audioId, status: { not: "deleted" } },
        data: { status: "processing" },
      });
      const job = await this.db.audioJob.update({
        where: { id: jobId },
        data: {
          status: "running",
          stage: "preparing",
          attempts: { increment: 1 },
          progress: 5,
        },
      });
      const checkpoints = job.checkpoints as Record<string, unknown>;
      const configuration = JSON.stringify({
        transcription: process.env.OPENAI_ASR_MODEL ?? "whisper-1",
        diarization:
          process.env.OPENAI_DIARIZATION_MODEL ?? "gpt-4o-transcribe-diarize",
        chunkSeconds: Number(process.env.AUDIO_CHUNK_SECONDS ?? 600),
        overlapSeconds: Number(process.env.AUDIO_OVERLAP_SECONDS ?? 2),
      });
      if (
        checkpoints._configuration &&
        checkpoints._configuration !== configuration
      )
        throw new AudioServiceError("JOB_CONFIGURATION_CHANGED", 409);
      checkpoints._configuration = configuration;
      await this.db.audioJob.update({
        where: { id: jobId },
        data: { checkpoints: json(checkpoints) },
      });
      const directory = join(this.root, audioId, "processed");
      signal.throwIfAborted();
      const prepared = await prepareAudio(
        join(this.root, asset.sourceKey),
        directory,
        signal,
      );
      const chunks = await createChunks(
        prepared.wav,
        directory,
        prepared.duration,
        signal,
      );
      const beforeCall = async () => {
        signal.throwIfAborted();
        await this.get(audioId);
        await this.db.audioJob.update({
          where: { id: jobId },
          data: { providerCalls: { increment: 1 } },
        });
      };
      const save = async (key: string, result: unknown) => {
        signal.throwIfAborted();
        await this.get(audioId);
        checkpoints[key] = result;
        await this.db.audioJob.update({
          where: { id: jobId },
          data: { checkpoints: json(checkpoints) },
        });
      };
      const results: { chunk: Chunk; result: WhisperResult }[] = [];
      for (const chunk of chunks) {
        signal.throwIfAborted();
        await this.get(audioId);
        await this.db.audioJob.update({
          where: { id: jobId },
          data: {
            stage: "transcribing",
            progress: 10 + Math.floor((55 * chunk.index) / chunks.length),
          },
        });
        const key = `whisper_${chunk.index}`;
        const result = validateWhisper(
          checkpoints[key] ??
            (await this.provider(chunk.path, "whisper", signal, beforeCall)),
          chunk.duration,
        );
        if (!checkpoints[key]) await save(key, result);
        results.push({ chunk, result });
      }
      await this.db.audioJob.update({
        where: { id: jobId },
        data: { stage: "diarizing", progress: 70 },
      });
      const turns = validateDiarization(
        checkpoints.diarization ??
          (await this.provider(
            prepared.mp3,
            "diarization",
            signal,
            beforeCall,
          )),
        prepared.duration,
      );
      if (!checkpoints.diarization) await save("diarization", turns);
      const transcript = buildTranscript(
        audioId,
        metadata.duration_sec,
        metadata.audio_start_sec ?? 0,
        results,
        turns,
      );
      signal.throwIfAborted();
      await this.db.$transaction(async (tx) => {
        const updated = await tx.audioAsset.updateMany({
          where: {
            id: audioId,
            status: { not: "deleted" },
            expiresAt: { gt: new Date() },
          },
          data: { status: "completed", transcript: json(transcript) },
        });
        if (!updated.count) throw new AudioServiceError("AUDIO_EXPIRED", 410);
        await tx.audioJob.update({
          where: { id: jobId },
          data: {
            status: "completed",
            stage: "completed",
            progress: 100,
            errorCode: null,
          },
        });
      });
    } catch (error) {
      if (signal.aborted && this.stopping) return; // startup recovers running jobs
      await rm(join(this.root, audioId, "processed"), {
        recursive: true,
        force: true,
      }).catch(() => undefined);
      const code =
        error instanceof AudioServiceError
          ? error.code
          : signal.aborted
            ? "JOB_CANCELLED"
            : "AUDIO_JOB_FAILED";
      try {
        await this.db.audioJob.updateMany({
          where: { id: jobId },
          data: { status: "failed", stage: "failed", errorCode: code },
        });
        await this.db.audioAsset.updateMany({
          where: { id: audioId, status: { not: "deleted" } },
          data: { status: "failed" },
        });
      } catch {
        this.logger.error(
          "Could not persist job failure; restart recovery required",
        );
      }
    }
  }
}
