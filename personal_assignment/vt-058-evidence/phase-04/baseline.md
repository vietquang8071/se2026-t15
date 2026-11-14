# Phase 04 Baseline and Characterization

## Git baseline

- Repository: `vietquang8071/se2026-t15`.
- Branch before test changes: `feature/vt-058-llm-notification`.
- HEAD before test changes: `5e54822fca535972ef9b10a7d39dfbabc7df4b3d`.
- HEAD subject: `fix(llm): correct owner reassignment and absence verification`.
- Expected baseline: `5e54822fca535972ef9b10a7d39dfbabc7df4b3d` — matched.
- Pre-change `git status --short --untracked-files=all`: no tracked changes; untracked `personal_assignment/vt-058.md` and Phase 02/03 evidence were present and left untouched.
- Pre-change `git diff --check`: exit 0, no output.
- `personal_assignment/vt-058-evidence/phase-04/` did not exist before this work; no evidence targets conflicted.

## Test environment

- Service directory: `apps/llm-service`.
- Invoked the locked, no-sync `uv` environment with `PYTHONDONTWRITEBYTECODE=1` and pytest cache disabled (`-p no:cacheprovider`). No dependencies were installed or updated.
- The traceback identifies the existing project environment as `.venv/lib/python3.12`; OS, exact Python patch version, and pytest version were not separately recorded.
- `tests/conftest.py` removes inherited `OPENROUTER_API_KEY` and blocks synchronous and asynchronous `httpx` transports. The characterization tests use an injected fake extraction service and made no provider call.

## Existing characterization tests

Run started at `2026-11-14 14:13:39 UTC`.

Exact command, from `apps/llm-service`:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync --locked --extra test \
  pytest -q -p no:cacheprovider \
  tests/integration/test_runtime.py::test_dependency_override_returns_typed_extraction_response \
  tests/integration/test_extraction_pipeline_boundary.py::test_invalid_injected_extraction_response_maps_to_error_envelope
```

Actual result: exit code `0`.

```text
..                                                                       [100%]
2 passed in 0.95s
```

The successful typed-response characterization and invalid injected-response error-envelope characterization both passed before N02 was changed. These results are baseline characterization evidence, not RED evidence.

## Baseline conclusion

The required branch and commit matched the assignment baseline. There were no unexplained tracked changes or pre-existing failures in the selected characterization tests. Existing untracked assignment documents were preserved.
