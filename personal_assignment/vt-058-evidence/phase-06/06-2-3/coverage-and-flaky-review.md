# Phase 06.3 — Coverage and Flaky-Test Review

## Evidence baseline

This review is based on the actual tests at HEAD `beae5161608cba48db81a10e892e5c743de55e10` plus the developer-confirmed HC-01 and HC-02 worktree edits. The repository middleware SHA-256 is `299f7cfd050a2114a5eae471d2f8f5bb5c50ba1311ef690613f1d4a82ef84a01`.

## Acceptance-criteria traceability

| Requirement | Test evidence | Scope and observed status |
|---|---|---|
| AC-01 — successful completion event | N02: `tests/integration/test_runtime.py::test_dependency_override_returns_typed_extraction_response`; successful pairwise rows PW01, PW03, PW06, PW08, PW11, PW12, PW16–PW18 | N02 remains the success-dispatch regression. Successful pairwise rows verify one allowlisted event per request, associated request/meeting identity, and HTTP 200 preservation. All 21 pairwise rows passed in the current run. |
| AC-02 — no false completion event | N03: `test_extraction_rejects_missing_or_invalid_bearer_token`; N04: `test_extraction_validates_request_before_calling_service`; N05: `tests/integration/test_verified_extraction_service.py::test_provider_errors_map_without_exposing_provider_details`, `test_unknown_source_id_returns_unverified_evidence_error`, and related verification failures; N06: `tests/integration/test_extraction_pipeline_boundary.py::test_invalid_injected_extraction_response_maps_to_error_envelope`; N07 identity: `tests/contract/test_response_models.py::test_cross_request_validation_rejects_identity_or_module_mismatch`; request timeout: `tests/integration/test_runtime.py::test_request_timeout_maps_to_retryable_contract_error` | Existing error contracts are retained and unsuccessful paths assert no dispatch where applicable. Pairwise provider, structural-invalid, request-timeout, and size-reject rows additionally assert zero attempts. N06 and N07 are characterization/regression checks, not feature RED claims. |
| AC-03 — notification failure isolation | N08/N09/N10: `tests/integration/test_completion_notification.py::test_notifier_exception_preserves_response_and_safe_diagnostics`, `test_notifier_timeout_is_bounded_and_cancels_dispatch`, and `test_task_scheduling_failure_preserves_response_and_safe_diagnostics`; N11: `tests/integration/test_verified_extraction_service.py::test_full_pipeline_remains_request_isolated_under_concurrency` | N08 compares response bytes with control and checks safe diagnostics; N09 checks bounded cancellation; N10 checks scheduling failure; N11 checks one notifier error does not alter another successful request. Pairwise raises/timeouts further exercise concurrent successes. |
| AC-04 — allowlisted event and privacy | N02, N08, N11, successful pairwise rows | Event assertions use exactly `event_type`, `request_id`, `meeting_id`, and `status`; synthetic transcript/token/provider/exception canaries are checked against logs or event observations. |
| AC-05 — exact and over-limit behavior | N12/N13/N14 in `tests/integration/test_runtime.py`; M01/M02 in this evidence set | N12 validates declared exact N; N13 validates streamed exact N with no declared length; N14 has declared and streamed N+1 cases. Fixture serialization is N = **1,587 bytes** and N+1 = **1,588 bytes**. N12 and N13 passed and independently killed their respective `>` to `>=` mutants. N14 was included in the focused and full suites. |
| I-01 — notification failure cannot alter successful extraction | N08–N11 and successful pairwise notification-failure rows | Evidence compares actual HTTP response behavior separately from notification work; it makes no claim about App database durability. |
| I-02 — no false completion after failure | N03–N07, failed pairwise rows PW02, PW04, PW05, PW07, PW09, PW10, PW13–PW15, PW19–PW21 | Failed extraction or size rejection resulted in zero notification attempts in the test assertions. |

N17 (200-task performance) and N18 (large-valid-input timeout/resource experiment) were not executed or claimed. This milestone did not run a performance benchmark.

## Separate coverage measures

### Pairwise coverage

