# Human Engineering Review — VT-058 Initial Plan

## A. Review Context

Assignment BT3 — AI-05 — VT-058. Specification: personal_assignment/vt-058.md. Reviewed plan: initial-implementation-plan.md. Branch feature/vt-058-llm-notification. Baseline SHA 5e54822fca535972ef9b10a7d39dfbabc7df4b3d. Review scope: response validation, notification boundary, and test coupling.

Branch, SHA, spec, and cited source were inspected. This records decisions, not implementation or test results.

## B. Review Decisions

### REV-01 — Response Revalidation

**Initial proposal:** JSON-serialize route result, then repeat full response and request-response identity validation before scheduling.

**Evidence:** apps/llm-service/app/services/response_builder.py — ResponseBuilder.build calls validate_response_for_request(request, response). apps/llm-service/app/api/routes.py — create_extraction declares response_model=ExtractionResponse. apps/llm-service/tests/integration/test_extraction_pipeline_boundary.py — test_invalid_injected_extraction_response_maps_to_error_envelope checks a 502 INVALID_STRUCTURED_OUTPUT response for invalid injected output.

**Risk:** Duplicates structural and identity checks without evidence of a production-path gap.

**Decision: REVISE.** Characterize first. Distinguish structural validation from request-response identity validation. Do not duplicate JSON serialization/revalidation unless a behavioral test demonstrates need.

**Revised approach:** Extend/characterize invalid structural output with recording notifier; assert no dispatch. Retain existing identity checks; add a narrow guard only if a production-path gap is demonstrated.

**Impact:** Removes unconditional route round-trip; adds characterization before new validation code.

### REV-02 — Logging Is Not Notification Delivery

**Initial proposal:** In-process logging adapter as default notification mechanism.

**Evidence:** VT-058 AC-01 requires scheduling/dispatch; AC-04 allowlists metadata. External messaging, brokers, migrations, and durable delivery are out of scope; no recipient/sink exists.

**Risk:** Log record does not prove independent adapter invocation or recipient receipt.

**Decision: REVISE.** Add injectable CompletionNotifier and recording fake. Logging is diagnostics only. Use no-op runtime adapter pending authorized sink. Do not claim user notification/durable delivery.

**Revised approach:** Distinguish event creation, dispatch attempt, adapter-call return. No-op return is not proof of user receipt.

**Impact:** Adds observable injection boundary without external service/broker/migration.

### REV-03 — Separate Boundary Tests from Notification Assertions

**Initial proposal:** Couple exact-byte tests with notification assertions.

**Evidence:** apps/llm-service/app/core/middleware.py — ExtractionRequestBoundaryMiddleware.__call__ independently checks Content-Length and streamed bytes. apps/llm-service/tests/integration/test_runtime.py has existing declared and streamed oversize tests.

**Risk:** Coupling independent middleware and notification behavior makes failures harder to locate and duplicates unrelated assertions.

**Decision: REVISE.** N12–N14 focus on byte semantics and successful processing. N02 covers dispatch; N08/N09 isolate notification failures. One combined-risk case is optional.

**Revised approach:** Exact-size tests assert acceptance/processing; over-limit tests assert 413; optional N15 combines exact limit with notifier failure.

**Impact:** Separates HTTP boundary semantics from delivery behavior.

## C. Review Summary

REV-01 reduces duplicate validation complexity; REV-02 prevents logs being misrepresented as delivery; REV-03 reduces test coupling/duplication. These were human engineering decisions based on repository evidence and scope, not automatic AI acceptance.

## D. Evidence References

- apps/llm-service/app/services/response_builder.py — ResponseBuilder.build and identity check.
- apps/llm-service/app/api/routes.py — create_extraction response model.
- apps/llm-service/tests/integration/test_extraction_pipeline_boundary.py — invalid injected result.
- apps/llm-service/app/core/middleware.py — two byte checks.
- apps/llm-service/tests/integration/test_runtime.py — oversize tests.
- personal_assignment/vt-058.md — AC-01–AC-05 and limitations.
