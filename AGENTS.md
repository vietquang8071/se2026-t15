# Repository Guidelines

## Project Structure & Module Organization

This repository contains the MVP workspace for **Meeting Minutes Assistant**, which turns meeting audio into structured minutes:

- `apps/web/`: Next.js App Router frontend.
- `apps/api/`: NestJS API.
- `packages/database/`: Prisma schema and shared PostgreSQL client.
- `services/audio/`: independent audio API, worker, Prisma schema and exports;
  runs on port 3002 with its own database, storage and service API key. Keep
  audio endpoints out of `apps/api`; App integrates by HTTP in a later task.
- `docker-compose.yml`: local PostgreSQL service.
- `docs/`: product scope, output schemas, and feature breakdown.

## Build, Test, and Development Commands

Install with `pnpm install`, copy `.env.example` to `.env`, then start PostgreSQL with `docker compose up -d`. Useful commands:

- `pnpm dev`: start Next.js and NestJS through Turborepo.
- `pnpm build`, `pnpm lint`, `pnpm typecheck`: build and check workspace packages.
- `pnpm db:generate`, `pnpm db:migrate`, `pnpm db:studio`: manage Prisma Client and the development database.

Document setup changes in `README.md` and keep root scripts coordinated with Turborepo tasks.

## Coding Style & Naming Conventions

Use TypeScript and two-space indentation. Name React components and Nest classes in PascalCase, Nest providers with role suffixes (`PrismaService`), and utility functions in camelCase. Use descriptive, lowercase, hyphen-separated Markdown filenames. Keep headings hierarchical, indent nested list items consistently, and label fenced code blocks. Prefer repository-relative links over machine-specific paths.

Preserve established schema names such as `anchor_date` and `source_timestamp`, ISO dates (`YYYY-MM-DD`), and identifiers such as `ACT-001`. Use ESLint and the workspace Prettier scripts for linting and formatting.

## Testing Guidelines

There is no shared test suite or coverage threshold yet. When adding product behavior, add tests in the owning app and document its test command. For documentation changes, inspect tables and Mermaid diagrams, check links, and validate JSON examples. Cross-check scope and schemas between both product documents, and verify calendar calculations in temporal-resolution examples.

## Commit & Pull Request Guidelines

### Son's fixed branch workflow

At Son's explicit request, all future work for Son in this repository MUST use
the single persistent branch `son_branch`. Do not create new feature/docs/fix
branches for this work. Commit and push to `son_branch`. Do not create pull
requests unless Son explicitly asks; if requested, target `main` and retain
`son_branch` after merging. This overrides the general branch workflow in
`CONTRIBUTING.md` for Son's work only. Do not modify other contributors' branches.

The short Git history uses messages such as `add: document about product description and feature overview` and `update README`; no strict convention is established. Write concise, descriptive commit subjects and keep changes focused.

In pull requests, explain what changed and why, reference affected feature cards or issues when available, and state validation performed. Include screenshots when rendered layout changes need visual review.

## Security & Configuration

Keep API keys, credentials, private recordings, and identifiable transcripts out of commits. Use synthetic meeting examples in documentation and future test fixtures.
