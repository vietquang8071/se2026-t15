# Phase 05.1 — Implementation Review

## Files changed

| Path | Change | Purpose |
|---|---|---|
| `apps/llm-service/app/services/notification.py` | New | Defines allowlisted event type, notifier protocol, and no-op adapter. |
| `apps/llm-service/app/main.py` | Modified | Stores one notifier per FastAPI app, defaulting to a new no-op instance; supports optional factory injection. |
| `apps/llm-service/app/api/dependencies.py` | Modified | Resolves the notifier from `request.app.state.completion_notifier`. |
| `apps/llm-service/app/api/routes.py` | Modified | Adds `BackgroundTasks`, obtains the notifier dependency, awaits extraction in the existing timeout, then schedules one dispatch and returns the same response. |

No test file was changed in Phase 05.1. The only test diff remains the pre-existing N02 RED change from Phase 04.

## Architecture and behavior review

- **Replaceable boundary:** `CompletionNotifier` is a small async Protocol; the route does not depend on an external provider, mail service, broker, or database.
- **App-scoped injection:** Each `create_app` invocation receives its own injected notifier or a fresh `NoOpCompletionNotifier`. The dependency reads the current request's app state, so the Phase 04 test seam works without global state.
- **Event construction:** The route creates a new `CompletionEvent` dictionary for each successful service return. Its literal contains exactly `event_type`, `request_id`, `meeting_id`, and `status`.
- **Ordering:** A service exception or request timeout exits before event construction. Event dispatch registration occurs after the existing `asyncio.timeout` block. One `BackgroundTasks.add_task` call is made per successful return.
- **Response:** The route returns the same response object from `service.extract`. The existing `response_model=ExtractionResponse` and verified-service `validate_response_for_request` boundary remain in place. No JSON serialization round-trip or duplicate route validation was added.
- **Task lifecycle:** Dispatch is registered with FastAPI `BackgroundTasks`; no detached `asyncio.create_task` is used.

## Security review

The constructed event has four allowlisted keys. It excludes transcript text, extracted meeting content, provider response data, bearer tokens, and API keys. The implementation adds no event logging, so it does not introduce raw identifiers into diagnostics. The N02 exact-dictionary assertion passed with the local recording fake.

## Test evidence

- Pre-implementation N02 rerun: exit `1`, expected zero-dispatch assertion; see [n02-green-evidence.md](n02-green-evidence.md).
- N02 after implementation: exit `0`, `1 passed in 1.23s`.
- Focused regressions: exit `0`, `52 passed in 1.41s` for runtime tests, invalid injected-response mapping, and response identity contract tests.
- `git diff --check`: exit `0`, no output.
- No full service suite, performance run, mutation experiment, or notification-failure scenario was executed.

## Relevant production diff summary

```diff
+class CompletionEvent(TypedDict):
+    event_type: Literal["extraction.completed"]
+    request_id: str
+    meeting_id: str
+    status: Literal["completed"]
+
+class CompletionNotifier(Protocol):
+    async def dispatch(self, event: CompletionEvent) -> None: ...
+
+class NoOpCompletionNotifier:
+    async def dispatch(self, event: CompletionEvent) -> None:
+        return None
```

`create_app` stores the injected notifier or a fresh no-op instance at `application.state.completion_notifier`. The route's relevant sequence is:

```python
async with asyncio.timeout(settings.llm_service_request_timeout_seconds):
    response = await service.extract(request)

event = {
    "event_type": "extraction.completed",
    "request_id": request.request_id,
    "meeting_id": request.meeting.id,
    "status": "completed",
}
background_tasks.add_task(notifier.dispatch, event)
return response
```

## Remaining gaps for Phase 05.2

| Severity | Gap | Follow-up |
|---|---|---|
| High | Notifier exceptions and timeouts are not yet bounded or isolated. | N08/N09 staged RED tests, then implement the approved narrow isolation wrapper. |
| High | Background task scheduling errors are not caught. | N10 staged RED, then add only approved scheduling-failure isolation. |
| Medium | Existing invalid injected-response regression observes the 502 contract but not notifier attempts. | N06 characterization should inject a recording fake and verify that response validation failure produces no completion dispatch. Do not add duplicate route revalidation without evidence. |
| Expected limitation | The default adapter is a no-op and sends nothing to a user. | Keep this explicit until a recipient/sink is approved. |
| Residual system risk | FastAPI background tasks are not durable and do not guarantee exactly-once delivery. The LLM Service does not own App database transactions. | Document; do not redesign this vertical slice. |

Phase 05.1 does not establish AC-03 or all AC-02 failure paths. It does not prove real user notification, durable delivery, exactly-once behavior, or database transaction durability.

## Review status

This is a Codex self-review against the approved Phase 05.1 scope. **Independent developer review and approval are pending.** No approval, commit, deployment, or merge is claimed.
