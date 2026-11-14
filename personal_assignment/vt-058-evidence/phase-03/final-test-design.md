# Final Phase 03 Test Design — VT-058

> Authoritative test design for a future implementation phase. Documentation only: no tests, benchmarks, mutations, or implementation were executed.

## 1. Scope and Objectives

Cover AC-01 through AC-05 and NFR-01 through NFR-04 in personal_assignment/vt-058.md. Keep extraction primary and notification secondary. Use a CompletionNotifier port with recording fake; logging is diagnostic, and a no-op runtime adapter is not user delivery. Do not claim App transaction durability, durable notification, or exactly-once processing.

The design adds N18 for large valid payload timeout, corrects test classifications, retains the complete pairwise set, separates large-payload resource measurements from the 200-request concurrency experiment, and identifies human corrections required later.

## 2. Existing Tests to Reuse

| Existing test/path | Final use |
|---|---|
| tests/integration/test_runtime.py::test_dependency_override_returns_typed_extraction_response | Extend with N02 recording fake dispatch count and event fields. |
| tests/integration/test_runtime.py::test_extraction_rejects_missing_or_invalid_bearer_token | Extend with N03 zero attempts; do not duplicate HTTP status checks. |
| tests/integration/test_runtime.py::test_extraction_validates_request_before_calling_service | Extend with N04 zero attempts/service not called. |
| tests/integration/test_runtime.py::test_request_timeout_maps_to_retryable_contract_error | Keep existing timeout assertion; use N18 for the distinct large-valid-input path. |
| tests/integration/test_runtime.py::test_declared_content_length_over_limit_is_rejected | Extend boundary group with exact N and preserve existing over-limit assertion. |
| tests/integration/test_runtime.py::test_streaming_body_limit_rejects_oversized_body_without_trusting_header | Extend boundary group with exact streamed N; preserve absent/understated header cases. |
| tests/integration/test_extraction_pipeline_boundary.py::test_invalid_injected_extraction_response_maps_to_error_envelope | Extend N06 with zero dispatch after characterization. |
| tests/contract/test_response_models.py::test_cross_request_validation_rejects_identity_or_module_mismatch | Use for N07 identity contract, distinct from FastAPI structural validation. |
| tests/integration/test_verified_extraction_service.py::test_provider_errors_map_without_exposing_provider_details | Extend N05 with zero attempts. |
| tests/integration/test_verified_extraction_service.py::test_full_pipeline_remains_request_isolated_under_concurrency | Extend N11 with per-request notification association. |
| tests/integration/test_verified_extraction_service.py::test_request_timeout_maps_separately_from_provider_timeout | Retain distinction between provider timeout and request timeout. |

## 3. Deterministic Fixtures and Fakes

- **Request/response:** use existing summary-actions request and response fixtures. For each request, align request_id, meeting.id, transcript.revision_id, requested modules and response fields.
- **Static extraction fake:** configurable async outcome: typed response, existing service exception, or waiting operation. It tracks calls and cancellation, keyed by request_id where concurrent.
- **Provider fake:** reuse the existing scripted fake/provider pattern for service-level failure/evidence tests. No outbound provider access; tests/conftest.py already blocks network.
- **Recording notifier:** record attempted event at dispatch entry and completed event only after normal return. Support raise and event-wait timeout cases; track cancellation. Use a fresh instance per test and asyncio.Lock or per-request storage for concurrent tests.
- **Large input:** construct valid request from fixture and pad a transcript text with ASCII x. Use deterministic UTF-8 compact JSON. Keep body <= max. No transcript canary or secret is written to logs.
- **Response validator:** structural-invalid test uses the existing incomplete mapping. Identity mismatch uses the contract validator test and real verified-service failure semantics; do not infer identity from structural validation alone.

## 4. Final N01–N18 Matrix

