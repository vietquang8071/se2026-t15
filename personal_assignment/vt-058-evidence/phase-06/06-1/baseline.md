# Phase 06.1 — Baseline Evidence

## Git baseline

- Repository: `vietquang8071/se2026-t15`.
- Branch: `feature/vt-058-llm-notification`.
- Starting HEAD: `a0a4ea40ce54193d694ce488f6319644b51d4c42`.
- Expected Phase 06 baseline: `a0a4ea40ce54193d694ce488f6319644b51d4c42` — verified.
- Reference branch: `feature/llm-03-provider-integration` (not checked out or changed).
- Initial `git status --short --untracked-files=all`: empty; no pre-existing tracked or untracked changes.
- Initial `git diff --check`: exit 0, no output.
- The Phase 05.2 implementation and evidence were present. The Phase 06.1 evidence directory did not exist, so there were no evidence files to overwrite.

The baseline checks were run before any Phase 06.1 test modifications. No Git state was changed.

## Environment

Tests ran from `apps/llm-service` using the existing locked environment. The pytest banner identified Linux, Python 3.12.3, pytest 8.4.2, pluggy 1.7.0, and the repository's `.venv`; the only listed plugin was anyio 4.15.1. `PYTHONDONTWRITEBYTECODE=1` and `-p no:cacheprovider` were used. No dependencies were installed or synchronized.

The first sandboxed invocation stopped before pytest because `uv` could not create a temporary lock file in its read-only cache. The same command was then run with the authorized command escalation; that execution used `--no-sync --locked` and completed. The sandbox failure is environment setup evidence, not a test failure.

## Pre-change full-suite run

Run started: `2026-11-14 15:20:08 UTC`.

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync --locked --extra test \
  pytest -q -p no:cacheprovider
```

Exit code: **0**.

```text
........................................................................ [ 12%]
........................................................................ [ 25%]
........................................................................ [ 38%]
........................................................................ [ 51%]
........................................................................ [ 64%]
........................................................................ [ 77%]
........................................................................ [ 90%]
.......................................................                  [100%]
559 passed in 4.46s
```

No pre-existing test failure was observed. The earlier Phase 05.2 record reported `559 passed in 4.86s`; that is historical comparison only. The fresh Phase 06.1 pre-change run independently recorded 559 passes in 4.46s.

## Baseline interpretation

This establishes that the existing LLM Service suite passed before Phase 06.1 tests were changed. It does not establish mutation-killing results, the 200-concurrent-task performance target, or large-input memory/latency measurements. Those were not run in this phase.
