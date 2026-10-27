# Meeting Minutes Assistant

Turborepo monorepo for the Meeting Minutes Assistant MVP.

## Current input scope

Input is **file upload only**: WAV, MP3, M4A, WebM and MP4 video, up to
100 MB / 60 minutes. There is no in-browser recording feature. MP4 audio can be
extracted to a separate WAV while retaining the original file.

The independent audio service lives in `services/audio` and runs on port 3002,
with its own database/storage/API key. It implements upload, durable jobs,
OpenAI Whisper + diarization, playback, exports (JSON/TXT/SRT/Markdown/Excel/PDF)
and 30/60-day cleanup of media and transcripts. App/LLM integration is separate.
See the [audio service setup](services/audio/README.md),
[API contract](docs/audio-service-api.md) and [validation results](docs/audio-validation.md).

## Workspace

- `apps/web`: Next.js App Router frontend.
- `apps/api`: NestJS API with a starter `GET /health` endpoint.
- `services/audio`: Independent NestJS audio API and worker with its own Prisma schema.
- `packages/database`: Prisma schema, PostgreSQL adapter, and shared client factory.
- `docker-compose.yml`: local PostgreSQL service and persistent volume.
- `docs/`: product description and feature breakdown.

## Requirements

Node.js 22.18 or newer (24 LTS recommended), pnpm 11, and Docker Compose.

Audio inspection additionally needs `ffmpeg` and `ffprobe` available on `PATH`.
The audio helper and App integration responsibilities are documented in
[Audio ingestion](docs/audio-ingestion.md).

## Run locally

```sh
cp .env.example .env
pnpm install
docker compose up -d
pnpm db:generate
pnpm db:migrate
pnpm dev
```

The web app runs at `http://localhost:3000`; the API runs at `http://localhost:3001` and exposes `GET /health`. The apps load configuration from the root `.env` file; use `API_PORT` to change the API port. Docker Compose starts PostgreSQL only so both apps can use local hot reload.

The frontend currently demonstrates audio selection and sample minutes. Its `/sign-in` and `/sign-up` pages are demo forms without account or session creation. See [the frontend README](apps/web/README.md) for the current behavior.

## Common commands

```sh
pnpm dev            # Start both apps
pnpm build          # Build all workspace packages
pnpm lint           # Lint workspace packages
pnpm typecheck      # Type-check workspace packages
pnpm --filter @meeting-minutes/audio test:audio # Check audio inspection
pnpm db:generate    # Regenerate Prisma Client
pnpm db:migrate     # Apply/create a development migration
pnpm db:studio      # Open Prisma Studio
docker compose down # Stop PostgreSQL; keep its data volume
```

To reset the local database, run `docker compose down -v` and then apply migrations again. This removes the PostgreSQL data volume.

## Run the independent audio service

See [services/audio/README.md](services/audio/README.md) for database/key setup,
Docker Compose, test commands and the file-processing client. App is not required.

```sh
pnpm audio:db:deploy
pnpm audio:build
pnpm --filter @meeting-minutes/audio start
# In another terminal:
pnpm audio:file /path/to/meeting.mp4 artifacts/private/audio-result 30
```
