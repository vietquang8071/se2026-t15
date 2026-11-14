# AI Usage Log — Phase 05.2

> No model version or commit is recorded. Timestamps are UTC and only included where captured. No deployment, mutation experiment, benchmark, or real notification delivery occurred.

| ID | AI Tool / Task | Prompt or Instruction | AI Output | Human Decision | Evidence |
|---|---|---|---|---|---|
| AI-05.2-01 | Codex; baseline verification | Reconstructed prompt summary from the combined user request: verify branch, HEAD, clean status, Phase 05.1 implementation, and N02 GREEN before editing. | Confirmed branch `feature/vt-058-llm-notification`, HEAD `965b85940e8f3db9a34081ca388824e6f4329b34`, clean working tree; N02 passed `1 passed in 0.87s` at 14:49:03 UTC. | User-authorized scope followed; developer review pending. | baseline command/result in `regression-results.md`. |
| AI-05.2-02 | Codex; N06 characterization | Reconstructed prompt summary: extend the invalid injected-response test with a recording notifier; preserve 502 contract and assert zero dispatch; do not add duplicate validation. | N06 passed before production changes: 502 `INVALID_STRUCTURED_OUTPUT`, one extraction call, zero dispatch; characterization, not RED. | Existing FastAPI/response-builder validation boundaries retained. | `n06-characterization.md`. |
| AI-05.2-03 | Codex; N08 staged RED/GREEN | Reconstructed prompt summary: compare success control and raising notifier using raw response bytes; include privacy canaries; add safe fixed diagnostics without exposing exception details. | RED: missing notification-specific diagnostic; GREEN: `1 passed in 0.79s`; status/body remained equal. | No independent developer code review is recorded. | `failure-isolation-red-green.md`. |
| AI-05.2-04 | Codex; N09 staged RED/GREEN | Reconstructed prompt summary: configure positive finite notification timeout, keep it separate from extraction timeout, test a waiting notifier with bounded watchdog and observed cancellation. | RED: 7 failed (`2.26s`); GREEN: 7 passed (`0.87s`); cancellation observed and response matched control. | No independent developer code review is recorded. | `failure-isolation-red-green.md`. |
| AI-05.2-05 | Codex; N10 staged RED/GREEN | Reconstructed prompt summary: force a test-local `BackgroundTasks.add_task` error; preserve successful response and emit fixed safe diagnostic without fallback. | RED: scheduling failure changed status 200 to 500; GREEN: `1 passed in 0.81s`. | No independent developer code review is recorded. | `failure-isolation-red-green.md`. |
| AI-05.2-06 | Codex; regression and implementation review | Reconstructed prompt summary: run focused and complete service regressions, review authorized diffs, save evidence, and verify scope without starting later test phases. | Focused: 107 passed. Full service suite: 559 passed. Evidence and scope review recorded. | Developer approval remains pending; no AI-generated completion claim substitutes for independent review. | `regression-results.md`; `implementation-review.md`; final Git checks. |

## Prompt provenance and human review

The full Phase 05.2 instructions were supplied as one combined user request. No separate prompt messages were recorded for the six activity rows, so their prompt cells are explicitly reconstructed summaries, not verbatim prompts. The combined user request is the source of the authorization and requirements.

N03/N04 duplicate tests were not added, and N16 privacy checks were incorporated into N08. These choices follow the reviewed test design; they do not count as the two concrete developer-authored test correction/removal diffs required by VT-058. That requirement remains pending for independent human review.

No approval, commit, push, PR, mutation result, benchmark value, production deployment, real user notification, durable delivery, or exactly-once guarantee is claimed.
