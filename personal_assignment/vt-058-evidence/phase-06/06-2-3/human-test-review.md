# Phase 06.3 — Human Test-Quality Review Checkpoint

## Review status

The actual Phase 06.1 test files were reviewed after both isolated mutations were restored. This document records AI review recommendations only. The mandatory developer checkpoint has **not** been completed, and no human-authored test correction is claimed.

## Candidate 1 — N12/N13 duplicated fake setup

- **Path/tests:** `apps/llm-service/tests/integration/test_runtime.py::test_n12_declared_content_length_accepts_exact_utf8_limit` and `test_n13_streamed_body_accepts_exact_utf8_limit`.
- **AI-generated behavior:** Both tests define an identical local `CountingExtractionService`, build the same fixture `ExtractionResponse`, and validate the same response. They differ in how the request body is delivered: N12 declares Content-Length; N13 sends two chunks without Content-Length.
- **Specific weakness:** Test setup is duplicated, which makes future assertion changes easier to apply inconsistently. The two cases are otherwise individually useful and mutation-traceable.
- **Evidence:** Each function contains its own local class with `requests: list[str]`, an `extract()` method appending `request.request_id`, and returns the same validated response model. The two tests independently assert HTTP 200, typed response equality, and one extraction request.
- **Proposed developer correction:** Extract a small stateless factory/helper for the counting service and shared typed-response construction. Keep N12 and N13 as separate independently selectable tests and retain their distinct ASGI request construction and exact behavioral assertions.
- **Acceptance criteria to preserve:** AC-05; exact valid UTF-8 body of N bytes; N12 declared Content-Length=N; N13 split streamed body with no Content-Length; extraction invocation; valid `ExtractionResponse`.
- **Validation after correction:** Run N12 and N13 separately against original middleware. If either behavioral assertion changes, repeat its isolated mutation experiment. Compare source against the preserved Phase 06.1 snapshots.
- **Mutation/pairwise impact:** A pure helper refactor should leave both mutation kills and all 61 pairwise pairs unaffected. Do not merge the tests into one opaque case.

## Candidate 2 — Pairwise row ID uniqueness guard

- **Path/test:** `apps/llm-service/tests/integration/test_pairwise_completion_notification.py::test_pairwise_dataset_covers_every_feasible_factor_pair`.
- **AI-generated behavior:** The verifier checks 39 feasible combinations, 61 feasible pairs, 21 selected values, row-value uniqueness, domain validity, feasibility, and zero uncovered pairs.
- **Specific weakness:** It does not directly assert that the selected row identifiers themselves are unique and exactly `PW01` through `PW21` in order. Duplicate or altered IDs could make pytest's per-row evidence ambiguous even if the underlying value tuples still cover all pairs.
- **Evidence:** `PAIRWISE_ROWS` carries the stable ID in column zero, while the verifier's `selected` projection starts at `row[1:]`; its uniqueness assertion therefore covers scenario tuples, not identifiers. The parametrization uses `row[0]` as the displayed pytest ID.
- **Proposed developer correction:** Add a direct assertion that the IDs equal the expected ordered sequence `PW01`–`PW21` (or an equivalent unique-ID assertion plus exact row-count check). Do not change any row's factor values.
- **Acceptance criteria to preserve:** All 21 approved rows, all 39 feasible combinations and 61 pairs, zero uncovered pairs, separately identifiable row execution.
- **Validation after correction:** Run the coverage verifier and the complete pairwise module; confirm every PW ID appears exactly once and all 61 pairs remain covered.
- **Mutation/pairwise impact:** This strengthens pairwise evidence identity without changing the dataset or either mutation test.

## Review of PW05/PW14/PW15

These rows share `over / size_reject / not_attempted` and differ in concurrency 8, 1, and 2. They are not recommended for removal: the approved dataset uses them to cover distinct concurrency values, and the test-local ASGI gate asserts all row requests arrive concurrently. Their evidence must continue to describe **concurrent HTTP rejection before extraction**, not concurrent extraction work. No row redesign was performed.

## Human checkpoint — action required

Developer: please review and manually make corrections to at least two AI-generated test cases. Candidate 1 offers two separately retained test cases (N12 and N13); Candidate 2 is the pairwise verifier. After making your changes, provide:

1. The exact test cases changed.
2. A brief reason for each correction.
3. Confirmation that the edits were developer-authored.

No test source was edited by Codex in this checkpoint. Human corrections are **PENDING**. Validation of the actual developer diff, coverage, flaky-test analysis, final regression, and the remaining evidence documents must wait for that confirmation.
