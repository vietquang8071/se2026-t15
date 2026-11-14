# Initial VT-058 Implementation Plan

> Historical Phase 02 AI proposal before human review. This plan was not implemented.

## 1. Repository and Git Baseline

Repository vietquang8071/se2026-t15; assignment branch feature/vt-058-llm-notification; reference feature/llm-03-provider-integration; baseline 5e54822fca535972ef9b10a7d39dfbabc7df4b3d. Branches were identical (0 ahead/0 behind). Working tree had untracked personal_assignment/ containing the spec; no staged/tracked edits. Preserve it.

## 2. Specification Summary

Emit extraction.completed only after successful validated extraction; never after authentication, request validation, provider, response validation, evidence, or request-timeout failure. Notification exceptions/timeouts cannot change successful HTTP status/body. Allow event_type, request_id, meeting_id, status only; no transcript/secrets/provider response. Preserve existing request/response contract and body limit (exact valid size accepted, greater size is 413 PAYLOAD_TOO_LARGE). NFR: bounded failures, safe diagnostics, 200 concurrent tasks, p95 <=5s, compatibility. Request timeout is not the p95 goal. LLM Service does not own App transaction; no DB durability, durable delivery, or exactly-once claims.

## 3. Current State

create_app in apps/llm-service/app/main.py composes the verified service and stores dependencies. create_extraction in app/api/routes.py runs extraction inside asyncio.timeout and declares response_model=ExtractionResponse. VerifiedExtractionService.extract runs orchestration, projection, source validation, evidence verification, temporal safeguards and response building. ResponseBuilder.build calls validate_response_for_request.

ExtractionRequestBoundaryMiddleware in app/core/middleware.py checks declared Content-Length and accumulated streamed bytes; each currently uses strict >. Existing tests cover auth, request validation, provider/errors/timeouts, invalid injected output, concurrency, and oversized bodies. No notifier/event exists. README and architecture/contract docs have stale status; product/roadmap scope exceeds current runtime. Do not change extraction behavior.

## 4. Initial Proposed Solution

Add immutable event, async notifier protocol, and default in-process logging adapter. Inject via create_app/dependency. In create_extraction serialize to JSON mode and fully revalidate response and request identity before scheduling FastAPI BackgroundTasks. Add positive finite notification timeout. Catch scheduling/notifier failures, log safe diagnostics, preserve success response, propagate cancellation.

This proposal used logging as the in-process event sink. Event creation, task scheduling, and task execution are distinct; no durable/exactly-once claim.

Alternatives: route handoff after explicit revalidation (recommended, but duplicate checks); notify inside VerifiedExtractionService (couples side effect and request timeout); custom FastAPI response wrapper (later lifecycle but more framework complexity).

## 5. Initial Affected Files

| Path | Proposal |
|---|---|
| New apps/llm-service/app/services/notification.py | Event, protocol, logging adapter, bounded helper. |
| apps/llm-service/app/main.py | Inject/store notifier. |
| apps/llm-service/app/api/dependencies.py | Notifier dependency. |
| apps/llm-service/app/api/routes.py | Round-trip/revalidate, event/task scheduling, failure isolation. |
| apps/llm-service/app/core/config.py | Notification timeout. |
| New apps/llm-service/tests/unit/services/test_notification.py | Event and delivery tests. |
| New apps/llm-service/tests/integration/test_completion_notification.py | HTTP success/failure/timeout/concurrency tests. |
| apps/llm-service/tests/integration/test_runtime.py | Exact boundary cases. |
| New apps/llm-service/tests/performance/notification_load.py | 200-task experiment. |
| apps/llm-service/.env.example; apps/llm-service/README.md | Timeout, behavior, commands, stale status. |
| New docs/llm/report/vt-058-notification-evidence.md | Later execution evidence. |

No provider, prompt, App persistence, schema, or Prisma changes.

## 6. Initial Test-First Breakdown