Classifications:
- **Feature RED:** baseline lacks the behavior; failure must be an observable assertion.
- **Staged RED:** written after the initial dispatch path exists; exposes missing isolation/hardening.
- **Characterization:** documents behavior already present.
- **Regression:** confirms existing behavior after changes.
- **Mutation:** intended to kill deliberate temporary mutant.
- **Performance:** measurement, not an assertion of guaranteed production performance.

| ID / name | Requirement or risk; preconditions, fixtures, input and steps | Expected outputs and dispatch | Priority / level / path / classification |
|---|---|---|---|
| N01 Event contract allowlist | AC-04. Event type available after initial boundary. Construct event from normal IDs and completed status; serialize/inspect key set. | Exactly event_type, request_id, meeting_id, status. No transcript, bearer token, provider secret/response, or extra key. | P0; unit; tests/unit/services/test_notification.py; staged RED |
| N02 Successful dispatch | AC-01. Existing valid request/response fixtures, static extraction fake, recording notifier. POST authenticated request through create_app route. | HTTP 200 and existing ExtractionResponse contract; exactly one attempted event with matching request/meeting IDs/status. Fake completes normally. | P0; API; extend tests/integration/test_runtime.py::test_dependency_override_returns_typed_extraction_response; genuine feature RED |
| N03 Authentication failure | AC-02. Existing auth test cases and recording fake. Send absent/wrong bearer. | Existing 401 envelope; zero dispatch attempts; existing service/provider non-invocation assertion retained. | P0; API regression; extend test_runtime.py::test_extraction_rejects_missing_or_invalid_bearer_token; regression |
| N04 Request validation failure | AC-02. Existing fixture with invalid timezone or malformed request; recording fake. POST authenticated request. | Existing validation error; zero attempts; extraction service not called. | P0; API regression; extend test_runtime.py::test_extraction_validates_request_before_calling_service; regression |
| N05 Provider/evidence failure | AC-02/I-02. Real verified pipeline, scripted provider configured to raise or produce rejected evidence, recording notifier. | Existing provider/evidence status and code; zero attempts. Existing behavior may pass before notifier support. | P0; service/API; extend test_verified_extraction_service.py provider/evidence failure cases; regression, not claimed feature RED |
| N06 Structural response failure | AC-02. Existing InvalidExtractionService returns incomplete mapping; attach recording notifier; send valid request. | Existing 502 INVALID_STRUCTURED_OUTPUT; zero adapter attempts. Characterize FastAPI response_model execution/task behavior. | P0; API; extend test_extraction_pipeline_boundary.py::test_invalid_injected_extraction_response_maps_to_error_envelope; characterization then regression |
| N07 Request-response identity mismatch | AC-02/response integrity. Contract fixture mutated in request_id/meeting_id/revision/module cases; exercise validate_response_for_request. Preserve the distinction from structural model validation. | Existing identity validator rejects mismatch. Real verified service must not return success on identity failure; route does not duplicate identity check without evidence. | P0; contract/service; extend tests/contract/test_response_models.py::test_cross_request_validation_rejects_identity_or_module_mismatch; characterization |
| N08 Notifier exception isolation/privacy | AC-03/04, I-01. Valid fixed extraction result; control fake and raising notifier carrying unique transcript/token/provider/exception canaries. Run control and failure request with same serialized response fixture; capture logs. | Both HTTP status and raw response body identical. One dispatch attempt, none completed. Fixed diagnostic only; no exception text or canary in event/log. Merge N16 assertions here. | P0; API; tests/integration/test_completion_notification.py; staged RED |
| N09 Notifier timeout/cancellation | AC-03/NFR-01. Valid extraction; fake waits forever on asyncio.Event, marks cancellation in finally. Configure short notifier timeout and outer safety bound. | Same success status/body as control; one attempt, no normal completion, cancellation observed, safe timeout diagnostic. | P0; API/unit; notification tests; staged RED |
| N10 Task scheduling failure | AC-03/NFR-01. Valid extraction; controlled monkeypatch/injected scheduler makes BackgroundTasks.add_task fail. | Same successful status/body as control; notifier never called; fixed safe diagnostic. | P0; API; notification tests; staged RED |
| N11 Concurrent request isolation | I-01. Extend existing full-pipeline concurrency test with 2+ requests, unique IDs/segments and recording notifier; one notification raises. Synchronize with events/barrier, not sleep. | Responses retain their own content/IDs; event attempts map to successful request; one failure cannot alter another response. | P0; service/API; extend test_verified_extraction_service.py::test_full_pipeline_remains_request_isolated_under_concurrency; regression |
| N12 Declared Content-Length exact N | AC-05. Valid request JSON bytes exactly N, setting max=N, static extraction response matching request. Send raw body with Content-Length N. | Not 413; fake extraction reached; request succeeds. Does not assert notification. | P0; API; extend tests/integration/test_runtime.py; characterization and mutation-killing |
| N13 Streamed exact N | AC-05. Same valid N-byte body, raw ASGI split into two chunks, omit Content-Length; max=N. | Not 413; fake extraction reached; success. Does not assert notification. | P0; raw ASGI/API; extend test_runtime.py; characterization and mutation-killing |
| N14 Over-limit declared/streamed N+1 | AC-05. Valid body plus one trailing JSON whitespace byte; max=N. For declared branch send Content-Length N+1. For stream branch omit length and deliver N+1 bytes. | Existing 413 PAYLOAD_TOO_LARGE. Separate cases prove declared and actual-body paths. No notification assertion. | P0; API/raw ASGI; extend existing oversize tests; regression |
| N15 Exact-limit plus notifier failure | AC-03/05 interaction. Exact-N valid request; fixed extraction result; control and raising recording notifier. | Success status/body match control; body is accepted at N; one attempt/no normal adapter return. Keep only if this interaction is judged useful. | P1; API; completion notification tests; regression |
| N16 Diagnostic privacy standalone | Initial separate test proposal. | **Do not create a separate test function by default.** Merge the independent privacy canaries/assertions into N08. Retain standalone unit test only if it proves a distinct dispatch-helper contract. | P0 requirement covered by N08; candidate removed/merged in final design |
| N17 200-concurrent-task performance | NFR-02. Real FastAPI/verified pipeline with deterministic fake provider and fake notifier; 200 valid requests with unique IDs; gate-release synchronization; warm-up and repeated runs. Instrument final response body frame separately from adapter completion. | Report p50/p95/p99, throughput, HTTP/error rate, dispatch count, adapter completion and latency. Compare measured HTTP response p95 with ≤5.0 sec; do not prestate pass. | P1; performance script; performance |
| N18 Large valid input request timeout | Primary large-input/timeout risk, AC-02/NFR-01. Build a structurally valid JSON request approaching but below max bytes (e.g. max minus fixed 512 bytes), using ASCII text padding. Verify computed UTF-8 body size <= configured max. Use controlled fake extraction service waiting on Event, short request timeout, recording notifier, and outer safety watchdog (e.g. 5 sec). POST body; fake records entry and cancellation. | HTTP 504 with existing REQUEST_TIMEOUT envelope; request was not rejected with 413; extraction fake was entered/cancelled; zero completion dispatch; test itself terminates within watchdog. No OpenRouter call. | P0; API; new tests/integration/test_large_input_timeout.py or completion integration file; regression/risk characterization |

