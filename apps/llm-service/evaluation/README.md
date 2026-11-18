# LLM-03.7 Offline Evaluation

This tool validates the immutable synthetic dataset and scores saved `ExtractionResponse` Contract v1 JSON. It does not call HTTP endpoints, OpenRouter, or any model. Offline is the default and works without `LLM_SERVICE_TOKEN` or provider credentials.

Run commands from `apps/llm-service`.

## Validate the dataset

```bash
uv run --locked --extra test python -m evaluation.runner validate-dataset
```

Validation checks the manifest and case split counts, the 3 required files per case, Pydantic `ExtractionRequest`, Audio Transcript v2 structure, Audio-to-LLM field preservation, and gold source/temporal consistency. Invalid data returns exit status `2` and prints case-specific findings. The validator never rewrites dataset files.

## Offline reports

Each response file must be named `<case-id>.json` and contain the saved public `ExtractionResponse` JSON body. Missing files are `not_evaluated`; invalid JSON, schema, or request relationship are failures and are never interpreted as empty extraction output.

Run an offline dry run with no saved responses:

```bash
uv run --locked --extra test python -m evaluation.runner run \
  --output-dir /tmp/llm03.7-dry-run
```

Evaluate one case:

```bash
uv run --locked --extra test python -m evaluation.runner run \
  --responses-dir /path/to/saved-responses \
  --case case-001 \
  --output-dir /tmp/llm03.7-case-001
```

Evaluate the development split:

```bash
uv run --locked --extra test python -m evaluation.runner run \
  --responses-dir /path/to/saved-responses \
  --split development \
  --output-dir /tmp/llm03.7-development
```

Evaluate the holdout split using previously saved responses:

```bash
uv run --locked --extra test python -m evaluation.runner run \
  --responses-dir /path/to/saved-responses \
  --split holdout \
  --output-dir /tmp/llm03.7-holdout
```

Every run writes `report.json` and `report.md` into its output directory. Keep output outside `evaluation/datasets/llm-03.7-evaluation/`. Exit status `0` means the dataset was valid and no provided response failed validation; status `1` indicates one or more response failures; status `2` indicates an invalid dataset; status `3` indicates rejected live authorization or review input.

Exit-code precedence is deterministic: live mode is rejected with `3` before dataset loading; otherwise dataset failure returns `2`; invalid review input returns `3` before a report is written; response validation failures return `1` after a report is written; successful offline evaluation returns `0`. A review attached to an unknown case, a case without a valid saved response, or a response claim that does not exist is invalid input. A valid but incomplete review is accepted and remains pending/partial.

## Human review annotations

Automatic Action Item matches use only deterministic exact task normalization. A paraphrase or competing unmatched prediction/gold pair remains `needs_manual_review`; it does not affect finalized precision/recall/F1 until a reviewer decides the pair. Use explicit decisions in an optional JSON review file:

```json
{
  "cases": {
    "case-001": {
      "action_matches": [
        {
          "prediction_id": "ACT-001",
          "gold_id": "GOLD-ACT-001",
          "decision": "match",
          "reviewer": "reviewer-a"
        }
      ],
      "summary_review": {
        "faithfulness": 4,
        "required_fact_coverage": 0.8,
        "conciseness_actionability": 4,
        "semantic_source_grounding": 0.75,
        "hallucination_count": 1,
        "hallucinations": ["Nêu thêm một mốc thời gian không có trong transcript."],
        "reviewer": "reviewer-a",
        "reviewer_scores": [],
        "adjudication": null
      },
      "semantic_grounding": {
        "reviewer": "reviewer-a",
        "claims": [
          {"claim_id": "actions[0].task", "verdict": "supported"},
          {"claim_id": "summary.overview", "verdict": "unsupported"}
        ]
      }
    }
  }
}
```

For a confirmed non-match, use `"decision": "not_match"`; it allows that prediction and gold action to be counted separately as FP and FN. Match decisions are enforced one-to-one. Summary scores are accepted only in the rubric ranges; reviewer and adjudication records are preserved. A review file is data, never a prompt to a model.

