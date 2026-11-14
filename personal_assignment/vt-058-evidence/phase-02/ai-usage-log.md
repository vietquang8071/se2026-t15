# AI Usage Log — Phase 02

> Exact timestamps were not recorded. This log covers Phase 02 only. It distinguishes AI proposals, human decisions, approved constraints, and future work. It does not claim tests, benchmarks, implementation, commits, or notification delivery.

| ID | Tool | Prompt / Task | AI Output | Human Decision | Evidence |
|---|---|---|---|---|---|
| AI-02-01 | Codex assistant; exact model/time not recorded | Full initial task prompt reproduced below. | Initial implementation plan; included route JSON round-trip/revalidation and logging adapter. | AI proposal only; later revised. | initial-implementation-plan.md and personal_assignment/vt-058.md. |
| AI-02-02 | Developer review in conversation | Full human review prompt reproduced below. | Not applicable; this records human review. | REV-01, REV-02, REV-03 each REVISE. | human-review.md and cited source files. |
| AI-02-03 | Codex assistant; exact model/time not recorded | Apply the three decisions and revise the initial plan. This task was requested in AI-02-02; no separate follow-up prompt was recorded. | Revised implementation plan reflecting all three decisions. | Revised output remains a proposal; no implementation approval/evidence. | revised-implementation-plan.md. |
| AI-02-04 | No separate tool/task recorded | No separate final-assessment prompt or independent assessment event appears in the Phase 02 discussion. | Revised plan’s risk/uncertainty sections contain the final engineering assessment; it is not a separate action/result. | No separate human decision recorded. | revised-implementation-plan.md; no execution evidence. |

## Full Prompt — AI-02-01

> You are a Senior Software Architect, Technical Lead, and Test-Driven Development Engineer working on SE2026-T15 — AI-05 Meeting Minutes Assistant.
>
> Your task is to produce an evidence-based implementation plan for BT3 — VT-058 before any implementation begins.
>
> **Repository and branch:** repository vietquang8071/se2026-t15; local workspace /home/vitquay1708/Study_Space/SE; assignment branch feature/vt-058-llm-notification; parent/reference branch feature/llm-03-provider-integration; target apps/llm-service; authoritative specification personal_assignment/vt-058.md. The assignment branch already exists. Do not create or switch branches.
>
> Before analyzing: read the complete specification; confirm branch; inspect working-tree status without modifying it; record current HEAD SHA as baseline; verify branch relationship; report uncommitted changes. If the branch is wrong, specification cannot be accessed, or repository state is inconsistent, report and stop without modification. Specification is source of truth for requirements; source code is source of truth for existing behavior. Identify discrepancies.
>
> **Mandatory read-only:** do not create, edit, overwrite, move, or delete files; modify the spec; generate/apply patches; change branches or Git state; install dependencies; run state-changing commands; create Issues/PRs; implement features or write tests. Inspect files, run non-mutating Git inspection, analyze existing tests, and propose changes. Stop after plan and wait for explicit developer approval.
>
> **Repository investigation:** read docs/product-description.md, docs/feature-overview.md, docs/implementation-roadmap.md, CONTRIBUTING.md, relevant architecture/API contracts; inspect apps/llm-service main.py, routes.py, dependencies.py, extraction.py, verified_extraction.py, factory.py, middleware.py, config.py, errors.py, schemas, tests, fixtures, fake providers, and additional lifecycle files. Cite architectural conclusions by actual path and function/class. Separate implemented, documented-but-not-implemented, and VT-058-proposed behavior. Do not invent services/endpoints/transactions/notification mechanisms.
>
> **Approved decisions:** introduce extraction.completed only after successful validated extraction. Failures must not create false completion. Use a best-effort injectable adapter; keep the slice small/testable/maintainable; no external email/SMS, brokers, new database tables/migrations, unnecessary framework, or unjustified dependencies. Use fake notifier in tests. Notification exceptions/timeouts must not alter successful extraction.
>
> The primary operation is extraction; notification is secondary. LLM Service does not own App PostgreSQL transaction. Do not claim extraction tests prove database durability. Identify App durability and notification-delivery risks; evaluate whether a small executable characterization harness adds evidence without scope growth. Do not redesign the system.
>
> Preserve exact spec criteria: success event, no false event after auth/validation/provider/response/evidence/timeout failures, exception/timeout isolation, safe allowlisted metadata, large-input boundary behavior, compatibility. Include 200 concurrent tasks and p95 <=5.0 seconds. Do not equate request timeout with the performance target.
>
> Trace HTTP request → authentication → request-size validation → Pydantic validation → extraction orchestration → provider calls → source/evidence validation → response construction → HTTP response. Analyze asyncio.timeout, FastAPI response validation, service error handling, scheduling/execution failures, notification timeouts, task lifecycle/cancellation, concurrent isolation, transcript/secret leakage, response schema. Compare at least two reasonable designs; recommend the smallest. Distinguish event creation, dispatch/scheduling, and delivery completion. Do not claim exactly-once or durable delivery.
>
> **Test-first plan:** genuine Red → Green steps; test first; observable behavior; why test fails before implementation; avoid import errors/missing files as sole Red evidence; smallest patch; full regression suite; future output and Git references. Do not execute plan.
>
> **Risk-based tests:** at least 10 detailed cases with ID, requirement/risk, level, preconditions, input, expected result, priority and file. Cover unit/API/service-level E2E, two negative cases, a primary-risk failure path, exceptions/timeouts, large/exact boundaries and concurrency. Identify unnecessary tests.
>
> **Pairwise:** define factors/values/constraints/infeasible combinations, generation method/tool, pair coverage verification, high-risk targeted cases and deterministic data. Pairwise is not boundary coverage.
>
> **Mutation:** identify both existing body-size conditions in apps/llm-service/app/core/middleware.py. Plan deliberate > to >= mutation for declared Content-Length and actual streamed bytes. Exact-boundary test must reach intended condition, not fail earlier. Mutation only later in isolated temporary experiment; never leave mutant in branch.
>
> **Performance/reliability:** reproducible 200 concurrent tasks, deterministic requests, fake LLM provider/notifier, synchronization, latency collection, p50/p95/p99, throughput/error rate, warm-up/repeated runs/environment. Separate extraction response latency, notification processing/dispatch latency, large payload boundary. Explain fake-provider limitations. Identify flaky risks and mitigations.
>
> List every proposed file, state existing/new, change, reason, acceptance criteria, tests and priority. State assumptions/uncertainties, alternatives, possible overengineering, coverage gaps, architecture mismatch. Developer will independently review and reject/revise at least two weak/duplicate AI-generated tests. Do not fabricate review, test, benchmark, or commit evidence.
>
> Required sections: Repository and Git Baseline; Specification Summary; Current State; Proposed Solution; Affected Files; Test-First Task Breakdown; Risk-Based Test Matrix; Pairwise Testing Plan; Mutation Testing Plan; Performance Testing Plan; Risks and Residual Limitations; Human Review Checkpoints; Recommended Execution Order.
>
> Final instruction: stop after presenting plan; do not create/modify files, tests, branches, commits, or PRs.

