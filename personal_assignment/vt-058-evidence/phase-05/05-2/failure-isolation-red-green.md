# N08–N10 — Staged RED → GREEN Evidence

All commands ran from `apps/llm-service` with the already-installed environment, `uv run --no-sync --locked`, bytecode writes disabled, and pytest cache disabled. No dependency synchronization occurred. Tests were written before their corresponding production fixes. Their behavioral assertions were not weakened.

## N08 — Notifier exception isolation and diagnostic privacy

### Test behavior

`tests/integration/test_completion_notification.py::test_notifier_exception_preserves_response_and_safe_diagnostics` uses a fixed successful extraction service and two per-app notifiers: a returning control fake and a failing fake that records an attempt then raises with unique synthetic transcript, bearer-token, provider-response, and exception-detail canaries.

The test captures ASGI response frames directly. It compares raw status and body bytes, verifies exactly one attempt and no normal completion, checks the exact four-key event, requires the fixed notification diagnostic, and rejects every canary in captured logs. This avoids treating a test-client exception or middleware behavior as proof of an HTTP response change.

### RED — before the safe dispatch wrapper

Run started `2026-11-14 14:53:43 UTC`.

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync --locked --extra test \
  pytest -q -p no:cacheprovider \
  tests/integration/test_completion_notification.py::test_notifier_exception_preserves_response_and_safe_diagnostics
```

Actual exit code: `1`; `1 failed in 0.90s`.

Relevant actual output:

```text
>       assert any(
            record.getMessage() == "Completion notification dispatch failed."
            for record in caplog.records
        )
E       assert False

------------------------------ Captured log call -------------------------------
ERROR    app.core.middleware:middleware.py:36 Unhandled internal error in LLM Service request.
```

The test had already verified equal HTTP 200 status and identical body bytes for control and failing notifier. The baseline `SafeUnhandledErrorMiddleware` stopped the post-response exception from changing the sent response, but it emitted only a generic internal-error diagnostic. RED therefore identifies the missing notification-specific safe isolation/diagnostic path; it does not claim the baseline changed the HTTP response.

### GREEN — after adding safe adapter dispatch

Run started `2026-11-14 14:54:10 UTC`.

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync --locked --extra test \
  pytest -q -p no:cacheprovider \
  tests/integration/test_completion_notification.py::test_notifier_exception_preserves_response_and_safe_diagnostics
```

Actual exit code: `0`.

```text
.                                                                        [100%]
1 passed in 0.79s
```

The production helper catches ordinary adapter exceptions, returns normally, and logs the fixed message `Completion notification dispatch failed.` without exception text or event data. The same control and failure response assertions pass; the failing fake recorded one attempt and no normal completion. All privacy canaries were absent from logs.

### Production change

`app/services/notification.py` adds `dispatch_completion_safely(notifier, event, timeout_seconds)`. At this staged point it isolates ordinary adapter exceptions; N09 adds timeout handling. `app/api/routes.py` registers the helper as the background task. The test body and assertions were unchanged between its RED and GREEN runs.

## N09 — Bounded timeout and cancellation

### Test behavior

Three configuration/behavior tests were added in `test_completion_notification.py`:

- The setting defaults to 1.0 second.
- Zero, negative, NaN, positive infinity, and negative infinity are rejected.
- A waiting notifier records its attempt, waits on an unset event, and records cancellation. The test compares raw ASGI response frames to a returning control notifier and uses a separate 1.0-second safety watchdog. The test timeout is 0.03 seconds; the extraction timeout remains 5.0 seconds.

### RED — before notification timeout configuration and enforcement

Run started `2026-11-14 14:55:49 UTC`.

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync --locked --extra test \
  pytest -q -p no:cacheprovider \
  tests/integration/test_completion_notification.py::test_notification_timeout_setting_defaults_to_one_second \
  tests/integration/test_completion_notification.py::test_notification_timeout_setting_rejects_invalid_values \
  tests/integration/test_completion_notification.py::test_notifier_timeout_is_bounded_and_cancels_dispatch
