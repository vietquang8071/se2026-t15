# Phase 06.3 — Regression Results

## Environment and scope

- Branch: `feature/vt-058-llm-notification`.
- Current committed baseline: `beae5161608cba48db81a10e892e5c743de55e10` (`mutation testing`).
- Developer-confirmed uncommitted changes: HC-01 in `test_runtime.py` and HC-02 in `test_pairwise_completion_notification.py`.
- Environment: Python 3.12.3, pytest 8.4.2, existing service virtual environment. No dependency installation or synchronization.
- No production code was changed. No performance or large-payload resource benchmark was run.

## N12/N13 corrected boundary tests

Started `2026-11-14 16:10:24 UTC`. The initial uv attempt could not create uv's temporary lock in the sandbox's read-only cache. The same no-sync command was rerun with approved escalation; pytest then executed normally.

    PYTHONDONTWRITEBYTECODE=1 uv run --no-sync --locked --extra test pytest -q -p no:cacheprovider tests/integration/test_runtime.py -k 'n12 or n13' -vv

Exit code **0**; **2 passed, 25 deselected in 1.17s**. N12 and N13 each use a valid compact UTF-8 request of **1,587 bytes**; the one-byte-over value is **1,588 bytes**. N12's declared Content-Length path and N13's split streamed-body path both reached the fake extraction service and returned a valid response.

## Pairwise suite

Started `2026-11-14 16:10:39 UTC`.

    PYTHONDONTWRITEBYTECODE=1 uv run --no-sync --locked --extra test pytest -q -p no:cacheprovider tests/integration/test_pairwise_completion_notification.py -vv

Exit code **0**; **22 passed in 2.24s**: verifier plus PW01–PW21. The output identified each row and marked every row PASS. Repeated stability runs used the existing virtual-environment interpreter directly, with the same pytest options:

| Run | Command target | Result | pytest duration |
|---|---|---:|---:|
| 1 | `test_notifier_timeout_is_bounded_and_cancels_dispatch` | 1 passed | 1.27s |
| 2 | Same N09 test | 1 passed | 0.91s |
| 3 | Same N09 test | 1 passed | 0.86s |
| 1 | `test_full_pipeline_remains_request_isolated_under_concurrency` | 1 passed | 0.93s |
| 2 | Same N11 test | 1 passed | 0.92s |
| 3 | Same N11 test | 1 passed | 1.46s |
| 1 | Complete pairwise module | 22 passed | 1.51s |
| 2 | Complete pairwise module | 22 passed | 1.53s |
| 3 | Complete pairwise module | 22 passed | 1.91s |

The repeat commands were run sequentially; individual wall-clock timestamps were not separately sampled. Repeats provide observed stability only.

Each repeat used this command from `apps/llm-service`, with the target replaced by the test shown in the table:

    PYTHONDONTWRITEBYTECODE=1 /home/vitquay1708/Study_Space/SE/apps/llm-service/.venv/bin/python -m pytest -q -p no:cacheprovider TARGET

The current pairwise execution identified every approved row exactly once and passed: PW01 PASS; PW02 PASS; PW03 PASS; PW04 PASS; PW05 PASS; PW06 PASS; PW07 PASS; PW08 PASS; PW09 PASS; PW10 PASS; PW11 PASS; PW12 PASS; PW13 PASS; PW14 PASS; PW15 PASS; PW16 PASS; PW17 PASS; PW18 PASS; PW19 PASS; PW20 PASS; PW21 PASS. The separate verifier also passed the exact ordered-ID assertion and the 39/61/zero-uncovered checks.

## Focused regression

Started `2026-11-14 16:13:35 UTC` and exited **0** in 5.65 seconds wall time (pytest reports **133 passed in 4.66s**):

    PYTHONDONTWRITEBYTECODE=1 /home/vitquay1708/Study_Space/SE/apps/llm-service/.venv/bin/python -m pytest -q -p no:cacheprovider tests/integration/test_runtime.py tests/integration/test_verified_extraction_service.py tests/integration/test_pairwise_completion_notification.py tests/integration/test_completion_notification.py tests/integration/test_extraction_pipeline_boundary.py tests/contract/test_response_models.py

This includes the exact-boundary and over-limit cases, authentication/request-validation/provider/evidence/identity paths, N02 and N06–N10 regressions, N11 concurrent isolation, the full pairwise module, and response-model contract tests.

## Full LLM Service regression

Started `2026-11-14 16:13:51 UTC`, ended `16:13:59 UTC`; exit code **0**, 7.72 seconds wall time, **585 passed in 6.50s**:

    PYTHONDONTWRITEBYTECODE=1 /home/vitquay1708/Study_Space/SE/apps/llm-service/.venv/bin/python -m pytest -q -p no:cacheprovider

No failed or skipped tests were reported in the pytest summary. This is the full service test suite, not a performance measurement. Historical Phase 06.1 count was also 585; the current pass is a new execution, not an assumed carry-forward.

## Mutation confirmation after HC-01

Both mutants ran only in `/tmp/vt058-phase0623.J3ztKe/mutant` using the corrected N12/N13 test file. M01 changed only declared length `>` to `>=`; N12 failed with 413 instead of 200, then passed after restore. M02 changed only streamed-byte `>` to `>=`; N13 failed with 413 instead of 200, then passed after restore. All isolated/restored/repository source hashes matched `299f7cfd050a2114a5eae471d2f8f5bb5c50ba1311ef690613f1d4a82ef84a01`. The scoped score is 2/2; see `mutation-results.md` for exact output.

## Limitations

- The existing environment has no `coverage` module, so numerical statement/branch coverage was unavailable without adding a dependency. No package was installed.
- N17 (200 concurrent tasks, p95 target) and N18 (large valid payload timeout/resource experiment) were not run in this milestone.
- Fake providers and notifiers establish deterministic contract behavior, not production OpenRouter throughput or durable user delivery.
