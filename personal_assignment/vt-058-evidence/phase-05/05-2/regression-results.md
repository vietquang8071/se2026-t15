# Phase 05.2 — Regression Results

All times are UTC and are run-start timestamps where captured. Tests used the existing locked, no-sync environment, `PYTHONDONTWRITEBYTECODE=1`, and pytest cache disabled. No dependencies were installed or synchronized.

## N02 baseline before Phase 05.2 edits

Run started `2026-11-14 14:49:03 UTC`.

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync --locked --extra test \
  pytest -q -p no:cacheprovider \
  tests/integration/test_runtime.py::test_dependency_override_returns_typed_extraction_response
```

Exit 0 — `1 passed in 0.87s`. N02 remained GREEN before Phase 05.2 changes.

## N06 characterization

Run started `2026-11-14 14:49:34 UTC`.

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync --locked --extra test \
  pytest -q -p no:cacheprovider \
  tests/integration/test_extraction_pipeline_boundary.py::test_invalid_injected_extraction_response_maps_to_error_envelope
```

Exit 0 — `1 passed in 0.83s`; HTTP 502 / `INVALID_STRUCTURED_OUTPUT`; zero dispatch attempts. N06 is characterization, not feature RED.

## Staged RED/GREEN executions

| Scenario | Run | Result |
|---|---|---|
| N08 | RED, `2026-11-14 14:53:43 UTC` | Exit 1; `1 failed in 0.90s`; lacked notification-specific safe diagnostic while response bytes were already unchanged. |
| N08 | GREEN, `2026-11-14 14:54:10 UTC` | Exit 0; `1 passed in 0.79s`. |
| N09 | RED, `2026-11-14 14:55:49 UTC` | Exit 1; `7 failed in 2.26s`; setting absent/ignored and notifier did not finish before outer watchdog. |
| N09 | GREEN, `2026-11-14 14:56:27 UTC` | Exit 0; `7 passed in 0.87s`. |
| N08 after timeout integration | Regression | Exit 0; `1 passed in 0.82s`; start timestamp not recorded. |
| N10 | RED, `2026-11-14 14:57:38 UTC` | Exit 1; `1 failed in 0.91s`; scheduling exception changed HTTP 200 to 500. |
| N10 | GREEN, `2026-11-14 14:57:57 UTC` | Exit 0; `1 passed in 0.81s`. |

Commands and relevant output excerpts are preserved in [failure-isolation-red-green.md](failure-isolation-red-green.md).

## Focused regression group

Run started `2026-11-14 14:58:22 UTC`.

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync --locked --extra test \
  pytest -q -p no:cacheprovider \
  tests/integration/test_runtime.py \
  tests/integration/test_extraction_pipeline_boundary.py \
  tests/integration/test_completion_notification.py \
  tests/contract/test_response_models.py \
  tests/integration/test_verified_extraction_service.py
```

Exit 0.

```text
........................................................................ [ 67%]
...................................                                      [100%]
107 passed in 3.08s
```

This includes N02, N06, N08–N10, existing authentication/request validation and extraction timeout checks, response identity contract tests, and verified-service tests.

## Complete LLM Service suite

Run started `2026-11-14 14:58:32 UTC`.

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync --locked --extra test \
  pytest -q -p no:cacheprovider
```

Exit 0.

```text
........................................................................ [ 12%]
........................................................................ [ 25%]
........................................................................ [ 38%]
........................................................................ [ 51%]
........................................................................ [ 64%]
........................................................................ [ 77%]
........................................................................ [ 90%]
.......................................................                  [100%]
559 passed in 4.86s
```

No tests were skipped or reported failing in this run. Mutation testing, performance benchmarking, and large-payload experiments were not run in Phase 05.2.