Write positive dispatch test first; Red must be zero event attempts, not import failure. Add no-event tests for auth, request validation, provider/evidence, response validation, and request timeout. Add notifier exception/timeout, task-registration failure, safe diagnostics, and exact successful body comparison. Add exact size and over-limit tests, concurrency, and pairwise coverage. Mutate each > to >= separately in isolated temporary experiment, restore, and verify. Run focused/full suite and load experiment later; capture output/environment/commit refs. Nothing was run in planning.

## 7. Initial Risk Matrix

| ID | Case / expected result | Level/path |
|---|---|---|
| N01 | Event exactly allowlisted fields; no sensitive content. | Unit; tests/unit/services/test_notification.py |
| N02 | Successful verified request dispatches once; contract unchanged. | API; tests/integration/test_completion_notification.py |
| N03 | Auth failure is 401, no event. | API; notification tests |
| N04 | Invalid request returns existing error, no event. | API; notification tests |
| N05 | Provider/evidence error keeps existing mapping, no event. | Verified pipeline |
| N06 | Invalid injected result errors, no event. | API; extend test_extraction_pipeline_boundary.py |
| N07 | Request timeout gives existing 504, no event. | API; test_runtime.py |
| N08 | Notifier exception preserves success status/body; safe diagnostics. | API/unit |
| N09 | Notifier timeout bounded and response unchanged. | API/unit |
| N10 | Scheduling failure does not alter result. | API |
| N11 | Concurrent request/event IDs stay isolated. | API |
| N12 | Valid N-byte declared body accepted. | API; test_runtime.py |
| N13 | Valid N-byte streamed body accepted. | Raw ASGI; test_runtime.py |
| N14 | Declared/streamed N+1 gives 413. | API/raw ASGI |
| N15 | 200 tasks report percentiles, throughput, errors and notification timing. | Performance script |

N03/N04 overlap existing checks and could extend those. N06 must distinguish response and request validation.

## 8. Initial Pairwise Strategy

Factors: size small/exact N/over N+1; extraction success/provider-or-evidence failure/response invalid/request timeout/size rejection; notification delivered/exception/timeout/not attempted; concurrency 1/2/8 (200 reserved for performance). Over-limit implies size rejection/no notification; failed extraction implies no notification; success allows delivery/exception/timeout. Auth/malformed remain targeted.

Generate feasible rows in fixed order, enumerate feasible value pairs, deterministic greedy set cover with lexical tie-break, verify none uncovered. Use fixed UTF-8 JSON/IDs and no randomness/network. Pairwise supplements targeted tests.

## 9. Initial Mutation Strategy

In ExtractionRequestBoundaryMiddleware mutate declared length and accumulated stream strict > to >= independently. Declared test: valid N bytes, Content-Length N, maximum N. Stream test: same valid bytes in chunks without or with understated header. Exact test should reach target and fail 413 under mutation. Use isolated temporary experiment, restore and verify, rerun boundary cases. No mutation occurred.

## 10. Initial Performance Strategy

200 synchronized deterministic requests with fake provider/notifier, warm-up and repeated runs. Report p50/p95/p99, throughput, error rate, notification timing and environment. Measure HTTP response at final body frame and notification separately; ASGI total call may include background work. Keep boundary tests separate. Fake results do not prove OpenRouter/production latency.

## 11. Risks and Residual Limitations

No App transaction ownership; background work may be lost on cancellation/restart and repeated on retries; no exactly-once/durable guarantee. JSON round trip duplicates existing checks. Caller IDs may contain arbitrary strings, so raw logs can leak. Fixed sleeps/shared state risk flaky tests; use events/per-test fakes. Fake load is not provider throughput. Docs have stale status. Fake App persistence harness cannot prove DB durability.

## 12. Human Review Checkpoints

Review route validation, logging sink, timeout, ID logging, event scope, duplicate tests, pairwise coverage, performance boundaries and docs mismatches. REV-01–03 later revised initial assumptions; this file preserves them.

## 13. Initial Execution Sequence

1. Capture branch/baseline/status and preserve spec.
2. Add positive test, capture Red.
3. Implement event/log adapter/injection/route scheduling/timeout; capture Green.
4. Add failure, concurrency and boundary tests.
5. Run pairwise/mutations and restore.
6. Full suite and 200-task experiment.
7. Update README/env/evidence with actual data.

Planning only.