Semantic grounding IDs are generated from the **saved public response**, after production filtering: `summary.overview`, `summary.key_topics[0]`, `actions[0].task`, and non-null fields such as `actions[0].owner`, `actions[0].raw_due_expression`, `actions[0].priority`, and `actions[0].context`. Action indexes follow the public `modules.action_items` order and do not reuse internal candidate indexes. Null optional fields do not create claims. An empty requested `action_items` array has the explicit `actions.absence` claim so a reviewer can verify that no qualifying commitment was omitted. The resolved `due_date` is scored as a deterministic temporal attribute; source claim review follows the production verifier's raw-expression claim identity.

Semantic review status is `pending_review` when no claim has been reviewed, `partial_review` when at least one required claim remains pending, and `reviewed` only when every expected claim in that response has a valid verdict. Reports retain expected/reviewed/pending counts and coverage. Partial reviews may expose `provisional_accuracy`; final `accuracy` remains null until all expected claims are reviewed. Across cases, the aggregate accuracy also remains null while any evaluated claim is pending. A valid partial review does not fail the CLI.

## Metrics and interpretation

- Contract parsing and request relationship checks reuse `ExtractionResponse` and `validate_response_for_request`; evaluation also checks response timestamps against the cited source segment start.
- Structural grounding means IDs exist, the lists are unique/ordered, temporal sources are valid subsets, and timestamp derivation is consistent. It does **not** assert that the source text semantically supports a claim.
- Semantic source grounding and Summary quality remain `pending_review` until the review file contains human annotations.
- Exact normalized task text can establish a deterministic match; non-exact Vietnamese paraphrases require review. If a match decision is unresolved, action precision, recall, and F1 remain null.
- Correct empty-action cases are reported separately and do not add true positives. Undefined precision/recall/F1 are null.
- Owner, raw deadline, resolved date, temporal status and priority are scored only for matched actions. Null-owner/deadline/priority rates use their own denominators.
- Gold raw deadline expressions are compared verbatim except harmless edge punctuation. Relative Vietnamese dates remain unresolved under LLM-03; full relative-date resolution belongs to LLM-04.
- Model/provider, prompt versions, latency and token usage are reported when present in the saved response. HTTP status and attempt count are unavailable for bare response JSON. Estimated and billed costs remain unavailable because this runner does not invent prices or infer zero cost from missing usage.
- The 16 synthetic cases are a small diagnostic dataset; development and holdout are always labeled separately. Human labels remain a dependency for semantic quality results.

## Future live mode status

Live execution is fail-closed and is not implemented in this milestone. There is no provider client in the runner. Even an authorized invocation is refused because current provider prices have not been revalidated and reliable pre-request cost enforcement is unavailable. A future milestone must supply explicit operator acknowledgment, a positive per-run spending limit, a positive case limit, current verified pricing, and a real enforcement mechanism before any HTTP integration is enabled. No retries or concurrency are performed by this offline runner.

## LLM-03.7.2 manual DeepSeek evaluation

`evaluation.deepseek_runner` is separate from `evaluation.runner`. The existing offline evaluator remains offline and its `--mode live` option remains fail-closed. The new runner's default command is a network-free preflight; it never calls OpenRouter directly. Its only live destination is the authenticated local `POST /v1/extractions` endpoint.

### Prerequisites and preflight

Configure the service's local `.env` with `LLM_SERVICE_TOKEN`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL=deepseek/deepseek-v4.1-flash-1017`, `OPENROUTER_STRUCTURED_OUTPUT_MODE=json_object`, `OPENROUTER_MAX_OUTPUT_TOKENS` of at least `4096`, `OPENROUTER_REQUIRE_PARAMETERS=true`, `LLM_SERVICE_PROVIDER_TIMEOUT_SECONDS`, and `LLM_SERVICE_REQUEST_TIMEOUT_SECONDS` long enough to cover the two bounded provider stages. The runner requires an exact model ID match and does not provide a model override. Do not print or commit `.env` values.

In terminal 1, start the existing service with that same `.env`:

```bash
uv run --locked --env-file .env uvicorn app.main:app \
  --host 127.0.0.1 --port 8000
```

In terminal 2, run preflight. `uv --env-file` loads local settings into the process; preflight validates the 16-case dataset, runtime settings, local endpoint shape, model ID, JSON mode and timeouts. It makes no HTTP request:

```bash
uv run --locked --extra test --env-file .env \
  python -m evaluation.deepseek_runner
```

