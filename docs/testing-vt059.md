# VT-059: scoped meeting export contract

This opt-in backend slice implements `GET /meetings/:meetingId/export` in
`apps/api/src/export`. It is **not registered in AppModule**: the starter has no
production authentication or persisted membership model. Tests compose a Nest
application with synthetic token verification and server-owned grants. Before
production use, supply a trusted `TokenVerifier`, resolve current server-side
permissions and register `ExportController` with `exportProviders`. Never derive
grants from query/body fields, or expose the test token mapping as authentication.

The service authenticates before validating IDs, explicitly checks the grant,
then calls the scoped repository. `PrismaMeetingRepository` applies both requested
ID and granted-ID filters in the actual Prisma query. This tests the existing
Meeting database contract; it does not persist or verify membership. Concurrent
permission revocation between grant resolution and DB read remains untested.

## Contract

- Authorized: 200 JSON `{ "id": "meeting-0", "title": "CANARY-0", "anchor_date": "2026-11-13" }`.
- Missing/invalid bearer identity: 401. Missing record or denied grant: 404,
  deliberately indistinguishable and without meeting contents.
- Authenticated malformed identifier: 400; IDs allow 1-128 ASCII letters, digits,
  underscores and hyphens. Dependency/verifier outage or invalid row: 503.
- Success: attachment filename from validated ID, `private, no-store`, `nosniff`.
  Only id/title/date are exported, not transcripts or audio-service records.

## Setup and commands

Use the root README prerequisites and `pnpm install`, `pnpm db:generate`, and
`pnpm --filter @meeting-minutes/database build`. No new dependency was added.
From repository root (npm run uses the existing pnpm-installed dependencies):

```sh
npm --prefix apps/api run test:export
npm --prefix apps/api run test:export:coverage
npm --prefix apps/api run lint
npm --prefix apps/api run typecheck
```

The first command includes unit and loopback HTTP contract/concurrency/load tests.
Without `VT059_DATABASE_URL`, the real DB case is explicitly skipped. The suite
opens ephemeral loopback HTTP ports; restricted sandboxes need network permission.
To run the real Prisma integration and HTTP load checks, use a disposable database,
never `.env` / `DATABASE_URL` or the team's existing database:

```sh
docker run --detach --rm --name bt3-vt059-isolated \
  --env POSTGRES_HOST_AUTH_METHOD=trust --env POSTGRES_DB=vt059 \
  --publish 127.0.0.1::5432 postgres:17-alpine
docker port bt3-vt059-isolated 5432
# Poll until accepting connections; no fixed readiness sleep:
docker exec bt3-vt059-isolated pg_isready -U postgres -d vt059
# Replace PORT with the port printed above (not 5432):
VT059_DATABASE_URL=postgresql://postgres@127.0.0.1:PORT/vt059 \
  npm --prefix apps/api run test:export:coverage
docker stop bt3-vt059-isolated
```

The test rejects non-loopback URLs, non-`vt059` database names and port 5432.
The container is disposable, uses no shared volume and should be stopped after
use. Test-only trust auth is bound to loopback; do not use this setup for hosting.
The real test applies the actual initial migration, seeds 60 uniquely prefixed
synthetic meetings for 20 principals (3 each), and deletes only its own IDs.
The fixture namespace is random for isolation; dataset contents and schedules
are fixed. It characterizes Prisma Date/null/select/filter behavior against real
PostgreSQL. Failure-path tests deliberately inject errors and invalid rows.

## Test matrix and measurement

| ID  | Risk / AC              | Level             | Input and expected behavior                             | Priority |
| --- | ---------------------- | ----------------- | ------------------------------------------------------- | -------- |
| T01 | authorized / AC1       | HTTP              | granted M -> exact id/title/date JSON                   | P0       |
| T02 | identity / AC2         | HTTP              | absent, invalid, empty bearer -> 401                    | P0       |
| T03 | authorization / AC2    | HTTP              | B requests A:M, forged ownerId -> 404, no canary        | P0       |
| T04 | scope / AC3            | HTTP              | M response excludes N, exact payload                    | P0       |
| T05 | absent row / AC4       | HTTP              | permitted missing ID -> 404                             | P1       |
| T06 | dependency / AC4       | HTTP/unit         | throw/invalid row -> 503, no partial export             | P0       |
| T07 | fake/DB mismatch / AC4 | PostgreSQL + HTTP | actual migration/client/query, Date/null and scope      | P0       |
| T08 | mutation / AC2         | HTTP              | permissive adapter still cannot bypass service grant    | P0       |
| T09 | isolation / AC3        | concurrent HTTP   | mixed allowed/forbidden/missing, exact per-task payload | P0       |
| T10 | latency / AC5          | HTTP load         | 100 barrier-released tasks, p95 <= 3000ms               | P1       |
| T11 | validation / AC4       | HTTP              | malformed ID -> 400                                     | P1       |
| T12 | consistency / AC1      | HTTP              | repeated exact schema and download/cache headers        | P2       |

Tests live in `apps/api/test/export/{export,prisma,service}.test.mjs`. The fake
HTTP batch has 10 principals/10 meetings; real DB batch has 20 principals/60
meetings. Each batch asserts all 100 tasks reached a promise barrier, then
releases them together. Node's event loop and connection/DB pools still schedule
execution: this is 100 concurrent tasks, not proof of 100 simultaneous SQL reads.
`performance.now()` measures release-to-full-JSON latency per request, including
client scheduling. p95 is nearest rank: sorted sample index `ceil(.95*n)-1`.
Both success and expected denial payloads are checked; output reports successes,
expected denials, every duration and scope match. JSON diagnostics are emitted to
stdout; redirect them to an ignored local folder for evidence. An expected 404 is
not counted as a successful export. Use repeated runs to assess timing variance.

Shared-state/order flakiness is limited by fresh apps, immutable test grants,
request-local snapshots and uniquely prefixed DB rows with `finally` cleanup.
Timing flakiness is limited by readiness probing, no fixed sleeps, monotonic
clocks and explicit 10-second requests/30-second DB test limits. Local CPU load
can still affect latency. Browser E2E, real identity, revocation, LLM/audio and
external-network tests are outside this backend contract's scope.

For the mutation experiment, temporarily remove the service line
`if (!grants.includes(meetingId)) throw new NotFoundException();`, rebuild and
run `node --test --test-name-pattern='T06/T07' test/export/export.test.mjs` from
`apps/api`. The permissive-adapter T08 case must detect 200 instead of 404.
Restore the line, rebuild and rerun the complete suite. Keep mutation/report
logs local; do not submit vulnerable code.
