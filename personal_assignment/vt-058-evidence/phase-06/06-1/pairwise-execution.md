# Phase 06.1 — Executable Pairwise Results

## Factors and feasibility constraints

The executable module is `apps/llm-service/tests/integration/test_pairwise_completion_notification.py`. It retains the approved factor values:

| Factor | Values |
|---|---|
| Payload size | `small`, `exact`, `over` |
| Extraction outcome | `success`, `provider_error`, `structural_invalid`, `request_timeout`, `size_reject` |
| Notification outcome | `returns`, `raises`, `times_out`, `not_attempted` |
| Concurrency | `1`, `2`, `8` |

Constraints implemented in `_is_feasible`:

1. `over` is equivalent to `size_reject`; neither occurs with any other size/outcome pairing.
2. `size_reject` requires notification `not_attempted`.
3. `provider_error`, `structural_invalid`, and `request_timeout` require `not_attempted`.
4. Successful extraction permits only `returns`, `raises`, or `times_out`.
5. The `not_attempted` notification outcome is not paired with successful extraction.
6. Concurrency 200 is excluded; it belongs to the separate performance milestone.

`test_pairwise_dataset_covers_every_feasible_factor_pair` independently constructs the Cartesian product, filters it with the constraints, enumerates all factor-value pairs, checks every selected row against both the allowed factor domains and constraints, rejects duplicate rows, and computes the uncovered set.

## Independently verified coverage

| Measure | Approved design | Recomputed by test | Result |
|---|---:|---:|---|
| Feasible full combinations | 39 | 39 | Match |
| Feasible factor-value pairs | 61 | 61 | Match |
| Selected rows | 21 | 21 | Match |
| Duplicate selected rows | 0 | 0 | None |
| Uncovered feasible pairs | 0 | 0 | None |

This is design/coverage verification. It is distinct from executing each row and observing its result.

## Complete selected dataset and execution observations

Each row below has a stable pytest ID and was executed through the real FastAPI app, actual request validation and byte middleware, route timeout, response/error mapping, and production notification safe-dispatch wrapper. Deterministic test-local extraction/notifier fakes were used; no OpenRouter or external provider was called. Each row sends the indicated number of actual concurrent HTTP requests. `ConcurrentRequestGate` holds all invocations at the ASGI edge until the row's full concurrency cardinality is present and asserts `max_active == concurrency`.

| Row | Size | Extraction | Notification | C | Asserted HTTP outcome | Asserted service/notification observation | Result |
|---|---|---|---|---:|---|---|---|
| PW01 | small | success | returns | 1 | 200, valid response | 1 extraction; 1 dispatch; 1 normal completion | PASS |
| PW02 | small | provider_error | not_attempted | 2 | 502 `PROVIDER_FAILURE` | 2 extraction calls; 0 attempts | PASS |
| PW03 | exact | success | raises | 2 | 200, valid responses | 2 extraction; 2 attempts; 0 normal completions; safe failure diagnostic per attempt | PASS |
| PW04 | exact | structural_invalid | not_attempted | 1 | 502 `INVALID_STRUCTURED_OUTPUT` | 1 extraction; 0 attempts | PASS |
| PW05 | over | size_reject | not_attempted | 8 | 413 `PAYLOAD_TOO_LARGE` | 0 extraction; 0 attempts | PASS |
| PW06 | small | success | times_out | 8 | 200, valid responses | 8 extraction; 8 attempts; 8 notifier cancellations; safe timeout diagnostic per attempt | PASS |
| PW07 | exact | request_timeout | not_attempted | 8 | 504 `REQUEST_TIMEOUT` | 8 extraction calls cancelled by request timeout; 0 attempts | PASS |
| PW08 | small | success | raises | 1 | 200, valid response | 1 extraction; 1 attempt; 0 normal completions | PASS |
| PW09 | small | structural_invalid | not_attempted | 2 | 502 `INVALID_STRUCTURED_OUTPUT` | 2 extraction; 0 attempts | PASS |
| PW10 | small | request_timeout | not_attempted | 1 | 504 `REQUEST_TIMEOUT` | 1 extraction call cancelled; 0 attempts | PASS |
| PW11 | exact | success | returns | 2 | 200, valid responses | 2 extraction; 2 dispatches; 2 normal completions | PASS |
| PW12 | exact | success | times_out | 1 | 200, valid response | 1 extraction; 1 attempt; 1 notifier cancellation | PASS |
| PW13 | exact | provider_error | not_attempted | 1 | 502 `PROVIDER_FAILURE` | 1 extraction; 0 attempts | PASS |
| PW14 | over | size_reject | not_attempted | 1 | 413 `PAYLOAD_TOO_LARGE` | 0 extraction; 0 attempts | PASS |
| PW15 | over | size_reject | not_attempted | 2 | 413 `PAYLOAD_TOO_LARGE` | 0 extraction; 0 attempts | PASS |
| PW16 | small | success | returns | 8 | 200, valid responses | 8 extraction; 8 dispatches; 8 normal completions | PASS |
| PW17 | small | success | raises | 8 | 200, valid responses | 8 extraction; 8 attempts; 0 normal completions | PASS |
| PW18 | small | success | times_out | 2 | 200, valid responses | 2 extraction; 2 attempts; 2 notifier cancellations | PASS |
| PW19 | small | provider_error | not_attempted | 8 | 502 `PROVIDER_FAILURE` | 8 extraction; 0 attempts | PASS |
| PW20 | small | structural_invalid | not_attempted | 8 | 502 `INVALID_STRUCTURED_OUTPUT` | 8 extraction; 0 attempts | PASS |
| PW21 | small | request_timeout | not_attempted | 2 | 504 `REQUEST_TIMEOUT` | 2 extraction calls cancelled; 0 attempts | PASS |

