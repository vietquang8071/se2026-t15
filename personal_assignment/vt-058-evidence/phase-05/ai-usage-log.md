# AI Usage Log — Phase 05.1

> No model version or commit is recorded. Activity timestamps are UTC and only included where available from tool execution. No deployment or external notification delivery occurred.

| ID | AI Tool / Task | Prompt or Instruction | AI Output | Human Review | Evidence |
|---|---|---|---|---|---|
| AI-05-01 | Codex; baseline and RED confirmation | Reconstructed prompt summary: verify required branch/SHA/status and authorized scope; compare the N02 test with Phase 04; rerun its existing RED before changing production code. | Baseline matched. N02 rerun at `2026-11-14 14:28:35 UTC` exited 1 at the expected empty-dispatch assertion. | User-provided scope and test criteria governed the work; independent developer review remains pending. | `n02-green-evidence.md`; Git status and test output. |
| AI-05-02 | Codex; minimal notification implementation | Reconstructed prompt summary: add only the event contract, async notifier protocol/no-op, app-scoped state/dependency, and one BackgroundTasks dispatch after successful extraction; do not modify N02 or implement timeout/failure isolation. | Created `notification.py`; modified `main.py`, `dependencies.py`, and `routes.py`. | No separate human review of generated production code has yet been recorded. | Production diff and `implementation-review.md`. |
| AI-05-03 | Codex; N02 GREEN execution | Reconstructed prompt summary: rerun the exact unchanged N02 test and accept GREEN only if it passes with one allowlisted dispatch. | Run at `2026-11-14 14:30:03 UTC`: exit 0, `1 passed in 1.23s`. | No N02 assertion or setup edits were made in Phase 05.1. | `n02-green-evidence.md`; pytest output. |
| AI-05-04 | Codex; focused regression testing | Reconstructed prompt summary: run runtime integration tests, invalid injected-response mapping, and response identity contract tests using the locked no-sync environment. | Run at `2026-11-14 14:30:16 UTC`: exit 0, `52 passed in 1.41s`. | No regression failure was reported in this focused selection; broader suite remains unrun. | `n02-green-evidence.md`; pytest output. |
| AI-05-05 | Codex; code review and evidence preservation | Reconstructed prompt summary: review authorized production files for architecture, correctness and security; document focused results and limitations; verify branch, HEAD, staged state, and modification scope. | Recorded self-review, residual risks, and evidence in the three Phase 05.1 files. | Independent developer review and explicit approval are still required. | `implementation-review.md`; final Git checks. |

## Prompt provenance

The full Phase 05.1 instruction was supplied as one combined user request in this conversation. There were no separate recorded prompts for each AI-05 activity. The table therefore labels the activity-specific text as reconstructed prompt summaries rather than verbatim prompts. The combined user request is the source of the authorized scope and acceptance criteria.

## Work boundaries

- AI-generated production changes are limited to the four authorized paths: new `app/services/notification.py`, plus `app/main.py`, `app/api/dependencies.py`, and `app/api/routes.py`.
- The N02 test was written in Phase 04 and was not modified in Phase 05.1.
- Human review of the production patch has not yet occurred. The earlier test-author correction in Phase 04 is not represented as a new human approval here.
- Future work: after explicit approval, review Phase 05.1, then address N08 notifier exception/privacy, N09 bounded timeout/cancellation, N10 scheduling failure, and N06 structural-invalid-response notification safety characterization.
- No commit, push, PR, performance result, mutation result, real notification delivery, database durability, or exactly-once guarantee is claimed.
