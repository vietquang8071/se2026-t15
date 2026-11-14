# Phase 06.1 — Test-Quality Review

## Existing tests reused

| Requirement | Existing test reused or extended | Review decision |
|---|---|---|
| N03 authentication failures | `tests/integration/test_runtime.py::test_extraction_rejects_missing_or_invalid_bearer_token` | Preserve all existing auth cases and error assertions; add only service-call and dispatch-attempt counts. |
| N04 request validation | `tests/integration/test_runtime.py::test_extraction_validates_request_before_calling_service` | Preserve existing invalid request/error envelope; add zero service calls and zero notification attempts. |
| N05 provider/evidence failures | `tests/integration/test_verified_extraction_service.py::test_provider_errors_map_without_exposing_provider_details`, `test_unknown_source_id_returns_unverified_evidence_error`, and `test_unsupported_summary_overview_returns_non_success` | Reuse the real verified service and existing scripted provider; no duplicate provider harness. |
| N11 request isolation | `tests/integration/test_verified_extraction_service.py::test_full_pipeline_remains_request_isolated_under_concurrency` | Extend existing full-pipeline concurrent test and replace its sleep with an event barrier. |
| N12–N14 | `tests/integration/test_runtime.py` | Add separate exact declared, exact streamed, and one-byte-over declared/streamed assertions; keep older arbitrary-over-limit coverage intact. |
| N06, N02, N08–N10 | Existing boundary, runtime, and completion-notification tests | Do not modify these tests; run them in focused and full regressions. |

## Review findings

- Boundary byte counts derive from serialized UTF-8 bytes. The request includes Vietnamese text, and the test checks the encoded bytes directly.
- N12 and N13 use direct ASGI request construction to control Content-Length and chunk boundaries. N13 sends multiple chunks and omits Content-Length.
- N14 uses valid request JSON plus one legal trailing whitespace byte; it verifies no extraction or notification occurs on 413.
- N11 synchronizes actual concurrent HTTP calls and candidate provider calls with events. It does not use sleeps as a concurrency mechanism.
- Pairwise rows use an ASGI request gate, deterministic fakes, unique fixed-width IDs, an independent coverage verifier, and bounded request/notifier timeouts.
- Pairwise provider-error cases use the typed extraction error contract; they do not claim to replace N05's real verified-pipeline provider/evidence tests.
- The first focused regression attempt exposed a test setup mistake (`ConcurrentProvider.requests` was asserted but not recorded). The recorder was added in the authorized test file; the failure was not attributed to production behavior. The corrected focused run passed.

## Developer review candidates — correction requirement still pending

These are proposals for independent developer review. No human-authored test correction/removal diff is claimed in Phase 06.1.

### Candidate 1 — N12/N13 duplicated fake extraction setup

- Tests: `test_n12_declared_content_length_accepts_exact_utf8_limit` and `test_n13_streamed_body_accepts_exact_utf8_limit` in `tests/integration/test_runtime.py`.
- Weakness: each defines the same local `CountingExtractionService` class and nearly identical response validation setup. The transport path differs materially, but that fake setup is duplicated.
- Proposed correction: have the developer consolidate the shared fake or factor a small helper while retaining separate declared and streamed request paths. Preserve both tests because each independently targets a different `>` to `>=` mutation.
- Expected benefit: less setup duplication without reducing branch-specific boundary coverage.

### Candidate 2 — Repeated over-limit pairwise rows

- Tests: PW05, PW14, and PW15 in `tests/integration/test_pairwise_completion_notification.py`.
- Weakness to review: all three share `over / size_reject / not_attempted`; their distinguishing factor is concurrency 8, 1, and 2. They do exercise distinct concurrency factor values through the ASGI gate, but all reject before extraction, so they do not demonstrate concurrent extraction work.
- Proposed correction: independently review whether the row assertions and evidence text make this limitation clear enough, or whether a future human-authored presentation should distinguish concurrent HTTP rejection from concurrent service execution. Do not remove or change the approved PW rows without reviewing pair coverage and assignment constraints.
- Expected benefit: avoid overstating what concurrency coverage proves while preserving the required approved dataset.

Both candidates remain unchanged pending developer review. The required human-authored corrections to at least two AI-generated test cases remain **pending**; neither AI implementation nor the original Phase 03 review decisions are being represented as those human code-level corrections.

## Out-of-scope evidence

No test was intentionally weakened or introduced solely to satisfy a correction quota. No mutation, benchmark, live provider call, or production change was performed.
