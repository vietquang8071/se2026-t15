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
