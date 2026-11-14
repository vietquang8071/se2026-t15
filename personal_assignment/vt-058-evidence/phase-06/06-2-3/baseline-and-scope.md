# Phase 06.2–06.3 — Baseline and Scope Evidence

## Repository baseline

- Branch: `feature/vt-058-llm-notification`.
- Starting HEAD: `a0a4ea40ce54193d694ce488f6319644b51d4c42` — matches the expected Phase 06 baseline.
- Initial `git diff --check`: exit 0.
- Initial status contained only the intentionally uncommitted Phase 06.1 work:

  ```text
   M apps/llm-service/tests/integration/test_runtime.py
   M apps/llm-service/tests/integration/test_verified_extraction_service.py
  ?? apps/llm-service/tests/integration/test_pairwise_completion_notification.py
  ?? personal_assignment/vt-058-evidence/phase-06/06-1/ai-usage-log.md
  ?? personal_assignment/vt-058-evidence/phase-06/06-1/baseline.md
  ?? personal_assignment/vt-058-evidence/phase-06/06-1/boundary-and-negative-tests.md
  ?? personal_assignment/vt-058-evidence/phase-06/06-1/pairwise-execution.md
  ?? personal_assignment/vt-058-evidence/phase-06/06-1/test-quality-review.md
  ```

- No unexpected changes were present. `apps/llm-service/app/core/middleware.py` had no Git status entry.
- Phase 06.2–06.3 evidence directory did not exist before this milestone.

## Original-source N12/N13 run

Run started `2026-11-14 15:51:26 UTC` from `apps/llm-service` using the existing no-sync locked environment:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync --locked --extra test \
  pytest -q -p no:cacheprovider \
  tests/integration/test_runtime.py -k 'n12 or n13' -vv
```

Exit 0:

```text
tests/integration/test_runtime.py::test_n12_declared_content_length_accepts_exact_utf8_limit PASSED [ 50%]
tests/integration/test_runtime.py::test_n13_streamed_body_accepts_exact_utf8_limit PASSED [100%]
======================= 2 passed, 25 deselected in 0.95s =======================
```

## Source checksum and snapshots

The original repository middleware SHA-256 before mutation was:

```text
299f7cfd050a2114a5eae471d2f8f5bb5c50ba1311ef690613f1d4a82ef84a01  apps/llm-service/app/core/middleware.py
```

A read-only Phase 06.1 snapshot of the three test files was saved outside the repository at:

`/tmp/vt058-phase0623.J3ztKe/phase061-baseline/`

Snapshot checksums:

```text
dc0ff69562f2f7f18250b9d98e443be0da6309a9c5d63dadafcc813f8ea7fd64  apps/llm-service/tests/integration/test_runtime.py
294eec6ee705546bf14fc560af72cbfcb226257eed1854697e20444739bb88b8  apps/llm-service/tests/integration/test_verified_extraction_service.py
63626c64dd23e925fe3ce6901af6558babae4dde8442f4c7d703fe231981bdc1  apps/llm-service/tests/integration/test_pairwise_completion_notification.py
```

The isolated service copy is at `/tmp/vt058-phase0623.J3ztKe/mutant/`. It was copied from the current service tree and excludes `.git`, `.venv`, `.env` files, bytecode, and test/tool caches. It contains the uncommitted Phase 06.1 tests, application code, fixtures, and service configuration. No dependency installation or synchronization was performed.

The existing service virtual environment's Python 3.12.3 and pytest 8.4.2 were used to execute tests from the isolated copy, with `PYTHONPATH=.`. The isolated original middleware checksum matched the repository checksum. Its baseline N12/N13 run exited 0: **2 passed, 25 deselected in 0.99s**.

## Scope status at the human checkpoint

No repository application source or test file was edited during Phase 06.2. The only repository additions so far are this and the two companion evidence documents under the authorized Phase 06.2–06.3 directory. The Phase 06.1 test snapshot remains available for comparison after the developer's manual corrections. The final regression, coverage instrumentation, flaky-test repeat runs, and remaining three evidence files are pending the human checkpoint and subsequent validation.
