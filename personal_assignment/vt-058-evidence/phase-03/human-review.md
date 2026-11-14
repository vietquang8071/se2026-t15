# Human Review — Phase 03 Risk-Based Test Design

## Review Context

- Assignment: BT3 — AI-05 — VT-058.
- Specification: personal_assignment/vt-058.md.
- Reviewed artifact: initial-test-design.md, AI-generated Phase 03 design.
- Branch: feature/vt-058-llm-notification.
- Baseline SHA: 5e54822fca535972ef9b10a7d39dfbabc7df4b3d.
- Scope: principal large-input risk, correct Red/Green evidence, and human correction of weak/duplicate AI tests.

This review changes the test design only. It does not claim test code was modified or tests executed.

## FIX-01 — Add a Direct Large-Input Failure-Path Test

**Original AI proposal:** N12–N14 test exact/over size boundaries; N07 covers request timeout; N17 measures 200 concurrent tasks. No scenario directly combines a large but valid body with controlled extraction timeout.

**Repository/spec evidence:**

- personal_assignment/vt-058.md identifies large inputs, timeout risk and concurrent workloads in the problem statement; AC-05 separately defines byte-limit behavior.
- apps/llm-service/app/core/middleware.py, ExtractionRequestBoundaryMiddleware.__call__, first checks declared size then streamed bytes; an in-limit body proceeds to parsing.
- apps/llm-service/app/api/routes.py, create_extraction, wraps service.extract in asyncio.timeout and maps TimeoutError to ExtractionRequestTimeoutError.
- apps/llm-service/tests/integration/test_runtime.py::test_request_timeout_maps_to_retryable_contract_error tests request timeout with a short configured budget, but does not use a large body.
- Existing oversized tests assert size rejection before extraction; they do not prove timeout behavior for accepted large input.

**Risk:** Boundary tests can pass while a large, valid in-limit extraction still times out or is mishandled. A size 413 is not evidence of a timeout path.

**Human decision: FIX-01 accepted.** Add N18 using valid payload close to but below the configured maximum, deterministic waiting extraction service, short request budget, and bounded test watchdog.

**Revised approach:** Assert 504 REQUEST_TIMEOUT, no completion dispatch, fake cancellation, and that the request was under the byte limit. Add a separate large-input latency/memory experiment with deterministic fake extraction. Do not create 200 maximum-size payloads simultaneously or use boundary mutation tests as performance evidence.

**Impact:** Directly covers the principal large-input failure risk while preserving separate byte-limit and load scopes.

## FIX-02 — Correct Red/Green Classification

**Original AI proposal:** The initial design described N05 failure-path and N11 concurrency cases among feature tests, and treated N12–N14 as part of the notification test-first sequence without consistently distinguishing baseline behavior.

**Repository evidence:**

- Existing provider/evidence failures and request timeout paths already return errors before any notification feature exists.
- Existing invalid injected response test already expects 502.
- Existing size middleware already uses > and tests over-limit behavior.
- Existing full-pipeline concurrency test already verifies two-request isolation without notification.

**Risk:** Labeling these tests as feature Red would overstate evidence. N05 may pass on the baseline because no notification is emitted on errors. N11 is an integration/regression case after notifier injection. Exact/oversize checks characterize existing middleware. Import/missing-module failures do not show the intended behavior is missing.

**Human decision: FIX-02 accepted.** Classify tests as Genuine Feature RED, Staged RED, Characterization, Regression, Mutation-Killing, or Performance.

**Revised approach:** N02 is the primary genuine Red: successful extraction with zero notifier attempts. N08–N10 are staged Red after initial dispatch exists, targeting exception diagnostics/isolation, bounded timeout, and scheduling failure. Existing failure, invalid response, identity, auth, and size behavior are characterization/regression unless a specific new behavior assertion is shown to fail. Record baseline state, assertion, reason, expected Green and evidence for every Red claim.

**Impact:** Makes test evidence auditable and prevents ordinary baseline-green tests from being reported as feature Red.

## FIX-03 — Prepare Human Correction of AI-Generated Tests

### Candidate 1 — N03/N04 duplication

**Original AI proposal:** Add separate notification tests for auth and request-validation failures.

**Repository evidence:** tests/integration/test_runtime.py already covers missing/invalid bearer and request validation. tests/integration/test_verified_extraction_service.py also covers auth variants without provider invocation.

**Risk:** Repeating fixtures, HTTP statuses and error-envelope assertions adds duplicate setup without new evidence.

**Human decision: revise.** Extend existing tests and add only zero notifier attempts (and service/provider not called where already observable). Do not add duplicate status-only tests.

### Candidate 2 — N16 overlaps N08

**Original AI proposal:** Keep a separate diagnostic privacy test plus N08’s exception/canary response-isolation test.

**Repository evidence:** N08 already uses a canary-bearing notifier exception and inspects response and diagnostic safety.

**Risk:** Separate tests can assert the same privacy property twice without exercising an independent path.

**Human decision: revise.** Merge the meaningful event/log canary assertions into N08. Retain a separate unit test only if it verifies an independent dispatch-helper contract not covered by the API scenario.

### Additional candidate — N15 interaction test

N15 exact-limit plus notifier failure is useful only as distinct interaction coverage; it should be removed if it duplicates N08 and N12 without a separate risk hypothesis.

**Impact:** These are test-design corrections only. No test implementation or deletion has occurred. In a later code phase preserve the generated test and the actual correction/deletion diff to demonstrate human review.

## Review Summary

FIX-01 adds direct large-valid-input timeout coverage and a separate resource experiment. FIX-02 makes baseline-green characterization/regression tests distinct from feature Red. FIX-03 identifies two concrete weak/duplicate AI proposals for future human changes.

The reviewer applied independent engineering judgment to the AI design and source evidence. The review does not fabricate that the required code-level human corrections have already happened.
