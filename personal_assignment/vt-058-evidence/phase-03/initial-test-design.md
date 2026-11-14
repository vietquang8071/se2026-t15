# Initial Phase 03 — Risk-Based Test Design

> Historical AI-generated design from Phase 03, before FIX-01, FIX-02 and FIX-03. Preserve this proposal as originally designed; it includes weaknesses later identified by human review. It is a design artifact, not executed test evidence.

## 1. Scope and Existing-Test Reuse

The test design covers VT-058 notification dispatch, failure isolation, privacy, HTTP boundaries, concurrency and performance. It uses the existing LLM Service contract and avoids changing extraction prompts/provider behavior.

Tests recommended for extension:

| Existing test | Proposed initial reuse |
|---|---|
| tests/integration/test_runtime.py::test_dependency_override_returns_typed_extraction_response | Add recording notifier and assert one event on valid result. |
| tests/integration/test_runtime.py::test_extraction_rejects_missing_or_invalid_bearer_token | Assert no notifier attempt for each auth case. |
| tests/integration/test_runtime.py::test_extraction_validates_request_before_calling_service | Assert no notifier attempt for invalid request. |
| tests/integration/test_runtime.py::test_declared_content_length_over_limit_is_rejected | Preserve over-limit check; add exact-size case. |
| tests/integration/test_runtime.py::test_streaming_body_limit_rejects_oversized_body_without_trusting_header | Preserve absent/understated-header checks; add exact-size stream case. |
| tests/integration/test_extraction_pipeline_boundary.py::test_invalid_injected_extraction_response_maps_to_error_envelope | Add notifier and assert no dispatch on structural failure. |
| tests/contract/test_response_models.py::test_cross_request_validation_rejects_identity_or_module_mismatch | Reuse to establish identity validation. |
| tests/integration/test_verified_extraction_service.py::test_provider_errors_map_without_exposing_provider_details | Assert no notifier attempt for provider failure. |
| tests/integration/test_verified_extraction_service.py::test_full_pipeline_remains_request_isolated_under_concurrency | Add notifier event association assertions. |

## 2. Validation Boundaries

**Structural response validation** verifies the returned value conforms to ExtractionResponse. The API declares response_model=ExtractionResponse in app/api/routes.py. test_invalid_injected_extraction_response_maps_to_error_envelope already observes 502 INVALID_STRUCTURED_OUTPUT for a structurally invalid injected result. Extend that behavior with a recording notifier after the notification handoff exists.

**Request-response identity validation** verifies request_id, meeting_id, transcript_revision_id, requested modules, metadata and evidence correspond to the incoming request. ResponseBuilder.build calls validate_response_for_request in app/services/response_builder.py. Contract tests already reject mismatches. This is distinct from structural validation and should remain in the verified service unless a real-path test proves a gap.

## 3. Deterministic Fakes and Fixtures

- Use tests/fixtures/requests/summary_actions_request.json and its matching response fixture for route tests; keep IDs aligned.
- A fake extraction service returns the typed fixed response, raises a configured service error, or waits on an asyncio.Event.
- Reuse the scripted provider approach in test_verified_extraction_service.py for pipeline failure/evidence cases.
- A recording notifier stores attempted events at dispatch entry and completed calls after normal return. It supports raise and wait-until-cancelled modes.
- Each API test gets its own app/fakes. Concurrency fakes use request-keyed events/results and asyncio synchronization, not sleeps.
- Use unique canaries in transcript, token, provider response and error text; never put those canaries in allowlisted IDs.

## 4. Initial N01–N17 Matrix

