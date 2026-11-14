# Phase 07 — AI Usage and Execution Log

## Assistance and implementation

| Activity | AI assistance and result |
|---|---|
| Test and benchmark design | Inspected the VT-058 assignment, final Phase 03 test design, routes, middleware, settings, schemas, service factory, ASGI client, existing request/response fixtures, provider fakes, and verified-pipeline integration tests. Reused the established summary/actions candidate and verifier response shapes and existing full-valid request/response fixtures. |
| N17 implementation | Added `tests/manual/vt058_phase07_benchmark.py` with prompt-keyed deterministic fake provider behavior, a recording notifier, client and ASGI concurrency gates, terminal response-body timestamp capture, validation and association checks, nearest-rank metrics, and a 90-second run watchdog. No provider response queue relies on sequential ordering. |
| N18 implementation | Added `tests/integration/test_large_input_timeout.py` with compact UTF-8 serialization, measured ASCII padding to 1 MiB minus 512 bytes, request model validation, a blocking/cancellation-recording fake service, separate request/notification timeouts, zero-dispatch assertions, and a 5-second outer watchdog. |
| Resource experiment | Added a separate `--mode large-input` script mode that ran nine scenarios at 25%, 75%, and max-minus-512 bytes with concurrency 1, 2, and 4. Each scenario ran in a fresh subprocess and recorded `ru_maxrss` and `tracemalloc` measurements. |
| Evidence | Recorded measured results and limitations in the three experiment reports and this usage log. |

## Commands and results

| Command | Result |
|---|---|
| `git branch --show-current` | `feature/vt-058-llm-notification` |
| `git rev-parse HEAD` | `beae5161608cba48db81a10e892e5c743de55e10` at baseline and final audit; unchanged. |
| `git status --short --untracked-files=all` | Initial baseline had two modified Phase 06 test files. Their diffs matched the two corrections proposed in Phase 06.3 evidence. During this pass, three modified and three new Phase 06.3 evidence files appeared in the worktree; they were inspected, preserved, and not edited in this pass. |
| `git diff --check` | Exit code 0 at baseline and again in the final audit after Phase 07 edits. |
| `PYTHONDONTWRITEBYTECODE=1 uv run --no-sync --locked --extra test pytest -q -p no:cacheprovider tests/integration/test_large_input_timeout.py -vv` | First sandbox attempt could not create a temporary file in `~/.cache/uv`; the same command with filesystem approval completed: **1 passed in 1.06 seconds**, exit code 0. No package sync or installation. |
| `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python tests/manual/vt058_phase07_benchmark.py --mode n17` | Exit code 0. Warm-up 8/8; two measured batches each 200/200 HTTP 200. p95 713.887 ms and 775.812 ms; worst batch below the 5.0-second target. |
| `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python tests/manual/vt058_phase07_benchmark.py --mode large-input` | Exit code 0. All nine scenarios produced the expected 200 responses with zero HTTP errors; results are in `large-input-resource-results.md`. |
| Full regression suite | **Not run in this Phase 07 pass by instruction.** The user’s latest direction was to focus on N17/N18 and not rerun old tests. The newly appeared Phase 06.3 `regression-results.md` records an earlier full-service result of 585 passed in 6.50 seconds; that prior result was not rerun or independently reproduced in this pass. |

## Developer decisions and review limits

- The requested branch and baseline HEAD were retained. No production files, dependencies, lock files, Phase 01–06 evidence, or previous test files were modified by this Phase 07 work.
- Existing uncommitted Phase 06 edits in `test_runtime.py` and `test_pairwise_completion_notification.py` were preserved. Phase 06 mutation experiments were not repeated in this pass.
- The Phase 06.3 evidence appeared after the initial baseline inspection. Its updated human-review record says the developer explicitly confirmed authorship of HC-01 and HC-02, and its regression/coverage/flaky-review files record validation. Accordingly, Phase 06.3 human corrections and evidence are documented complete. Numerical statement/branch coverage remains unavailable because the existing environment lacks the `coverage` module; no dependency was installed. These Phase 06 results were inspected but not rerun in this pass.
- N17 is an in-process ASGI run with a deterministic fake provider and notifier. The resource experiment uses an immediate fake extraction service. Neither establishes production deployment capacity or real OpenRouter/model latency.
- No commit, push, merge, or pull request was made. No PDF report was started.