For successful rows, assertions validate `ExtractionResponse`, per-request request/meeting identity, exact event keys (`event_type`, `request_id`, `meeting_id`, `status`), and absence of cross-request event contamination. Failed extraction rows assert the expected typed HTTP error and no notifier attempts. Size-rejected rows assert the middleware error and zero extraction/notifier calls. Notification exceptions and timeouts assert that successful HTTP responses remain valid, with fixed safe diagnostics and no token, transcript, or exception-detail canaries in captured logs.

Payload serialization uses compact UTF-8 JSON. The full-valid fixture modified with fixed-width pairwise IDs and the synthetic transcript canary is **1,562 bytes** for `small`/`exact`; `small` configures a 32-byte margin. `exact` configures max=1,562. `over` appends one legal JSON whitespace byte (1,563 bytes) and sets max=1,562. The exact byte-limit dedicated N12/N13 tests use their separate full fixture value N=1,587; do not conflate those values or this pairwise dataset with mutation experiments.

## Pairwise command and actual output

Run started: `2026-11-14 15:37:22 UTC`.

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync --locked --extra test \
  pytest -q -p no:cacheprovider \
  tests/integration/test_pairwise_completion_notification.py -vv
```

Exit code: **0**.

```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-8.4.2, pluggy-1.7.0 -- apps/llm-service/.venv/bin/python
rootdir: apps/llm-service
configfile: pyproject.toml
plugins: anyio-4.15.1
collecting ... collected 22 items
tests/integration/test_pairwise_completion_notification.py::test_pairwise_dataset_covers_every_feasible_factor_pair PASSED [  4%]
tests/integration/test_pairwise_completion_notification.py::test_pairwise_completion_notification_scenario[PW01] PASSED [  9%]
tests/integration/test_pairwise_completion_notification.py::test_pairwise_completion_notification_scenario[PW02] PASSED [ 13%]
tests/integration/test_pairwise_completion_notification.py::test_pairwise_completion_notification_scenario[PW03] PASSED [ 18%]
tests/integration/test_pairwise_completion_notification.py::test_pairwise_completion_notification_scenario[PW04] PASSED [ 22%]
tests/integration/test_pairwise_completion_notification.py::test_pairwise_completion_notification_scenario[PW05] PASSED [ 27%]
tests/integration/test_pairwise_completion_notification.py::test_pairwise_completion_notification_scenario[PW06] PASSED [ 31%]
tests/integration/test_pairwise_completion_notification.py::test_pairwise_completion_notification_scenario[PW07] PASSED [ 36%]
tests/integration/test_pairwise_completion_notification.py::test_pairwise_completion_notification_scenario[PW08] PASSED [ 40%]
tests/integration/test_pairwise_completion_notification.py::test_pairwise_completion_notification_scenario[PW09] PASSED [ 45%]
tests/integration/test_pairwise_completion_notification.py::test_pairwise_completion_notification_scenario[PW10] PASSED [ 50%]
tests/integration/test_pairwise_completion_notification.py::test_pairwise_completion_notification_scenario[PW11] PASSED [ 54%]
tests/integration/test_pairwise_completion_notification.py::test_pairwise_completion_notification_scenario[PW12] PASSED [ 59%]
tests/integration/test_pairwise_completion_notification.py::test_pairwise_completion_notification_scenario[PW13] PASSED [ 63%]
tests/integration/test_pairwise_completion_notification.py::test_pairwise_completion_notification_scenario[PW14] PASSED [ 68%]
tests/integration/test_pairwise_completion_notification.py::test_pairwise_completion_notification_scenario[PW15] PASSED [ 72%]
tests/integration/test_pairwise_completion_notification.py::test_pairwise_completion_notification_scenario[PW16] PASSED [ 77%]
tests/integration/test_pairwise_completion_notification.py::test_pairwise_completion_notification_scenario[PW17] PASSED [ 81%]
tests/integration/test_pairwise_completion_notification.py::test_pairwise_completion_notification_scenario[PW18] PASSED [ 86%]
tests/integration/test_pairwise_completion_notification.py::test_pairwise_completion_notification_scenario[PW19] PASSED [ 90%]
tests/integration/test_pairwise_completion_notification.py::test_pairwise_completion_notification_scenario[PW20] PASSED [ 95%]
tests/integration/test_pairwise_completion_notification.py::test_pairwise_completion_notification_scenario[PW21] PASSED [100%]
============================== 22 passed in 1.53s ==============================
```

This result means 21 scenario rows and one coverage-verification test executed and passed. It does not mean a load benchmark ran. The fake extraction path is intentionally not the live OpenRouter provider; actual scripted-provider and evidence-verification failures are exercised separately by N05.

## Regression results

Final focused regression run started `2026-11-14 15:39:18 UTC` and exited 0: **133 passed in 3.77s**. It covered `test_runtime.py`, `test_verified_extraction_service.py`, the pairwise module, `test_completion_notification.py`, `test_extraction_pipeline_boundary.py`, and `test_response_models.py`.

Final full LLM Service run started `2026-11-14 15:37:26 UTC` and exited 0: **585 passed in 5.50s**. Final isolated boundary run started `2026-11-14 15:39:06 UTC` and exited 0: **4 passed, 23 deselected in 0.85s**.

No mutation experiment, 200-task benchmark, or large-input resource benchmark was executed.