| ID | Requirement/risk and preconditions | Input / steps | Expected result | Priority; intended file |
|---|---|---|---|---|
| N01 — Event allowlist | Unit; event type available; normal IDs. | Build event and inspect serialized keys/values. | Exactly event_type, request_id, meeting_id, status; no transcript, secret, provider response or extra keys. | P0; tests/unit/services/test_notification.py |
| N02 — Success dispatch | API; valid fixtures; fake extraction service and recording notifier. | POST authenticated valid request. | 200, existing contract body, one matching extraction.completed attempt and fake call returns. | P0; tests/integration/test_completion_notification.py; alternatively extend runtime typed-response test. |
| N03 — Authentication negative | API; valid request; recording notifier. | Missing and invalid bearer requests. | Existing 401 envelope for each; zero notifier attempts. | P0; notification integration tests. |
| N04 — Request-validation negative | API; valid request mutated to invalid timezone or malformed JSON. | POST authenticated invalid request. | Existing validation error; extraction service not called; zero attempts. | P0; notification integration tests. |
| N05 — Provider/evidence failure | Real verified pipeline, scripted provider. | Provider error or rejected evidence verdict. | Existing non-success code/status; zero attempts. | P0; extend test_verified_extraction_service.py. |
| N06 — Structural response failure | API; invalid injected service returns incomplete mapping. | POST using existing invalid response test setup. | Existing 502 INVALID_STRUCTURED_OUTPUT; zero dispatch. | P0; extend test_extraction_pipeline_boundary.py. |
| N07 — Identity mismatch | Contract and service boundary. | Mutate response request/meeting/revision identity in existing parameterized contract test; verify production service rejects before successful return. | Identity mismatch rejected; no completion follows a failed verified extraction. | P0; extend test_response_models.py and relevant verified-service path. |
| N08 — Notifier exception | API; successful fixed service response; raising recording fake with canary exception. | Compare control response and raising-notifier response. | Same successful HTTP status/body; one attempted/no completed call; safe diagnostic excludes exception/canaries. | P0; tests/integration/test_completion_notification.py. |
| N09 — Notifier timeout | API; notifier waits on unset event; short adapter timeout. | POST; observe bounded cancellation with outer watchdog. | Same status/body; one attempt, no completion, cancellation observed, safe timeout diagnostic. | P0; completion notification tests. |
| N10 — Scheduling failure | API; valid extraction; task registration raises. | POST with controlled add_task failure. | Successful response unchanged; adapter not invoked; safe scheduling diagnostic. | P0; completion notification tests. |
| N11 — Concurrent isolation | API; two requests have distinct IDs/content; one notifier call fails. | Release two overlapping requests together. | Each body/event remains associated with its request; one failure does not alter another response. | P0; extend verified pipeline concurrency test. |
| N12 — Declared exact boundary | API; valid request serialized to exactly N bytes; configured max N. | Send raw bytes with Content-Length N. | No size-based 413; fake extraction service is reached and successful response returned. | P0; extend tests/integration/test_runtime.py. |
| N13 — Streamed exact boundary | Raw ASGI/API; valid N-byte body; split into chunks; omit or understate Content-Length. | Deliver chunks to boundary middleware. | No size-based 413; request reaches extraction and succeeds. | P0; extend test_runtime.py. |
| N14 — Over-limit boundary | API/raw ASGI; valid N-byte JSON plus one whitespace byte; max N. | Test honest declared N+1 and streamed actual N+1 without reliable header. | Existing 413 PAYLOAD_TOO_LARGE in both intended paths. | P0; extend runtime oversize tests. |
| N15 — Exact-limit plus notifier failure | API; N-byte valid request and raising notifier. | POST exact-limit input; compare to no-failure control. | Success body/status unchanged; one attempted dispatch and no normal adapter return. | P1; completion notification tests. |
| N16 — Diagnostic privacy | Unit/API; exception contains transcript/token/provider canaries. | Capture event and logs after notifier failure. | No canary or exception text appears; fixed diagnostic category is present. | P0; tests/unit/services/test_notification.py. |
| N17 — 200-task performance | Performance; valid deterministic fake-provider workload and fake notifier. | Synchronize 200 requests, warm up, repeat runs, record response and adapter boundaries. | Report p50/p95/p99, throughput, errors, adapter attempts/completions; compare response p95 to 5 seconds. | P1; tests/performance/notification_load.py. |

## 5. Exact-Byte Request Construction

Start with the valid request fixture, pad transcript text with ASCII x characters, serialize deterministically with UTF-8, ensure_ascii=False and compact separators, then compute N=len(body). Set maximum to N. Exact Content-Length case sends the bytes with header N. Stream case sends two chunks without Content-Length. For over limit, append one ASCII JSON whitespace byte so the JSON remains valid but is N+1 bytes.

