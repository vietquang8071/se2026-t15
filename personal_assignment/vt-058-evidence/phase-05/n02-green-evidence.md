# Phase 05.1 — N02 GREEN Evidence

## Baseline and prior RED

- Branch: `feature/vt-058-llm-notification`.
- HEAD: `5e54822fca535972ef9b10a7d39dfbabc7df4b3d` (unchanged; no commit was made).
- Phase 04 RED record: [../phase-04/n02-red-evidence.md](../phase-04/n02-red-evidence.md).
- The N02 test was not edited in Phase 05.1. Its pre-existing diff remains the test change recorded in Phase 04.

Before production changes, N02 was rerun at `2026-11-14 14:28:35 UTC` with the same command used for GREEN. Actual result: exit code `1`; the successful HTTP/schema and extraction-call checks passed, then the notifier assertion observed zero attempts. Pytest summary: `1 failed in 1.10s`. This reconfirmed the Phase 04 behavioral RED.

## Production change

The authorized production patch adds `app/services/notification.py` with a four-key `CompletionEvent` TypedDict, async `CompletionNotifier` protocol, and `NoOpCompletionNotifier`. `create_app` initializes one app-scoped notifier (optionally injected); `get_completion_notifier` returns that same app-state object. The route awaits extraction inside the existing timeout block, then constructs the allowlisted event and registers exactly one `notifier.dispatch` call with FastAPI `BackgroundTasks`, returning the original response.

The N02 test continues to install its local fake at `app.state.completion_notifier`. No test source or assertion was changed to obtain GREEN.

## N02 GREEN run

Run started at `2026-11-14 14:30:03 UTC`, from `apps/llm-service`.

Exact command:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync --locked --extra test \
  pytest -q -p no:cacheprovider \
  tests/integration/test_runtime.py::test_dependency_override_returns_typed_extraction_response
```

Actual exit code: `0`.

```text
.                                                                        [100%]
1 passed in 1.23s
```

The unchanged test asserts that the same successful extraction response is returned, the fake extraction service is called once, and the notifier's recorded attempts equal a one-element list containing exactly `event_type`, matching `request_id`, matching `meeting_id`, and `status`. The Phase 04 observation was an empty attempts list; the GREEN result means that exact one-event assertion now passes. This proves a dispatch attempt to the recording fake, not delivery to a recipient.

## Focused regressions

Run started at `2026-11-14 14:30:16 UTC`, from `apps/llm-service`.

Exact command:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync --locked --extra test \
  pytest -q -p no:cacheprovider \
  tests/integration/test_runtime.py \
  tests/integration/test_extraction_pipeline_boundary.py::test_invalid_injected_extraction_response_maps_to_error_envelope \
  tests/contract/test_response_models.py
```

Actual exit code: `0`.

```text
....................................................                     [100%]
52 passed in 1.41s
```

No failure was reported in this focused set. The invalid injected-response test confirms the existing `502 INVALID_STRUCTURED_OUTPUT` response mapping. It does not inject a recording notifier and therefore does not independently assert zero dispatch on structural response failure; that remains N06 characterization work.

## Scope and limitations

The production change is limited to the four authorized paths. N02 was not modified after Phase 04. No full suite, benchmark, mutation experiment, or N08/N09/N10 test was run.

GREEN here establishes successful registration and execution of the recording fake for N02. It does not establish:

- Exception isolation, bounded notifier timeout, or cancellation behavior.
- Isolation of scheduling errors.
- A real user-facing notification; the runtime adapter is a no-op.
- Durable or exactly-once delivery.
- App database transaction durability.

Those items remain for later approved work, particularly Phase 05.2.