Preflight cannot inspect the settings of an already running server or verify an OpenRouter account spending cap. Start the service with the same `.env`; compare the returned model ID after a smoke call. Model support and prices vary by provider endpoint, and the public Contract v1 response does not expose the selected upstream provider route or billed cost.

### Smoke authorization

Do not run this command until the repository owner separately approves the exact model, one smoke case, a positive spending amount, current provider pricing/route and an account-level spending restriction. The proposed `$0.25` is not an approved limit and is not a default. Set `APPROVED_SMOKE_LIMIT_USD` only after approval. The command accepts only `case-001` and requires the distinct `--authorize-smoke` flag:

```bash
uv run --locked --extra test --env-file .env \
  python -m evaluation.deepseek_runner smoke \
  --authorize-smoke \
  --max-cases 1 \
  --spend-limit-usd "$APPROVED_SMOKE_LIMIT_USD" \
  --confirm-account-spending-limit \
  --output-dir /tmp/llm03.7.2
```

The runner sends only the selected `llm-request.json`, unchanged in business content; it never sends `gold.json` or review annotations. It uses the service bearer token, finite request timeout, one sequential request, no retries, and no redirects or environment proxies. Response and failure files are written exclusively so existing files are not overwritten. An invalid Contract v1 response is written as a sanitized failure record, not as a successful response.

### Development authorization

Run the development split only after a successful same-configuration smoke record exists in `/tmp/llm03.7.2` and the owner separately authorizes the development run. This command uses a different required flag and a separately supplied spending authorization. It is limited to `case-001` through `case-010`; any holdout or unknown ID is rejected. A matching saved smoke response for `case-001` is reused. A config mismatch stops the run without overwriting or paying for `case-001` again.

```bash
uv run --locked --extra test --env-file .env \
  python -m evaluation.deepseek_runner development \
  --authorize-development \
  --max-cases 10 \
  --spend-limit-usd "$APPROVED_DEVELOPMENT_LIMIT_USD" \
  --confirm-account-spending-limit \
  --output-dir /tmp/llm03.7.2
```

There is no automatic retry or concurrency. A failed request stops the run because a failed HTTP call may still have incurred provider cost. The runner requires the operator to confirm an account-level spending cap; this is an operator assertion and is not independently verified or enforced by the runner. The supplied run limit and request count are not hard monetary caps. When selected route pricing or actual billing is unavailable, estimated and billed cost remain `null`, never zero.

### Output and offline scoring

The output directory is outside the immutable dataset:

```text
/tmp/llm03.7.2/
├── responses/<case-id>.json
├── failures/<case-id>.json
├── metadata/<case-id>.json
├── metadata/smoke.json
├── metadata/development.json
├── reviews/review-template-smoke.json
├── reviews/review-template-development.json
└── reports/{smoke,development}/report.{json,md}
```

The runner reuses the existing offline scorer after each manual run. It can also be invoked separately against saved responses:

```bash
uv run --locked --extra test python -m evaluation.runner run \
  --responses-dir /tmp/llm03.7.2/responses \
  --split development \
  --output-dir /tmp/llm03.7.2/reports/offline-development
```

The generated review template contains empty case annotations only. Reviewers must inspect task equivalence, source support, owner, deadline, priority, Summary faithfulness/coverage/actionability, and hallucinations themselves. Valid source IDs establish structural grounding only; no semantic scores or verdicts are generated automatically. Until people fill in the review file, these metrics remain `pending_review`.

### Troubleshooting

- `preflight failed`: confirm the same `.env` is passed to both processes, the selected model ID is exact, `json_object` and `require_parameters=true` are configured, and request timeout is at least twice the provider timeout.
- `Development requires a successful ... smoke run`: use the same output directory as the successful smoke run; do not copy only the response JSON because its run metadata and configuration fingerprint are needed.
- `Existing output will not be overwritten`: choose a new output directory or retain the existing record; the runner will not replace it.
- `case ... failed`: inspect the sanitized status/category in `failures/` and `metadata/`; the response body and credentials are not copied into failure logs. Resolve the cause, seek any required authorization again, and use a new output directory for an intentionally repeated request.
- `unexpected_model`: stop. The response model differs from the pinned candidate in local configuration; do not accept it as a DeepSeek result.
