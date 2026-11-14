# N02 Genuine RED Evidence — Successful Extraction Completion Notification

## Requirement and location

- Test ID: **N02 — Successful Extraction Completion Notification**.
- Acceptance criterion: **AC-01** — a successful validated extraction dispatches exactly one `extraction.completed` event in that request's execution path.
- Existing test extended: `apps/llm-service/tests/integration/test_runtime.py::test_dependency_override_returns_typed_extraction_response`.
- Baseline HEAD: `5e54822fca535972ef9b10a7d39dfbabc7df4b3d` on `feature/vt-058-llm-notification`.

## Test-only change and injection contract

The existing success-path test now retains its typed `ExtractionResponse` checks and adds a call count to its local fake extraction service. It defines a local asynchronous recording fake with `dispatch(event)`, installs it at `app.state.completion_notifier`, and expects one event with exactly these fields:

```json
{
  "event_type": "extraction.completed",
  "request_id": "<the request request_id>",
  "meeting_id": "<the request meeting.id>",
  "status": "completed"
}
```

The assertion uses actual fixture IDs, not the placeholders above. Exact dictionary equality rejects transcript text, credentials, provider output, and undocumented keys. The fake records dispatch attempts only; it does not claim delivery to a user.

Future Phase 05 injection contract selected for this test: the app-scoped dependency reads `request.app.state.completion_notifier`; the adapter exposes `async dispatch(event: dict[str, str])`. This is a test seam only in Phase 04. No production hook or module was added.

## RED execution

Run started at `2026-11-14 14:15:07 UTC`, from `apps/llm-service`.

Exact command:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync --locked --extra test \
  pytest -q -p no:cacheprovider \
  tests/integration/test_runtime.py::test_dependency_override_returns_typed_extraction_response
```

Actual exit code: `1` (expected failing test). Pytest summary: `1 failed in 1.13s`.

Relevant excerpt copied from the pytest output (surrounding fixture representation and stack frames omitted):

```text
F                                                                        [100%]
=================================== FAILURES ===================================
__________ test_dependency_override_returns_typed_extraction_response __________

        assert response.status_code == 200
        assert ExtractionResponse.model_validate(response.json()) == response_model
        assert fake_service.calls == 1
>       assert recording_notifier.dispatch_attempts == [
            {
                "event_type": "extraction.completed",
                "request_id": request_model.request_id,
                "meeting_id": request_model.meeting.id,
                "status": "completed",
            }
        ]
E       AssertionError: assert [] == [{'event_type... 'completed'}]
E         
E         Right contains one more item: {'event_type': 'extraction.completed', 'meeting_id': 'meeting-42', 'request_id': 'req-20261005-001', 'status': 'completed'}
E         Use -v to get more diff

tests/integration/test_runtime.py:366: AssertionError
=========================== short test summary info ============================
FAILED tests/integration/test_runtime.py::test_dependency_override_returns_typed_extraction_response
1 failed in 1.13s
```

The first RED run, at `2026-11-14 14:14:51 UTC`, was invalid: the expected meeting ID initially referenced nonexistent `request_model.meeting_id`. Pytest imported the module and fixtures, but failed with `AttributeError` before the notification assertion. The test-only setup was corrected to use `request_model.meeting.id`; that attempt is not counted as RED evidence. The subsequent run above reached the intended assertion.

## Why this is genuine behavioral RED

The module and fixtures load. The authenticated request reaches `/v1/extractions`; status is `200`; the existing response model assertion passes; and the fake extraction service records one call. The only failing assertion expects one recording-notifier dispatch and observes zero. The current route has no notification behavior and ignores the test-only app-state attribute. The test uses the injected fake extraction service; automated-test network blocking is enabled. The failure is not an import, fixture, authentication, request-validation, provider, or network failure.

## Test-quality review

- **Correctness:** Exercises the real API route, validates the successful response, confirms extraction was invoked once, then requires one event with the request and meeting IDs and `completed` status.
- **Isolation:** The fake and its event list are local to this test and app instance. No shared mutable global, live provider, or sleep is used.
- **Assertion quality:** Retains the HTTP/schema assertions and uses exact event dictionary equality. It verifies a dispatch attempt, not notification delivery.
- **Maintainability:** Extends the existing test instead of duplicating request setup. The only test code change is in `test_runtime.py`.
- **Security:** Expected event fields exclude transcript content, bearer token, provider response, and extra metadata. The test fixture contains synthetic data.
- **Correction made:** Fixed the test's meeting ID access from the invalid `request_model.meeting_id` to `request_model.meeting.id`. No AI-generated weak-test correction requirement is claimed as complete; N03/N04 and N16/N08 remain later review items.

## Relevant test diff

The change is reproducible with `git diff -- apps/llm-service/tests/integration/test_runtime.py` before any later implementation changes. It adds a local fake, call count, app-state seam, and assertions; it does not edit production code.

```diff
 def test_dependency_override_returns_typed_extraction_response(
     full_request: dict[str, Any], full_response: dict[str, Any]
 ) -> None:
@@
     class FakeExtractionService:
+        def __init__(self) -> None:
+            self.calls = 0
+
         async def extract(self, request: ExtractionRequest) -> ExtractionResponse:
+            self.calls += 1
             assert request.request_id == request_model.request_id
             return response_model
 
+    class RecordingNotifier:
+        def __init__(self) -> None:
+            self.dispatch_attempts: list[dict[str, str]] = []
+
+        async def dispatch(self, event: dict[str, str]) -> None:
+            self.dispatch_attempts.append(dict(event))
+
     app = create_test_app()
+    fake_service = FakeExtractionService()
+    recording_notifier = RecordingNotifier()
+    app.state.completion_notifier = recording_notifier
 
     async def provide_fake_service() -> FakeExtractionService:
-        return FakeExtractionService()
+        return fake_service
@@
     assert response.status_code == 200
     assert ExtractionResponse.model_validate(response.json()) == response_model
+    assert fake_service.calls == 1
+    assert recording_notifier.dispatch_attempts == [
+        {
+            "event_type": "extraction.completed",
+            "request_id": request_model.request_id,
+            "meeting_id": request_model.meeting.id,
+            "status": "completed",
+        }
+    ]
```

## Phase 05 boundary and status

The minimum future production slice is an app-scoped `CompletionNotifier` dependency that reads `app.state.completion_notifier`, an allowlisted event value, and dispatch after successful extraction. Phase 05 must provide the runtime no-op adapter and bound/isolate adapter errors and timeouts as approved. No such logic is implemented here.

**GREEN has not been achieved and was not attempted.** The intended RED remains in place for developer review.
