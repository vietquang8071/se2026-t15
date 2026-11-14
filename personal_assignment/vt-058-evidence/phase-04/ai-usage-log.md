# AI Usage Log — Phase 04

> No model version, commit, approval beyond the user-provided scope, or test result is inferred. Times below are only recorded where the tool call timestamp was available (UTC).

| ID | Tool / Activity | Prompt / Task | Output | Human Review | Evidence |
|---|---|---|---|---|---|
| AI-04-01 | Codex; baseline and characterization inspection | Reconstructed prompt summary: verify branch/status/HEAD, read the VT-058 source documents and LLM Service code, then run the existing success and invalid-response characterization tests before editing. | Confirmed baseline branch/SHA, read the required source, and ran two selected characterization tests. | User had explicitly bounded write scope and required these tests; no independent code review is recorded yet. | baseline.md; command output and timestamp. |
| AI-04-02 | Codex; N02 test-only change | Reconstructed prompt summary: extend the existing typed-response runtime test with an app-scoped recording fake and exactly-one allowlisted event assertion; do not add production hooks. | Modified only `apps/llm-service/tests/integration/test_runtime.py`; added local fake, service call count and assertions. | Corrected the initial test setup mistake (`request_model.meeting_id` → `request_model.meeting.id`) after the first run. This was a test-author correction, not a human approval. | n02-red-evidence.md; Git diff. |
| AI-04-03 | Codex; N02 execution | Run the modified N02 test in isolation and accept only a behavioral notification assertion failure as genuine RED. | Actual result: HTTP/schema and extraction-call assertions passed; expected one dispatch, observed zero; exit 1. | The initial AttributeError attempt was rejected as invalid RED; the corrected run is the evidence. | n02-red-evidence.md; exact command and pytest excerpt. |
| AI-04-04 | Codex; test-quality review and evidence preservation | Reconstructed prompt summary: review correctness, isolation, assertions, maintainability and privacy; create baseline, RED evidence, and usage-log Markdown only; verify scope without attempting GREEN. | Test-quality observations and actual execution evidence recorded. No GREEN or implementation attempted. | No separate developer review of the resulting test is recorded. N03/N04 and N16/N08 human correction requirements remain future tasks. | Three Phase 04 Markdown files; final Git status/diff checks. |

## Prompt provenance

The full Phase 04 task prompt is present in this conversation. This evidence log records it as reconstructed summaries in the table rather than duplicating the full task text. The summaries are not verbatim prompts. No timestamps are assigned to activities without a recorded tool timestamp.

## Decisions and future work

- **AI-generated test change:** one extension to the existing N02 success-path test, confined to the authorized test file.
- **Human-provided constraints:** test-only RED phase; no production changes; no additional test or fixture files; no attempts to make N02 pass.
- **Observed execution:** the baseline characterization run passed 2 tests; the corrected isolated N02 run failed at the expected zero-dispatch assertion. The first N02 attempt failed at incorrect test setup and is explicitly excluded from RED evidence.
- **Future Phase 05:** implement the minimal approved notification injection and dispatch boundary, then rerun the same N02 assertions for GREEN only after explicit authorization.
- No notification delivery, durable delivery, exactly-once behavior, production performance, or database durability is established by this phase.
