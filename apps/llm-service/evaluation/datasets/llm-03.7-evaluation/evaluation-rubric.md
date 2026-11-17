# LLM-03.7 Evaluation Rubric — v1

## Scope and procedure

Score the completed `POST /v1/extractions` response for each case. First validate it against the repository's `ExtractionResponse` Contract v1 and `validate_response_for_request`; record non-200 errors and failure type rather than coercing failures into successes. Gold is evaluation-only.

### 1. API / Contract compliance

- Successful outputs must have `contract_version=1.0`, the correct request/meeting/revision IDs, both requested modules non-null and the other four modules null.
- Validate segment references, timestamps, metadata, owner/review fields and evidence/prompt versions.
- Report valid JSON, valid Contract v1, success, rejected unsupported evidence, and failure rates separately.

### 2. Action Item precision, recall and F1

- Match predictions to gold tasks **one-to-one** by meaning and deliverable, not by exact text. Log matching decisions and reviewer disagreements.
- TP: a gold action correctly identified as a distinct active commitment; FP: invented, duplicated, canceled, merely proposed, already completed or mis-scoped item; FN: missing qualifying gold action.
- Precision = TP/(TP+FP), Recall = TP/(TP+FN), F1 = 2PR/(P+R), with undefined denominators marked `N/A`.
- Zero-gold, zero-prediction cases count as **correct absence**; they do not artificially add true positives to F1. Report empty-case success separately.
- If extraction fails, mark action quality metrics for that request as not evaluable and include the failure in contract success rate.

### 3. Owner attribution

For each matched action, evaluate `owner` against gold independently. Only confirmed speaker→participant mappings or explicit named assignments support a person. Owner `null` can be correct. Penalize unsupported owner claims explicitly. Reassignment cases use **the final accepted assignment**, not an earlier canceled assignment.

### 4. Deadlines and temporal accuracy

- Compare `raw_due_expression` with a **verbatim supported span** of the transcript (allow harmless leading/trailing punctuation differences only, not invented normalized phrases).
- For present LLM-03 runtime, an ISO `YYYY-MM-DD` raw expression with supported evidence may resolve as `exact_date`; non-ISO natural-language deadlines should remain `unresolved`, with `due_date=null` and review state.
- Deadline correctness must not be conflated with LLM-04's eventual relative-date resolution. Report accuracy of raw phrase, `due_date` and status separately.

### 5. Evidence / source grounding

Check both (a) each referenced source ID exists in the matching request and (b) the cited segment **actually supports the full claim**, including owner, deadline, priority, and corrections. A valid ID alone is insufficient. Do not demand exact equality with gold source lists when another subset of segments demonstrably supports a claim; record equivalence reasoning.

### 6. Summary quality

Use the gold reference as a semantic anchor. Evaluate:

- **Faithfulness (1–5):** no unsupported factual assertions, no reversal of decisions/assignments.
- **Required-fact coverage (0–1):** fraction of substantive gold topics/facts correctly covered.
- **Actionability/conciseness (1–5):** understandable factual overview and useful main topics without unrelated padding.
- **Source grounding (0–1):** fraction of summary assertions with genuinely supporting source IDs.
- **Hallucination count:** unsupported specific claims or contradictions, including invented owners/dates.

Use at least two reviewers for ambiguous semantic cases if possible; record both scores and adjudication.

### 7. Operational metrics

Per request record `case_id`, model ID, provider route/parameters, extraction/evidence prompt versions, attempt count, both generation finish reasons, input/output tokens (if reported), start/end timestamps, wall time, response status, error type, and amount charged or estimated. **Two model generations are typical for a successful verified extraction.** Real price and availability must be checked at run time. Do not log keys, raw private transcripts, or full provider errors.

### 8. Reporting recommendations

Present per-model results by split and scenario (not only aggregate accuracy). Confidence claims must reflect the small sample. Development results support diagnosis; holdout is for a single final comparison. Do not present scripted verifier/fixture outcomes as evidence of real-model semantic accuracy.