```

Actual exit code: `1`; `7 failed in 2.26s`.

The default-setting assertion observed no setting. All five invalid-value cases showed `DID NOT RAISE ValidationError` because the existing settings model ignored the unknown key. In the hanging-notifier case, the response frames remained HTTP 200 and matched the control, and the outer watchdog cancelled the fake; the ASGI request did not finish before that outer watchdog. The failing assertion was:

```text
assert timeout_completed is True, "notification work exceeded the outer safety watchdog"
E assert False is True
```

This is staged RED for both missing bounded dispatch and missing validated timeout configuration. It does not use an import or fixture failure.

### GREEN — after config and `asyncio.timeout()` implementation

Run started `2026-11-14 14:56:27 UTC`.

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync --locked --extra test \
  pytest -q -p no:cacheprovider \
  tests/integration/test_completion_notification.py::test_notification_timeout_setting_defaults_to_one_second \
  tests/integration/test_completion_notification.py::test_notification_timeout_setting_rejects_invalid_values \
  tests/integration/test_completion_notification.py::test_notifier_timeout_is_bounded_and_cancels_dispatch
```

Actual exit code: `0`.

```text
.......                                                                  [100%]
7 passed in 0.87s
```

`Settings` now validates the positive finite default and invalid values. `dispatch_completion_safely` applies `asyncio.timeout` only to the secondary notifier call. The fake observed cancellation, did not complete normally, and the ASGI call finished before the outer watchdog with status/body identical to control. The extraction timeout value remained 5.0 seconds. Cancellation cleanup is awaited by the asyncio timeout context. `CancelledError` is not caught by the helper's `except TimeoutError` / `except Exception` clauses.

The unchanged N08 test was rerun after the timeout integration: `1 passed in 0.82s`, exit 0. Its separate start timestamp was not recorded.

### Production change

`app/core/config.py` adds `llm_service_notification_timeout_seconds` with default `1.0`, `gt=0`, and `allow_inf_nan=False`. `dispatch_completion_safely` wraps only `notifier.dispatch(event)` in `asyncio.timeout`; it logs `Completion notification timed out.` for timeout and preserves the separate fixed exception diagnostic. The extraction timeout scope is unchanged.

## N10 — Background-task scheduling failure isolation

### Test behavior

`tests/integration/test_completion_notification.py::test_task_scheduling_failure_preserves_response_and_safe_diagnostics` first captures a control response, then monkeypatches `BackgroundTasks.add_task` for one test to raise a deterministic synthetic scheduling exception. It checks exactly one registration attempt, response status/body equality, no notifier invocation, fixed safe diagnostic, and no scheduling canary in logs.

### RED — before route scheduling isolation

Run started `2026-11-14 14:57:38 UTC`.

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync --locked --extra test \
  pytest -q -p no:cacheprovider \
  tests/integration/test_completion_notification.py::test_task_scheduling_failure_preserves_response_and_safe_diagnostics
```

Actual exit code: `1`; `1 failed in 0.91s`.

```text
assert control_status == 200
> assert failing_status == control_status
E assert 500 == 200
```

The successful extraction response was replaced by a 500 when `add_task` raised before the response was returned. This is the intended scheduling-isolation RED.

### GREEN — after narrow route catch

Run started `2026-11-14 14:57:57 UTC`.

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync --locked --extra test \
  pytest -q -p no:cacheprovider \
  tests/integration/test_completion_notification.py::test_task_scheduling_failure_preserves_response_and_safe_diagnostics
```

Actual exit code: `0`.

```text
.                                                                        [100%]
1 passed in 0.81s
```

`create_extraction` catches ordinary exceptions only around the `BackgroundTasks.add_task` call, emits the fixed `Completion notification scheduling failed.` message, does not retry or dispatch synchronously, and returns the original extraction response. The test's assertions were unchanged.

## Diff references

- N06 extension: `apps/llm-service/tests/integration/test_extraction_pipeline_boundary.py`.
- N08–N10 tests and raw ASGI helper: new `apps/llm-service/tests/integration/test_completion_notification.py`.
- Safe dispatch and timeout: `apps/llm-service/app/services/notification.py`.
- Timeout setting: `apps/llm-service/app/core/config.py`.
- Scheduling isolation and dispatch registration: `apps/llm-service/app/api/routes.py`.

No N02 test changes were made. The tests do not establish real user delivery, durable delivery, exactly-once delivery, or App database transaction durability.