The executable verifier constructs the Cartesian product and applies the feasibility constraints. The current test output confirms **39 feasible full combinations, 61 feasible factor-value pairs, 21 selected unique rows, and zero uncovered feasible pairs**. HC-02 additionally asserts the exact ordered IDs PW01–PW21. The verifier and every row passed: **22 passed** (one verifier plus 21 scenarios). Three repeat runs each also reported 22 passed.

Pairwise coverage is combinatorial design coverage. It is not code coverage and does not imply that every runtime state was tested.

### Mutation score

The two approved, non-equivalent boundary mutants were both killed after HC-01 and restored in the isolated copy: M01 by N12 and M02 by N13. Scoped mutation score: **2/2 = 100%** for these two mutants only. This is separate from pairwise and code-coverage measures.

### Numerical code coverage

Numerical statement or branch coverage is unavailable in the existing environment. `/home/vitquay1708/Study_Space/SE/apps/llm-service/.venv/bin/python -m coverage --version` exited 1 with `No module named coverage`. Pytest's observed environment did not provide a coverage plugin. No package was installed. The acceptance-criteria matrix above is evidence-backed traceability, not a percentage.

## Flaky-test risks

### Risk A — timeout and async scheduling sensitivity

- **Affected tests:** N09 `test_notifier_timeout_is_bounded_and_cancels_dispatch`; pairwise timeout rows PW06, PW12, PW18 and request-timeout rows PW07, PW10, PW21.
- **Cause:** N09 uses a 0.03-second notifier timeout and a 1.0-second outer watchdog. Pairwise uses a 0.02-second notification timeout, a 0.05-second extraction timeout, event barriers with 1- or 2-second safety bounds, and a 4-second outer request watchdog. Event-loop scheduling or contended CI can delay timeout/cancellation observation.
- **Expected symptom:** A test may hit its outer watchdog, fail to observe cancellation before assertion, or map an overloaded fake into a timeout outcome.
- **Severity / likelihood:** Medium severity; low-to-medium likelihood under normal local runs, higher under overloaded CI.
- **Mitigation:** Keep event-based start/cancel synchronization rather than fixed sleeps; retain an outer watchdog substantially larger than the configured notification timeout; keep request and notification timeouts separately configured; assert cancellation state rather than a narrow elapsed-time interval. If CI flakes, increase the safety margin without weakening the required timeout behavior.
- **Validation:** N09 passed three consecutive executions. The pairwise module passed three consecutive executions. These observations reduce but do not eliminate timing risk.

### Risk B — concurrency barrier and shared fake state

- **Affected tests:** N11 `test_full_pipeline_remains_request_isolated_under_concurrency`; pairwise concurrency values 2 and 8, including PW05/PW14/PW15.
- **Cause:** N11 waits for two candidate provider calls on an `asyncio.Event` with a 1-second bound. Pairwise uses a request gate, per-row fake service/notifier state, a 1-second extraction-entry barrier, and a 4-second `asyncio.wait_for` around gathered HTTP requests. Cancellation or slow scheduling can leave a barrier unsatisfied. Shared lists are scoped to test-local fake instances.
- **Expected symptom:** Barrier timeout, watchdog expiry, incomplete request/event counts, or a cross-request identity assertion failure.
- **Severity / likelihood:** Medium severity; low likelihood in the observed runs, with increased risk under loaded CI.
- **Mitigation:** Preserve per-test app/fake instances and unique request IDs; retain `asyncio.gather` plus explicit arrival/event barriers to establish overlap; ensure gate cleanup is in `finally`; avoid sleeps and module-global mutable fake state; keep watchdogs bounded. For over-limit rows, describe concurrency as concurrent HTTP rejection before extraction, not concurrent extraction work.
- **Validation:** N11 passed three consecutive executions. The pairwise module, whose gate asserts arrival cardinality and `max_active`, passed three consecutive executions. Repeats are evidence of observed stability, not proof of no flakiness.

### Additional maintainability observation

The HC-02 identifier assertion is behaviorally correct and passes. Its continuation line is less indented than conventional formatter output; HC-01 also introduces a module-level class with less blank-line spacing than standard Python style. No formatter or lint tool was run, and no source or test edits were made during this validation. A later human style pass may normalize formatting without altering assertions.