### N18 exact construction controls

Set test max to a documented value such as 1 MiB to keep one near-limit test practical; define the payload target deterministically, e.g. N=max−512. Build body with ensure_ascii=False and compact separators, calculate byte length after serialization, and pad only safe ASCII transcript text so the size is exact. Assert precondition N<=max before sending. The 1 MiB test limit is a configured test limit, not a claim about production default.

Use a notifier fake whose dispatch count remains zero. A separate outer asyncio.wait_for watchdog protects the test runner; it is not the service request budget. Verify 504 REQUEST_TIMEOUT rather than 413 PAYLOAD_TOO_LARGE.

## 5. Test Levels and Reuse

- **Unit:** event field allowlist, bounded dispatch helper and exception safety.
- **API/integration:** route dispatch, auth/request errors, response-model failure, request timeout, body boundaries.
- **Service-level end-to-end:** actual VerifiedExtractionService with scripted fake provider for provider/evidence errors.
- **Performance:** 200-task HTTP latency experiment and separate large-input resource experiment.

Do not add separate tests duplicating N03/N04’s existing status/body assertions; add the new zero-dispatch assertion to existing tests.

## 6. Large-Input Latency and Memory Experiment

Run a distinct, deterministic experiment using valid payload sizes such as 25%, 75%, and N=max−512 bytes with fake extraction service returning a fixed response immediately. Do not call OpenRouter. Vary concurrency modestly (1, 2, 4, optionally 8) and use a bounded number of requests. Never allocate 200 maximum-size payloads simultaneously.

