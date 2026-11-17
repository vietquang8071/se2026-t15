# SE2026-T15 — LLM-03.7 Synthetic Evaluation Dataset (v1.0.0)

This dataset contains **16 fully synthetic Vietnamese meeting scenarios**: 10 development cases (`case-001`–`case-010`) and 6 holdout cases (`case-011`–`case-016`). It has **not** been transcribed from recordings and does not establish real ASR accuracy.

Each case contains:

- `audio-transcript-v2.json`: the Audio Service's segment-level `AudioTranscriptV2` JSON shape, preserving `schema_version=2`, source timeline, speaker labels, transcript text, warnings, and model metadata. The `models` value is a **shape-compatible fixture constant**, not evidence that the OpenAI provider was called.
- `llm-request.json`: a valid `ExtractionRequest` Contract v1 payload for `POST /v1/extractions`. Both requested modules are `meeting_summary` and `action_items`, including in cases where no actions should be found.
- `gold.json`: **evaluation-only** human-reviewable reference summary and Action Items; this is deliberately not a production `ExtractionResponse` or `SummaryActionsCandidate`.

## Data alignment

- Audio `segments[].id`, `start`, `end`, and `text` are retained exactly in LLM input.
- Audio `segments[].speaker` becomes LLM `speaker_id`, except literal `unknown` becomes `null`.
- `duration_sec` becomes `meeting.duration_seconds`.
- `timeline=source`; source MP4 offset, when present, is **already included** in segment times and must not be added a second time.
- `participants` in LLM input are manually verified fixture metadata, **never inferred from speaker label strings**. An unverified mapping may remain empty.
- `title`, `anchor_date`, `timezone`, `request_id`, and `revision_id` are fixture App-context metadata, not fields supplied by Audio Service.
- Segment IDs are case-local; always scope a source ID by `meeting.id` and `transcript.revision_id`.

## Gold interpretation

- `meeting_summary.reference_overview` is a semantic reference, **not an exact expected string**. `key_topics` and `source_segment_ids` support grounding checks. `forbidden_claims` identify mistakes to penalize.
- `action_items` contains all qualifying **distinct, active commitments** at the end of the conversation (not suggestions, already-completed work, or superseded assignments). Every action has its own evidence sources.
- Raw deadlines reproduce a verbatim substring of a transcript segment. `due_date_resolution_status` reflects **current LLM-03 behavior**, not the eventual LLM-04 temporal resolver: only canonical ISO `YYYY-MM-DD` expressions can resolve to `exact_date`; natural-language phrases are `unresolved` with `due_date=null`.
- `gold.json` is not provided to the model or to the evidence verifier. It is used only by the evaluation process after inference.
- The test case author's annotations should receive independent human review before interpreting benchmark numbers as reliable labels.

## Coverage highlights

Clear commitments; multiple actions; no action items; unknown speaker attribution; accepted requests; owner reassignment; corrected deadlines; ISO dates and explicit priority; overlapping speech; conditional ideas; pending decisions; prompt injection; named assignment by unknown speaker; vague deadlines; mixed-topic meetings.

## Split and cost discipline

Use the 10 development cases for debugging prompts/evaluation infrastructure. **Lock the six holdout cases** for an unbiased final comparison; do not iteratively tune the system on holdout failures. With 6 holdout samples, findings are exploratory rather than statistically robust.

This archive **does not include** live OpenRouter calls, provider credentials, benchmark execution code, any changes to the repository, or audio recordings. The overall LLM budget discussed is $2; the proposed $0.50 limit for LLM-03.7 is **not yet an approved spending authorization**.

## How to use

1. Review gold labels, case coverage, and consistency.
2. Validate each `llm-request.json` with the repository's `app.schemas.request.ExtractionRequest.model_validate_json` in a local environment (requires project's dependencies).
3. Use `llm-request.json` as the request payload for LLM-03.7; **do not send gold labels to the model**.
4. Save outputs and token/latency/cost logs outside the dataset, keyed by case ID and model/config version.
5. Score using `evaluation-rubric.md` and document any judgment calls.

## Source contracts inspected

- `apps/audio/src/audio/audio-types.ts`
- `apps/audio/src/audio/audio-transcript.ts`
- `docs/audio-service-api.md`
- `apps/llm-service/app/schemas/request.py`
- `apps/llm-service/app/schemas/response.py`
- `apps/llm-service/app/prompts/v1/summary_actions.md`
- `apps/llm-service/app/services/temporal_safeguards.py`
