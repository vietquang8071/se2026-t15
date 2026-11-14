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

## Scope status at the initial human checkpoint

No repository application source or test file was edited during Phase 06.2. The only repository additions so far are this and the two companion evidence documents under the authorized Phase 06.2–06.3 directory. The Phase 06.1 test snapshot remains available for comparison after the developer's manual corrections. The final regression, coverage instrumentation, flaky-test repeat runs, and remaining three evidence files were pending at that checkpoint.

## Resumed validation after the developer checkpoint

The previous section records the state before the developer checkpoint. The developer subsequently confirmed that HC-01 and HC-02 were manually authored. The current committed baseline at resumption is:

- Branch: `feature/vt-058-llm-notification`.
- HEAD: `beae5161608cba48db81a10e892e5c743de55e10` (`mutation testing`). This is later than the original Phase 06 baseline `a0a4ea40ce54193d694ce488f6319644b51d4c42`; the current commit contains the committed Phase 06.1 tests and Phase 06.2 evidence.
- Initial working tree: only `test_runtime.py` and `test_pairwise_completion_notification.py` were modified. The diffs against HEAD match HC-01 and HC-02; no production source was changed.
- `git diff --check`: exit 0.
- Repository middleware SHA-256 before and after the resumed validation: `299f7cfd050a2114a5eae471d2f8f5bb5c50ba1311ef690613f1d4a82ef84a01`.

The current two test files were diffed both against HEAD and against the preserved Phase 06.1 snapshot at `/tmp/vt058-phase0623.J3ztKe/phase061-baseline/`. Those diffs contain exactly the two reported human changes: one shared `CountingExtractionService` for N12/N13 with separate instances, and an exact ordered PW01–PW21 identifier assertion. All N12/N13 behavioral assertions and all 21 pairwise rows remain present.

The corrected boundary tests were run from the repository at `2026-11-14 16:10:24 UTC` using the existing Python 3.12.3 / pytest 8.4.2 environment:

    PYTHONDONTWRITEBYTECODE=1 uv run --no-sync --locked --extra test pytest -q -p no:cacheprovider tests/integration/test_runtime.py -k 'n12 or n13' -vv

Exit code 0; **2 passed, 25 deselected**. The first sandboxed invocation could not create uv's temporary lock under the read-only cache; the same no-sync command then ran successfully with approved escalation. This was an environment launch failure, not a pytest failure.

The corrected pairwise module was run at `2026-11-14 16:10:39 UTC` with the equivalent no-sync uv command and `-vv`. Exit code 0; **22 passed**, comprising the coverage verifier and PW01–PW21. Every named row was reported PASS. The verified fixture boundary body is N = **1,587 UTF-8 bytes**; N+1 is **1,588 bytes**.

Post-HC mutation reruns, restoration checks, repeated timing-sensitive tests, focused regression, full suite, and coverage-tool availability are documented in the companion evidence files. No repository source or test file was changed during this resumed validation.