Record payload UTF-8 bytes, concurrency, response p50/p95/p99, throughput, errors, Python/platform, max-request setting, and method. For memory, run one measurement scenario per fresh process if using resource.getrusage peak RSS; document OS units. Optionally record tracemalloc peak allocations as Python-only allocation evidence. No memory threshold is specified, so report measurements, do not invent pass criteria.

Keep this experiment separate from N12/N13 mutation boundaries and N17 200-task latency target.

## 7. Complete Pairwise Dataset PW01–PW21

Factors/order:

- Size: small, exact, over.
- Extraction: success, provider_error, structural_invalid, request_timeout, size_reject.
- Notifier: returns, raises, times_out, not_attempted.
- Concurrency: 1, 2, 8.

Constraints:

- over implies size_reject and not_attempted.
- size_reject is infeasible for small/exact.
- provider_error, structural_invalid, request_timeout imply not_attempted.
- success allows returns/raises/times_out.
- concurrency 200 is only the separate load experiment.

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

Independent design recomputation: the constraints yield 39 feasible full combinations and 61 feasible factor-value pairs. The 21 selected rows cover all 61; uncovered=0. This is combinatorial calculation only, not a test run.

**Reproducible verification method:** Generate Cartesian product in factor order above; filter by constraints; enumerate every pair of factors/values present among feasible rows; derive same pair set from PW01–PW21; assert selected rows are unique, all feasible pairs are covered, and report any uncovered pair. To regenerate the selected set, greedy-select the earliest row covering the most uncovered pairs until coverage is complete. Fixed factor order and deterministic tie-breaking make output reproducible.

## 8. Correct Red/Green Classification

### Genuine Feature RED

**N02** is the primary genuine Red. Baseline state: route has no notifier behavior. In the first test-only revision, install a recording callable on the route module with `monkeypatch.setattr(..., raising=False)` at the agreed dispatch-hook name; do not import a not-yet-existing notifier class or dependency. Send a valid request through the existing route, then assert that the fake recorded exactly one correctly populated event. On baseline the endpoint should still execute and the behavioral count assertion should fail with zero calls; an import/attribute setup error is not accepted as Red evidence. When the injectable `CompletionNotifier` dependency is implemented, change the fixture to override that dependency while preserving the same observable event assertion. The HTTP response itself may already be 200; that is not the Red. Intended Green: exactly one correctly populated dispatch attempt and unchanged response. Record focused failure output and assertion location.

### Staged RED

- **N08:** after N02 route dispatch exists but before exception-isolation/diagnostic handling. Fake records attempt then raises. Red assertion is missing fixed notification-failure diagnostic or observable isolation helper behavior; compare status/body against control. Do not claim HTTP-body difference if framework already sends response before background work.
- **N09:** after notifier dispatch exists but before bounded timeout. Fake waits forever; setting supplies short notifier bound and outer watchdog. Red is failure to complete/cancel within test safety bound. Intended Green is service-configured timeout, cancellation observed, response preserved.
- **N10:** after route scheduling exists but before scheduling-failure catch. Controlled scheduler raises; Red is response mismatch/unhandled failure or missing fixed diagnostic. Green preserves successful result and makes no adapter call.
- **N01:** after event model exists, deliberately include an unauthorized extra field in a test construction path; expected exact-key assertion fails. Green limits serialized event to allowlist.

