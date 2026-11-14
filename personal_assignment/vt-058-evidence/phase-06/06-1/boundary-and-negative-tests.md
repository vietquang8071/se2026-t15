# Phase 06.1 — Boundary and Negative-Path Tests

## Scope and test reuse

The implementation work in this phase is test-only. N03 and N04 extend the existing authentication and request-validation tests in `apps/llm-service/tests/integration/test_runtime.py`; no duplicate status-only tests were added. N05 extends existing verified-service provider and evidence failure tests in `apps/llm-service/tests/integration/test_verified_extraction_service.py`. N11 extends the existing full-pipeline isolation test in that file.

N06 remains the existing characterization test in `apps/llm-service/tests/integration/test_extraction_pipeline_boundary.py`; it was not edited. N02 and N08–N10 were not edited. Their unchanged tests are included in the focused and full regression runs.

## N03 — Authentication failure

Extended `test_extraction_rejects_missing_or_invalid_bearer_token`, preserving its four existing authorization cases (missing, incorrect Bearer token, Basic scheme, and empty Bearer value) and the existing 401 `AUTHENTICATION_REQUIRED` envelope assertions. A fresh recording notifier is installed per test and a counting extraction fake is provided. The added assertions require zero service calls and zero dispatch attempts. All four cases passed in the focused and full runs.

## N04 — Request validation failure

Extended `test_extraction_validates_request_before_calling_service` with the existing invalid timezone and synthetic private-note input. The test retains its 400 `VALIDATION_ERROR`, request ID, content type, and safe error-body assertions. It now also verifies that the app-scoped extraction fake was not invoked and the recording notifier recorded no dispatch.

## N05 — Provider and evidence failures

Extended the existing `test_provider_errors_map_without_exposing_provider_details` parameterization, which runs the real verified extraction service with `ScriptedProvider`. The configuration, rate-limit, provider-timeout, and provider-failure variants retain their existing HTTP status/error-code/retryability checks; each confirms one provider call and zero notification dispatch attempts.

Two existing evidence-path tests were also extended: `test_unknown_source_id_returns_unverified_evidence_error` exercises source/evidence validation after a real scripted provider response, and `test_unsupported_summary_overview_returns_non_success` exercises the verifier rejecting a claim. They preserve `502 UNVERIFIED_EVIDENCE` and assert zero dispatch. These remain actual verified-pipeline paths, not generic fake-service failures.

## N11 — Concurrent request/notification isolation

Extended `test_full_pipeline_remains_request_isolated_under_concurrency`. The existing fake provider now uses an `asyncio.Event` barrier for the two candidate calls rather than a fixed sleep, so both requests must overlap before the candidate stage proceeds. Each request has a unique request ID and meeting ID. The app-scoped recording notifier raises a synthetic exception for request A and returns normally for request B.

The test requires both HTTP responses to remain 200 with their own request/meeting identities, two candidate and four total provider calls, exactly two dispatch attempts, event IDs mapped to the correct meetings, exactly the four allowlisted event fields, successful normal completion for B, and a safe fixed diagnostic without the synthetic exception canary. It uses concurrent `asyncio.gather`, not sequential calls.

## N12–N14 — Request-size boundaries

N12–N14 are characterization/regression and future mutation-killing tests, not notification feature RED tests. They reuse `full_valid_request.json` and deterministic compact JSON serialization with `ensure_ascii=False`, UTF-8 encoding, and compact separators. The transcript contains Vietnamese text; the tests assert the UTF-8 bytes for `Tôi` are present. The exact body length is calculated from bytes, not Python character count.

For the request fixture and serialization used by N12/N13:

- Configured maximum **N = 1,587 bytes**.
- Exact request body = **1,587 UTF-8 bytes**.
- N+1 body = valid request body plus one trailing ASCII JSON whitespace byte = **1,588 bytes**.

| Test | Request construction | Required assertions |
|---|---|---|
| N12 `test_n12_declared_content_length_accepts_exact_utf8_limit` | Direct ASGI request with valid body exactly N bytes and declared `Content-Length: 1587`; max=N. | HTTP 200; `ExtractionResponse` validates and equals the fixture response; fake extraction called once with the fixture request ID. This reaches the declared-size comparison and does not assert notification behavior. |
| N13 `test_n13_streamed_body_accepts_exact_utf8_limit` | Same valid N-byte body split into two ASGI chunks; no Content-Length header; max=N. | HTTP 200; response contract validates; extraction fake called once. This reaches the accumulated streamed-byte comparison independently. |
| N14 declared `content-length` case | N-byte valid body plus one JSON whitespace byte; declared Content-Length is N+1; max=N. | HTTP 413, body `PAYLOAD_TOO_LARGE`, no extraction invocation, no notifier attempt. |
| N14 streamed `streamed-body` case | Same valid N+1 body split into chunks; Content-Length absent; max=N. | HTTP 413 `PAYLOAD_TOO_LARGE`, no extraction invocation, no notifier attempt. |

The pre-existing arbitrary oversized-request tests remain unchanged and continue to run. N14 adds the stricter valid-JSON exact N+1 semantics. No `>` to `>=` mutation was performed.

## Commands and actual results

Initial combined runtime slice started `2026-11-14 15:26:16 UTC`:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync --locked --extra test \
  pytest -q -p no:cacheprovider tests/integration/test_runtime.py \
  -k 'n12 or n13 or n14 or extraction_rejects_missing_or_invalid_bearer_token or extraction_validates_request_before_calling_service' -vv
```

Exit 0 — **9 passed, 18 deselected in 0.83s**.

Provider/evidence and concurrency slice started `2026-11-14 15:27:27 UTC`:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync --locked --extra test \
  pytest -q -p no:cacheprovider \
  tests/integration/test_runtime.py::test_extraction_rejects_missing_or_invalid_bearer_token \
  tests/integration/test_runtime.py::test_extraction_validates_request_before_calling_service \
  tests/integration/test_verified_extraction_service.py::test_provider_errors_map_without_exposing_provider_details \
  tests/integration/test_verified_extraction_service.py::test_unknown_source_id_returns_unverified_evidence_error \
  tests/integration/test_verified_extraction_service.py::test_unsupported_summary_overview_returns_non_success \
  tests/integration/test_verified_extraction_service.py::test_full_pipeline_remains_request_isolated_under_concurrency -vv
```

Exit 0 — **12 passed in 1.20s**.

Final isolated boundary run started `2026-11-14 15:39:06 UTC`:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync --locked --extra test \
  pytest -q -p no:cacheprovider tests/integration/test_runtime.py \
  -k 'n12 or n13 or n14' -vv
```

Exit 0 — **4 passed, 23 deselected in 0.85s**. The focused 133-test regression run and full 585-test run also passed after the final test edits; see `pairwise-execution.md` for the final suite commands/results.

## Traceability

- **AC-02 / I-02:** N03–N05 prove the existing auth, validation, provider and evidence failure paths do not dispatch a completion event.
- **AC-05:** N12/N13 exercise exact N acceptance through each size-checking branch; N14 exercises declared and actual streamed N+1 rejection with the established error code.
- **I-01:** N11 shows one request's notifier exception does not alter either concurrent successful extraction response.

The tests exercise the LLM Service boundary. They do not prove App database transaction durability or durable delivery to a recipient.
