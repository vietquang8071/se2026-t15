# Meeting Minutes Assistant

Turborepo monorepo for the Meeting Minutes Assistant MVP.

## Workspace

- `apps/web`: Next.js App Router frontend.
- `apps/api`: NestJS API with a starter `GET /health` endpoint.
- `packages/database`: Prisma schema, PostgreSQL adapter, and shared client factory.
- `docker-compose.yml`: local PostgreSQL service and persistent volume.
- `docs/`: product description and feature breakdown.

## Requirements

Node.js 22.18 or newer (24 LTS recommended), pnpm 11, and Docker Compose.

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

## Common commands

```sh
pnpm dev            # Start both apps
pnpm build          # Build all workspace packages
pnpm lint           # Lint workspace packages
pnpm typecheck      # Type-check workspace packages
pnpm db:generate    # Regenerate Prisma Client
pnpm db:migrate     # Apply/create a development migration
pnpm db:studio      # Open Prisma Studio
docker compose down # Stop PostgreSQL; keep its data volume
```

To reset the local database, run `docker compose down -v` and then apply migrations again. This removes the PostgreSQL data volume.
