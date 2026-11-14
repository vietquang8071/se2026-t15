# N06 — Structural Response Validation Characterization

## Purpose

N06 checks that an injected structurally invalid extraction result retains the existing HTTP error contract and does not dispatch `extraction.completed`. It is a characterization test, not feature RED: the expected behavior already existed in the Phase 05.1 production implementation.

## Test change

Extended `apps/llm-service/tests/integration/test_extraction_pipeline_boundary.py::test_invalid_injected_extraction_response_maps_to_error_envelope`.

The test now:

- Uses the existing valid request and valid authentication header.
- Counts calls to the invalid fake extraction service, proving validation reached the service.
- Installs an app-scoped recording notifier.
- Preserves the existing assertions for HTTP 502, `INVALID_STRUCTURED_OUTPUT`, matching `request_id`, and no bearer-token disclosure.
- Asserts exactly one extraction call and zero notifier dispatch attempts.

No JSON serialization round-trip or route-level response revalidation was added. FastAPI `response_model=ExtractionResponse` and the existing verified response builder boundary remain in place.

## Baseline characterization run

Run started `2026-11-14 14:49:34 UTC`, from `apps/llm-service`.

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync --locked --extra test \
  pytest -q -p no:cacheprovider \
  tests/integration/test_extraction_pipeline_boundary.py::test_invalid_injected_extraction_response_maps_to_error_envelope
```

Actual exit code: `0`.

```text
.                                                                        [100%]
1 passed in 0.83s
```

Observed result: HTTP 502 with the existing `INVALID_STRUCTURED_OUTPUT` envelope, one extraction-service call, and an empty notifier attempt list. Authentication and request validation remain active: the valid authenticated request reaches the injected extraction service. The notifier was not invoked when FastAPI handled response validation failure.

The same case is included in the later 107-test focused regression and the 559-test full-service suite; both passed. No validation gap was found, so no production response-validation change was warranted.
