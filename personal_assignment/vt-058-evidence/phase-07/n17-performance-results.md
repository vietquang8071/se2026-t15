# N17 — 200 Concurrent HTTP Extraction Results

## Workload and method

- One process and one asyncio event loop ran an 8-request warm-up followed by two independent measured batches of exactly 200 requests each.
- Every measured request used the same 732-byte compact JSON payload shape from `tests/fixtures/requests/summary_actions_request.json`; request IDs and meeting IDs were unique and mapped one-to-one.
- An async client gate released scheduled request tasks together. An ASGI arrival gate held requests until all 200 reached the application; each measured run observed 200 arrivals and 200 maximum active requests.
- The actual FastAPI application handled authentication, request parsing and validation, the verified extraction service, response model validation, and completion background tasks. The fake provider chose candidate or verifier output from the current prompt and used no shared sequential response queue. The fake notifier recorded dispatch and completion timestamps.
- Start was `time.perf_counter_ns()` immediately before each `AsyncClient.post`. End was recorded immediately after the final `http.response.body` ASGI send (`more_body=false`) completed. The response recorder supported multiple body frames.
- Percentiles use nearest rank: sorted latency at index `ceil(p*n)-1`. Latency includes client invocation, ASGI processing, validation, extraction, and response body delivery, but excludes later notification work.

## Command and environment

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python tests/manual/vt058_phase07_benchmark.py --mode n17
```

Python 3.12.3; Linux `6.17.0-40-generic-x86_64`, glibc 2.39. The script used the existing `apps/llm-service/.venv` interpreter. The warm-up batch contained 8 requests and was excluded from the measured results.

## Measured batches

| Run | Requests / concurrency | p50 (ms) | p95 (ms) | p99 (ms) | Max (ms) | Throughput (responses/s) | Duration (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Run 1 | 200 / 200 | 409.489 | 713.887 | 754.766 | 765.433 | 235.47 | 0.849 |
| Run 2 | 200 / 200 | 413.728 | 775.812 | 805.787 | 812.890 | 222.04 | 0.901 |

Each batch produced 200 successful HTTP 200 responses, zero failed HTTP responses, zero request exceptions, and a 0% HTTP error rate. All 200 responses in each batch passed `ExtractionResponse` validation and preserved the expected request-ID/meeting-ID association. The response recorder found a terminal response-body frame for every request.

Each measured run recorded 200 notification dispatch attempts and 200 successful notifier completions. All events passed the allowlisted event and identity checks. Notification processing latency was p50/p95/p99/max 0.002/0.004/0.006/0.009 ms in Run 1 and 0.002/0.005/0.007/0.008 ms in Run 2. All 200 notifications in each run finished after their corresponding response-body frame. `AsyncClient.post()` returned after the ASGI body timestamp as well (Run 1 p50/p95/p99/max 0.433/0.777/1.052/1.114 ms later; Run 2 0.448/0.941/1.324/1.700 ms later), so its return time was not used as the HTTP response endpoint.

The fake provider handled 408 candidate and 408 verifier calls across the warm-up and both measured runs. No external provider call was made.

## Target and interpretation

The worst measured batch p95 was **775.812 ms (0.776 s)**, below the **5.0-second** target. Result: **PASS for this controlled offline workload**.

This is an in-process ASGI experiment with a deterministic fake provider and notifier. It is not a production deployment, network-server benchmark, or performance guarantee for OpenRouter or real model inference. It also does not model production process scheduling, provider latency, or external notification latency.