## Full Prompt — AI-02-02

> Review and revise your existing VT-058 implementation plan based on human engineering review.
>
> **REV-01 — Response Revalidation:** Initial AI proposes JSON serialization and full route response-validation round trip. Existing app/services/response_builder.py calls validate_response_for_request(); app/api/routes.py declares response_model=ExtractionResponse; tests/integration/test_extraction_pipeline_boundary.py covers invalid injected responses. Decision REVISE: require characterization before extra route validation; distinguish structural validation from request-response identity validation; avoid duplicate serialization/revalidation unless a failing test demonstrates the need.
>
> **REV-02 — Logging Is Not Notification Delivery:** Initial AI uses an in-process logging adapter. Logging does not prove an independent notification boundary was invoked or a recipient received a notification. Decision REVISE: use injectable CompletionNotifier with recording fake; logging is diagnostics only; revised design uses no-op runtime adapter until real recipient/sink is authorized. No email, external broker, or migration. Do not claim real user notification/durable delivery.
>
> **REV-03 — Boundary Test Separation:** Initial AI combines exact-byte boundary tests and notification assertions. Middleware is a distinct HTTP concern. Decision REVISE: N12–N14 focus on byte-limit semantics and successful request processing; notification success primarily N02, failure isolation N08/N09; one separate combined-risk case may be used.
>
> Required output: revised architecture and files, revised Red → Green breakdown, updated test matrix, pairwise and mutation plans, explicit review log with evidence, and remaining approval questions. Do not fabricate results. Stop after revised plan.

## AI-02-03 Prompt Availability

No separate user message for AI-02-03 exists: revising the plan was the requested action in the AI-02-02 review prompt. The revised plan is the output to that instruction. This log does not treat the later Phase 03 test-design request as Phase 02 evidence.

## Approved Decisions and Future Work

Developer-approved constraints: best-effort injectable adapter, allowlisted event after successful validated extraction, no external delivery service/broker/migration. REV-01–03 are human decisions in human-review.md. Adapter implementation, tests, mutation, load experiment, and evidence capture remain future work. No tests, benchmarks, implementation, commits, or delivery were performed in Phase 02.