The exact-size tests assert byte acceptance and successful extraction processing. They do not need notification assertions.

## 6. Initial Pairwise Design

Factors and order:

- Size: small, exact, over.
- Extraction: success, provider_error, structural_invalid, request_timeout, size_reject.
- Notifier: returns, raises, times_out, not_attempted.
- Concurrency: 1, 2, 8.

Constraints: over requires size_reject/not_attempted; size_reject is invalid at small/exact; all other extraction failures imply not_attempted; successful extraction permits returns/raises/times_out. The 200 concurrency level belongs to the performance experiment.

Selected dataset:

| Row | Size | Extraction | Notifier | Concurrency |
|---|---|---|---|---:|
| PW01 | small | success | returns | 1 |
| PW02 | small | provider_error | not_attempted | 2 |
| PW03 | exact | success | raises | 2 |
| PW04 | exact | structural_invalid | not_attempted | 1 |
| PW05 | over | size_reject | not_attempted | 8 |
| PW06 | small | success | times_out | 8 |
| PW07 | exact | request_timeout | not_attempted | 8 |
| PW08 | small | success | raises | 1 |
| PW09 | small | structural_invalid | not_attempted | 2 |
| PW10 | small | request_timeout | not_attempted | 1 |
| PW11 | exact | success | returns | 2 |
| PW12 | exact | success | times_out | 1 |
| PW13 | exact | provider_error | not_attempted | 1 |
| PW14 | over | size_reject | not_attempted | 1 |
| PW15 | over | size_reject | not_attempted | 2 |
| PW16 | small | success | returns | 8 |
| PW17 | small | success | raises | 8 |
| PW18 | small | success | times_out | 2 |
| PW19 | small | provider_error | not_attempted | 8 |
| PW20 | small | structural_invalid | not_attempted | 8 |
| PW21 | small | request_timeout | not_attempted | 2 |

The design used a fixed Cartesian-product order, feasible-row filter, pair enumeration, and greedy maximum-uncovered-pair selection with first-row tie breaking. The expected design count was 39 feasible combinations, 61 feasible value pairs, 21 selected rows and zero uncovered. Pairwise does not replace targeted boundary/failure cases.

## 7. Initial Red/Green Proposals

- N02: baseline request succeeds but recording fake has zero attempts; expected Red is the count assertion, not an import failure.
- N08: after initial dispatch exists, missing safe notification-specific diagnostic or exception isolation is the Red; compare exact status/body to control.
- N09: use waiting fake, short configured bound and an outer watchdog; baseline without bound does not complete within safety bound.
- N10: controlled task registration failure should expose missing scheduling isolation.
- Existing failure and size cases may be green before notification support; their no-dispatch assertions are not feature Red by themselves.

## 8. Initial Weak-Test Review Candidates

1. N03/N04 duplicate existing authentication/request-validation status tests; extend existing tests with no-dispatch assertions instead.
2. N16 overlaps N08’s canary-bearing exception/privacy assertions; merge unless it tests an independent helper contract.
3. N15 can duplicate exact-boundary plus notifier-failure coverage; retain only if interaction coverage is valuable.
4. A route identity-mismatch fake may bypass the verified service and misrepresent production behavior.

The developer must independently correct/remove at least two in later implementation and preserve actual code diffs. No test code was changed in Phase 03.

## 9. Initial Test Commands and Evidence

From apps/llm-service, proposed commands:

`uv run --locked --extra test pytest -q tests/integration/test_completion_notification.py -vv`

`uv run --locked --extra test pytest -q tests/integration/test_runtime.py`

`uv run --locked --extra test pytest -q tests/integration/test_verified_extraction_service.py`

`uv run --locked --extra test pytest -q`

Performance proposal: `uv run --locked --extra test python tests/performance/notification_load.py --requests 200 --concurrency 200 --warmups 1 --runs 3`.

Capture baseline/commit SHA, exact command, timestamp, runtime/environment, exit status, genuine Red assertion, focused/full Green output, coverage mapping, mutation and restoration evidence, benchmark metrics and human test-correction diffs. No results were executed or established.
