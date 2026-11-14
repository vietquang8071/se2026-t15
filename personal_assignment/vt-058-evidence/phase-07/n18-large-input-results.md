# N18 — Large Valid Input Request Timeout

## Request and timeout setup

The test loads `tests/fixtures/requests/full_valid_request.json`, assigns a unique request and meeting ID, and appends ASCII `x` padding to the first transcript segment. It serializes with `json.dumps(..., ensure_ascii=False, separators=(",", ":")).encode("utf-8")`, measures the resulting byte string, then validates the payload with `ExtractionRequest` before sending it.

- Configured `max_request_bytes`: **1,048,576 bytes (1 MiB)**.
- Actual serialized request body: **1,048,064 bytes**, exactly 512 bytes below the limit.
- Request timeout: **0.1 seconds**.
- Notification timeout: **1.0 second**, configured independently.
- Outer client watchdog: **5.0 seconds**.

The injected extraction fake records the request ID, signals its entry event, then waits on an unset event. Its `finally` block records cancellation. It never returns an extraction response. A recording notifier is injected, and no provider adapter is used. The automated test `conftest.py` also blocks outbound HTTPX network calls.

## Result

The extractor was entered once and cancellation was observed. The application returned HTTP **504** with a valid `ErrorEnvelope`, code **`REQUEST_TIMEOUT`**, status code 504, and the expected request ID. The response was explicitly checked to be **not 413**. Notification dispatch attempts were zero, so no `extraction.completed` event was emitted. The request completed within the independent 5-second watchdog.

This demonstrates the request timeout path for the constructed, schema-valid body below the configured byte limit. It does not demonstrate a successful extraction or completion notification for this failure case.

## Command and result

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync --locked --extra test pytest -q -p no:cacheprovider tests/integration/test_large_input_timeout.py -vv
```

Result: **1 passed in 1.06 seconds**, exit code 0. The command was first blocked because sandboxed `uv` could not create a temporary file under `~/.cache/uv`; the same no-sync, locked command was then run with the required filesystem approval. No package synchronization or installation occurred.
