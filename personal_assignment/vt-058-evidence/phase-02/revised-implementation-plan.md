# Revised VT-058 Implementation Plan

> Historical Phase 02 proposal after REV-01–03. No production implementation, tests, or benchmarks were performed in Phase 02.

## 1. Revised Architecture

After ExtractionService.extract returns successfully, create one allowlisted event and schedule one bounded FastAPI BackgroundTasks dispatch. Define immutable event and injectable CompletionNotifier.dispatch(event). Use a no-op runtime adapter until a recipient/sink is authorized; automated tests inject a recording fake. Logging is diagnostics only.

Use positive finite notification timeout independent of request timeout. Catch ordinary adapter/scheduling errors, log fixed safe diagnostics, preserve successful HTTP status/body, propagate cancellation. Distinguish event creation, dispatch attempt, and adapter completion (return/raise/timeout). No-op return does not prove user delivery. No durable/exactly-once claim.

## 2. Response-Validation Characterization

Do not add JSON serialization/full route revalidation by default. FastAPI response_model=ExtractionResponse provides structural validation. ResponseBuilder.build calls validate_response_for_request for request-response identity in the verified service. Existing tests cover invalid injected response and identity mismatch. Characterize whether invalid output can reach dispatch; add narrow guard only if a behavioral test proves a production-path gap.

## 3. Affected Files

| Path | Proposed change |
|---|---|
| New apps/llm-service/app/services/notification.py | Event, protocol, no-op adapter, bounded helper, safe diagnostics. |
| apps/llm-service/app/main.py | Accept/store notifier. |
| apps/llm-service/app/api/dependencies.py | App-scoped dependency. |
| apps/llm-service/app/api/routes.py | Create/schedule after extraction; isolate scheduling; preserve response boundary. |
| apps/llm-service/app/core/config.py | Positive finite timeout. |
| New apps/llm-service/tests/fakes/notifier.py | Recording fake separates attempt/normal return. |
| New apps/llm-service/tests/unit/services/test_notification.py | Allowlist, error, timeout, safe diagnostics. |
| New apps/llm-service/tests/integration/test_completion_notification.py | Dispatch, failures, characterization, concurrency. |
| apps/llm-service/tests/integration/test_runtime.py | Exact boundary tests separate from notification. |
| New apps/llm-service/tests/performance/notification_load.py | 200-task experiment and separate timing. |
| apps/llm-service/.env.example | Timeout docs. |
| apps/llm-service/README.md | Event boundary and corrected stale status. |
| New docs/llm/report/vt-058-notification-evidence.md | Later evidence. |

No provider, prompt, extraction rule, schema, App persistence or Prisma changes.

## 4. Revised Red → Green Sequence

1. Characterize existing structural failure/identity checks. Baseline-green characterization is not Red evidence.
2. Add N02 with valid fixtures and recording fake. Red: success response but zero attempts, not import error.
3. Add event/protocol/injection/route scheduling/no-op; verify Green without response-contract change.
4. Add N08–N10 before isolation code: exception + safe diagnostic; waiting fake + timeout/cancellation; registration failure. Implement only needed catch/timeout.
5. Extend auth, validation, provider/evidence, structural response and concurrency tests for no false dispatch/request isolation.
6. Add N12–N14; these may already pass.
7. Run isolated mutations, restore, full suite and performance; record actual evidence. None run in Phase 02.

## 5. Revised Risk Matrix

| ID | Scenario / expected result | Level/path |
|---|---|---|
| N01 | Exactly four event fields. | Unit; tests/unit/services/test_notification.py |
| N02 | Success dispatches once with matching IDs. | API; extend runtime typed-response test |
| N03 | Auth failure: existing 401, zero attempts. | API; extend auth test |
| N04 | Invalid request: existing error, zero attempts. | API; extend validation test |
| N05 | Provider/evidence error mapping, zero attempts. | Service/API; extend verified tests |
| N06 | Invalid injected structural result retains 502 and is not dispatched. | API; extend invalid-response test |
| N07 | Identity mismatch rejected by existing validation; no duplicate route check absent gap. | Contract/service |
| N08 | Notifier exception preserves status/body and safe diagnostics. | API; notification test |
| N09 | Timeout bounded, response unchanged, cancellation observed. | API; notification test |
| N10 | Scheduling failure preserves successful result and safe diagnostic. | API |
| N11 | Concurrent response/event IDs remain associated. | API; extend existing concurrency test |
| N12 | Valid exact-N declared body reaches extraction. | API; runtime test |
| N13 | Valid exact-N streamed body reaches extraction. | Raw ASGI/API; runtime test |
| N14 | Declared/actual N+1 returns 413. | API/raw ASGI; extend oversize tests |
| N15 | Optional exact-limit plus notifier failure preserves response. | API; notification test |

N03/N04 should extend existing tests. N15 is optional interaction coverage.

## 6. Revised Pairwise Strategy

Factors: size small/exact N/over N+1; extraction success/provider-or-evidence failure/structural invalid/request timeout/size reject; adapter returns/raises/times out/not attempted; concurrency 1/2/8 (200 reserved for performance). Constraints: over implies size reject/no attempt; size reject otherwise infeasible; failure means not attempted; success permits return/raise/timeout. Auth/malformed remain targeted.

Generate feasible tuples/value-pairs in fixed order, greedily cover with lexical tie-break, recompute and assert no pair uncovered. Use deterministic UTF-8 serialization/fixed IDs/no randomness. Pairwise supplements targeted cases.

## 7. Revised Mutation Plan

Mutate the declared-length and streamed-byte strict > checks independently. Declared test: valid N-byte JSON, Content-Length N, max N. Stream test: same body chunked with absent/understated header to bypass declared check. Mutant should return 413 while baseline exact N succeeds. Isolate, capture, restore/verify, rerun boundary tests. No mutation performed.

## 8. Revised Performance Experiment

Run 200 synchronized valid requests through FastAPI/verified pipeline with deterministic fake provider/notifier; warm-up and repeat. Report p50/p95/p99, throughput, errors, attempts/completions and notifier latency. Measure response at final body frame; ASGI total call may include background work. Record runtime/machine/payload/fake behavior/timeout/synchronization. Evaluate p95 <=5 sec without presuming result. Fake data does not prove OpenRouter/production throughput.

## 9. Review Log

| Decision | Revised outcome |
|---|---|
| REV-01 | Characterize structural and identity checks; no duplicate round-trip absent demonstrated gap. |
| REV-02 | Injectable CompletionNotifier, recording fake, no-op runtime; logs diagnostic, no user-delivery claim. |
| REV-03 | N12–N14 byte-focused; N02 dispatch; N08/N09 isolation; optional N15. |

## 10. Risks and Uncertainties

App durability outside service boundary. Background work may be lost/repeated; no durable/exactly-once claim. No-op default is not user notification and needs scope confirmation. Avoid raw IDs in logs. Characterize framework behavior after structural validation and real identity guard. Use events/per-test fakes; fake latency is not production latency.

## 11. Recommended Order

1. Developer records at least two evidence-based revisions of AI test proposals.
2. Recheck branch/baseline/status; preserve spec.
3. Characterize response validation; add N02 and capture Red.
4. Implement minimal dispatch boundary and Green.
5. Add isolation/privacy/no-false-completion/concurrency.
6. Add boundary tests, mutate each comparison, restore.
7. Run full suite/200-task experiment and report actual results.
8. Update README/config/evidence with actual outputs/environment/diffs/commits.

Proposed only. No implementation, tests, benchmarks, or notification guarantees were established in Phase 02.
