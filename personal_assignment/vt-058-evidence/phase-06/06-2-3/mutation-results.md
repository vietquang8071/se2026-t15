# Phase 06.2 — Isolated Mutation Results

## Experiment boundary

Both mutants were applied only to `/tmp/vt058-phase0623.J3ztKe/mutant/app/core/middleware.py`. The repository's original `apps/llm-service/app/core/middleware.py` was never edited. Each experiment used one operator mutation at a time, the Phase 06.1 test snapshot, and the existing service Python environment.

Original middleware SHA-256, isolated baseline SHA-256, and final repository SHA-256 all matched:

```text
299f7cfd050a2114a5eae471d2f8f5bb5c50ba1311ef690613f1d4a82ef84a01
```

## M01 — Declared Content-Length comparison

Target in `ExtractionRequestBoundaryMiddleware.__call__`:

```python
if declared_length > self.max_request_bytes:
```

Only the isolated copy was changed to:

```python
if declared_length >= self.max_request_bytes:
```

The isolated diff contained exactly this single operator change; the accumulated streamed-byte comparison remained `>`.

N12 command, run from `/tmp/vt058-phase0623.J3ztKe/mutant`:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  /home/vitquay1708/Study_Space/SE/apps/llm-service/.venv/bin/python -m pytest \
  -q -p no:cacheprovider \
  tests/integration/test_runtime.py::test_n12_declared_content_length_accepts_exact_utf8_limit -vv
```

Mutant run started `2026-11-14 15:52:39 UTC`, exit **1**. The behavioral failure was:

```text
>       assert status == 200
E       assert 413 == 200
...
FAILED tests/integration/test_runtime.py::test_n12_declared_content_length_accepts_exact_utf8_limit
============================== 1 failed in 1.16s ===============================
```

This is a valid kill: N12 sends a structurally valid 1,587-byte body with Content-Length equal to the configured maximum, and the mutant rejects that exact boundary with 413.

The isolated source was restored by copying the saved baseline bytes. Both SHA-256 values were then `299f7cfd...ef84a01`. Restored N12 started `2026-11-14 15:52:50 UTC`, exit **0**: `1 passed in 1.22s`.

## M02 — Accumulated streamed-body comparison

Target in the same middleware method:

```python
if received_bytes > self.max_request_bytes:
```

Only the isolated copy was changed to:

```python
if received_bytes >= self.max_request_bytes:
```

The isolated diff contained exactly this single operator change; the declared Content-Length comparison remained `>`.

N13 command, run from `/tmp/vt058-phase0623.J3ztKe/mutant`:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  /home/vitquay1708/Study_Space/SE/apps/llm-service/.venv/bin/python -m pytest \
  -q -p no:cacheprovider \
  tests/integration/test_runtime.py::test_n13_streamed_body_accepts_exact_utf8_limit -vv
```

Mutant run started `2026-11-14 15:53:02 UTC`, exit **1**. The behavioral failure was:

```text
>       assert status == 200
E       assert 413 == 200
...
FAILED tests/integration/test_runtime.py::test_n13_streamed_body_accepts_exact_utf8_limit
============================== 1 failed in 1.12s ===============================
```

This is a valid kill: N13 sends the valid exact-limit body as two chunks without Content-Length, so the failure reaches the accumulated-byte comparison and rejects at exactly N.

The isolated source was restored from the baseline snapshot. Baseline, restored isolated copy, and repository source again all hashed to `299f7cfd...ef84a01`. Restored N13 started `2026-11-14 15:53:13 UTC`, exit **0**: `1 passed in 1.02s`.

## Summary

| Mutant | Target | Killing test | Original | Mutated | Restored | Verdict |
|---|---|---|---|---|---|---|
| M01 | Declared Content-Length `>` → `>=` | N12 | PASS | FAIL: exact N returned 413 | PASS; checksum matched | Killed |
| M02 | Accumulated bytes `>` → `>=` | N13 | PASS | FAIL: exact N returned 413 | PASS; checksum matched | Killed |

Mutation score for these two approved, non-equivalent mutants: **2/2 = 100%**. This score applies only to this experiment, not the full LLM Service. The repository production source remained byte-for-byte unchanged.

## Post-HC mutation confirmation

Because HC-01 refactored the N12/N13 fake setup, both approved mutants were rerun against a refreshed isolated copy containing the developer-corrected test files. The current repository test sources were copied into `/tmp/vt058-phase0623.J3ztKe/mutant`; all source mutations remained confined to that temporary copy. The isolated baseline and repository middleware hashes were both `299f7cfd050a2114a5eae471d2f8f5bb5c50ba1311ef690613f1d4a82ef84a01` before each mutation.

The isolated baseline N12/N13 command used the existing interpreter and returned exit 0: **2 passed, 25 deselected in 1.10s**.

### M01 after HC-01

Only the declared-length comparison in the temporary copy changed from `declared_length > self.max_request_bytes` to `declared_length >= self.max_request_bytes`. The diff contained this one operator change; the streamed-byte comparison remained unchanged.

    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /home/vitquay1708/Study_Space/SE/apps/llm-service/.venv/bin/python -m pytest -q -p no:cacheprovider tests/integration/test_runtime.py::test_n12_declared_content_length_accepts_exact_utf8_limit

The run at `2026-11-14 16:11:42 UTC` exited 1 with the behavioral assertion `assert status == 200`, observed `413 == 200`. This is the expected exact-boundary rejection, not an import, fixture, or environment error. The copy was restored from the preserved baseline; its hash returned to `299f7cfd...ef84a01`. Restored N12 at `16:11:54 UTC` exited 0: **1 passed in 1.18s**.

### M02 after HC-01

Only the accumulated-byte comparison in the temporary copy changed from `received_bytes > self.max_request_bytes` to `received_bytes >= self.max_request_bytes`. The declared-length comparison remained unchanged.

    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /home/vitquay1708/Study_Space/SE/apps/llm-service/.venv/bin/python -m pytest -q -p no:cacheprovider tests/integration/test_runtime.py::test_n13_streamed_body_accepts_exact_utf8_limit

The run at `2026-11-14 16:12:10 UTC` exited 1 with `assert status == 200`, observed `413 == 200`. The exact-size body was split into two chunks and carried no Content-Length, so it reached the streamed-byte check. The temporary copy was restored; its hash returned to `299f7cfd...ef84a01`. Restored N13 at `16:12:22 UTC` exited 0: **1 passed in 1.06s**.

The repository middleware hash was rechecked as `299f7cfd050a2114a5eae471d2f8f5bb5c50ba1311ef690613f1d4a82ef84a01`. Both mutants remain killed after HC-01; M01 and M02 are each original PASS / mutant FAIL / restored PASS. The scoped score remains **2/2 (100%)**, not a whole-service mutation score. No repository production source was modified.
