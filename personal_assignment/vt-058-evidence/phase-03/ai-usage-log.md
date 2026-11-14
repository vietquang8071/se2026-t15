# AI Usage Log — Phase 03

> Exact timestamps and model versions were not recorded. No tests, benchmarks, mutations, code changes, or commits occurred while producing this design documentation.

| ID | AI Tool / Activity | Prompt or Task | AI Output | Human Review | Evidence |
|---|---|---|---|---|---|
| AI-03-01 | Codex assistant; initial Phase 03 design | Initial request to refine N01–N17, preserve pairwise rows, characterize validation, define fakes/Red evidence and commands. The complete original design is in the conversation; this task summary is not a verbatim prompt. | Initial N01–N17 design and PW01–PW21, preserved in initial-test-design.md. | Later review identified FIX-01–03; initial weaknesses retained in historical file. | Initial design file and Phase 03 conversation. |
| AI-03-02 | Human engineering review | Reconstructed prompt summary: add N18 for large-valid-input timeout; correct Red/Green classification; identify and later correct duplicate N03/N04 and overlapping N16/N08 proposals. Details are in human-review.md. | Not an AI proposal; human review decisions. | FIX-01, FIX-02, FIX-03 accepted for final test design. No test code correction is claimed. | human-review.md. |
| AI-03-03 | Codex assistant; revised design | Reconstructed prompt summary: apply FIX-01–03; produce N01–N18, retain and recompute all 21 pairwise rows, and specify future evidence. | final-test-design.md; design calculation: 39 feasible combinations, 61 pairs, 21 selected rows, zero uncovered. | Design only; reviewer has not approved implementation here. | final-test-design.md and prior pairwise rows. |
| AI-03-04 | Codex assistant; documentation/evidence preservation | Reconstructed prompt summary: preserve Phase 03 design, review and final plan in exactly four Markdown artifacts, validate the documentation and Git evidence, and do not implement or run tests. | Initial design, human review, final design and usage log. | No further decision beyond preserving evidence; explicit implementation authorization still required. | Phase 03 evidence directory; final Git status. |

## Verbatim Phase 03 Design Prompt — AI-03-01

> You are continuing **BT3 — VT-058** on branch `feature/vt-058-llm-notification`.
>
> Read `personal_assignment/vt-058.md` and the approved revised implementation plan.
>
> **STRICT READ-ONLY MODE. Do not edit files, create commits, change branches, run tests, or implement anything.**
>
> Your next task is **Phase 03: Risk-Based Test Design**, not implementation.
>
> 1. Refine test scenarios N01–N17 into executable test specifications with preconditions, fixtures, inputs, steps, expected outputs, priority, and intended file paths.
> 2. Identify which existing tests can be extended instead of duplicated.
> 3. Analyze response structural validation and request-response identity mismatch separately.
> 4. Define deterministic fake extraction services, fake providers, and fake notifiers.
> 5. Generate a feasible pairwise test dataset for the four approved factors. Include every row, an explanation of constraints, and a method to verify feasible pair coverage.
> 6. Design exact-byte-limit test data for both Content-Length and streamed-body validation.
> 7. Identify the strongest test for killing each `>` to `>=` mutation.
> 8. Identify at least two likely weak, redundant, or misleading AI-generated tests that the developer should independently review and correct.
> 9. Define clear Red-state assertions for the new notification behavior and distinguish them from characterization tests that should already pass.
> 10. Define test commands and evidence requirements for the subsequent implementation phase.
>
> Do not fabricate execution results.
>
> Produce the test design in the response only.
>
> **STOP after Phase 03 test design and await explicit approval before writing tests or implementation code.**

## Human Review Prompt Record — AI-03-02

The FIX-01–03 block below is a focused summary of the review criteria, not a verbatim reproduction of the full combined request and not a claim that implementation or tests occurred:

> FIX-01 — Add a Direct Large-Input Failure-Path Test. The assignment identifies large inputs causing unexpected timeout or degraded performance as the principal risk. Existing size-boundary tests, a request-timeout test, and a 200-concurrent-task experiment do not combine a large but valid input with a controlled extraction timeout. Add N18: a valid transcript JSON payload approaching but within the configured maximum; deterministic fake extraction service with controlled waiting; short request timeout; expect 504 REQUEST_TIMEOUT; no extraction.completed dispatch; bounded test safety timeout; no live OpenRouter call. Separate this from request-size rejection. Also define a separate large-input latency/memory experiment with deterministic fake extraction. Do not create 200 maximum-size payloads simultaneously and do not treat mutation tests as large-payload performance tests.
>
> FIX-02 — Correct Red/Green Classification. Do not call every case genuine feature Red. N05 may pass before notification implementation because failed extraction already emits no notification. N11 is principally integration/concurrency regression after notification support. N12–N14 characterize existing size behavior. Separate genuine feature Red, staged Red, characterization, regression, mutation-killing, and performance cases. For every genuine/staged Red specify baseline, expected failing assertion, failure reason, intended Green behavior, and evidence. Do not count import errors as behavioral Red and do not fabricate results.
>
> FIX-03 — Prepare Human Correction of AI-Generated Tests. Candidate 1: N03/N04 repeat existing auth/request-validation tests; extend existing tests with zero-dispatch assertions instead of duplicating setup/status checks. Candidate 2: N16 diagnostic privacy overlaps N08; merge relevant privacy assertions into N08 unless N16 proves an independent helper contract. For each, record proposal, weakness, repository evidence, human decision, corrected test, and expected quality improvement. These are design review decisions; do not claim code changes occurred. The developer must later preserve generated test code and actual correction/deletion diff.

## AI-03-03 and AI-03-04 Prompt Record

AI-03-03 (revised final design) and AI-03-04 (evidence preservation) were handled as separate activities within the combined current user request. There was no separately recorded prompt message for AI-03-03 that can be quoted independently. Their table entries are therefore explicitly labeled reconstructed prompt summaries, not verbatim prompts. No timestamp, tool version, test run, or separate final approval is inferred.

## Decisions and Future Work

- **AI proposals:** initial test matrix, pairwise rows, Red/Green suggestions, fakes and commands.
- **Human decisions:** FIX-01 adds N18 and separate large-input resource experiment; FIX-02 separates feature/staged Red from characterization/regression/mutation/performance; FIX-03 requires future code-level correction/removal of at least two weak/duplicate AI test proposals.
- **Final recommendation:** use N01–N18 and the recomputed pairwise design in final-test-design.md.
- **Future implementation:** write tests, capture real Red/Green, run mutations and restore, execute load/resource experiments, and record actual outcomes only after authorization.
- No run results, benchmark values, mutation results, commits, or implementation status are claimed.