Each Red is captured before the relevant isolation/hardening patch. An import error alone is not accepted.

### Characterization

N06 current structural-error envelope; N07 existing identity validator; N12/N13 exact-limit acceptance; existing 413, auth, request validation, provider and timeout mappings. These may already pass and must not be reported as feature Red.

### Regression

N03–N05, N06–N07 no-dispatch extension, N11 and N18 verify behavior remains correct after notification changes. N18 is a direct risk regression; the service already has request timeout handling.

### Mutation-Killing

N12 kills declared-length >→>=. N13 kills streamed-count >→>=. Each uses exact N and isolates its intended branch.

### Performance

N17 and the separate large-input resource experiment report actual measurements; neither is pass/fail Red/Green evidence until thresholds and execution are recorded.

## 9. Mutation Procedure

Current targets are declared Content-Length comparison in ExtractionRequestBoundaryMiddleware at the declared-length branch and accumulated bytes comparison at the streamed branch. Mutate one at a time from > to >= in a temporary isolated copy.

- Declared mutant: N12 exact valid body, header N, max N; mutant should return 413 before reading.
- Stream mutant: N13 exact valid body split into chunks with no Content-Length; reaches actual byte check and mutant should return 413.

Capture mutation diff and intended test failure. Restore source and verify both comparisons are original. Run N12–N14 after restore. Never leave mutant in branch. No mutation was executed.

## 10. Human Test-Quality Decisions

- **Candidate 1 N03/N04:** do not duplicate existing auth/request-validation tests; extend with no-dispatch assertion. Evidence: test_runtime.py existing cases and verified pipeline auth test.
- **Candidate 2 N16:** merge privacy canaries/log checks into N08; keep standalone unit test only for independent helper behavior. Evidence: same notifier exception path exercises event/log leak risk.
- N15 is optional and should be retained only if it tests a distinct size-plus-notification interaction.

These are design decisions. The later developer must modify/remove at least two generated test cases in actual test code and preserve the diff. That code-level correction has not happened here.

## 11. Future Test Commands

From apps/llm-service:

`uv run --locked --extra test pytest -q tests/integration/test_completion_notification.py -vv`

`uv run --locked --extra test pytest -q tests/integration/test_runtime.py`

`uv run --locked --extra test pytest -q tests/integration/test_extraction_pipeline_boundary.py::test_invalid_injected_extraction_response_maps_to_error_envelope`

`uv run --locked --extra test pytest -q tests/integration/test_verified_extraction_service.py`

`uv run --locked --extra test pytest -q`

Proposed N17 invocation after script creation: `uv run --locked --extra test python tests/performance/notification_load.py --requests 200 --concurrency 200 --warmups 1 --runs 3`. Define analogous separate large-input experiment invocation only after its script interface is finalized.

## 12. Evidence Requirements for Later Phase

- Baseline branch, SHA, status before edits.
- For each Red: exact command/output, failing behavioral assertion, and reason; no import-only Red.
- Focused Green output and complete service-suite output.
- Test-to-AC/risk traceability and reviewed coverage gaps.
- Pairwise generator order, constraints, selected rows, feasible pair count, uncovered count.
- Human correction diffs for at least two weak/duplicate AI-generated tests.
- Mutation diff/failure/restoration/post-restore boundary results.
- Large-input N18 request bytes, max bytes, status/error, fake cancellation, no-dispatch.
- Large-input latency/memory methods and raw measurements.
- N17 environment, payload, 200-task synchronization, response-frame timing, p50/p95/p99, throughput, error rate and notifier timings.
- Commit SHA references only after commits occur; none exist for Phase 03 design.

## 13. Residual Limitations

Tests prove service behavior only. They do not prove App database transaction durability, notification delivery after process restart, exactly-once dispatch, live OpenRouter performance, or user receipt. No code/tests/benchmarks have been executed in this Phase 03 design.
