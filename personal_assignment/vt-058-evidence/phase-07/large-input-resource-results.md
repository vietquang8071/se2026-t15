# Large-Input Latency and Memory Results

## Method

The same manual benchmark script used an immediate deterministic fake extraction service that returned a fixed, schema-valid response. Requests went through the real FastAPI HTTP boundary, size middleware, authentication, JSON parsing, request validation, response validation, and recording completion notifier. Each scenario used distinct IDs and compact UTF-8 JSON with ASCII padding in the existing transcript text field; actual byte length was checked to equal the target.

The configured maximum was **1,048,576 bytes**. Targets were 25% (262,144 bytes), 75% (786,432 bytes), and maximum minus 512 bytes (1,048,064 bytes). Each target ran at concurrency 1, 2, and 4. A fresh subprocess handled each of the nine scenarios, avoiding cross-scenario process high-water contamination. Percentiles use nearest rank (`sorted[ceil(p*n)-1]`). Each scenario returned HTTP 200 for every request, made the expected number of extraction calls and notification attempts, and had zero HTTP errors and zero response-contract failures.

Command:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python tests/manual/vt058_phase07_benchmark.py --mode large-input
```

Environment: Python 3.12.3; Linux `6.17.0-40-generic-x86_64`, glibc 2.39. The script ran the existing `apps/llm-service/.venv` interpreter. The matrix has no memory pass/fail threshold.

## Nine scenarios

| Actual bytes per request | Concurrency | HTTP statuses | p50 (ms) | p95 (ms) | p99 (ms) | Throughput (responses/s) | `ru_maxrss` after (KiB) | High-water increase (bytes) | `tracemalloc` peak increase (bytes) |
|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 262,144 | 1 | 200 (n=1) | 50.384 | 50.384 | 50.384 | 19.85 | 55,260 | 1,798,144 | 2,231,474 |
| 262,144 | 2 | 200 (n=2) | 53.588 | 67.266 | 67.266 | 29.73 | 57,060 | 2,379,776 | 2,251,489 |
| 262,144 | 4 | 200 (n=4) | 69.406 | 80.970 | 80.970 | 46.99 | 59,616 | 2,490,368 | 2,279,839 |
| 786,432 | 1 | 200 (n=1) | 53.692 | 53.692 | 53.692 | 18.62 | 60,892 | 4,595,712 | 6,425,778 |
| 786,432 | 2 | 200 (n=2) | 58.531 | 75.703 | 75.703 | 26.42 | 66,596 | 5,787,648 | 6,445,369 |
| 786,432 | 4 | 200 (n=4) | 68.810 | 85.696 | 85.696 | 44.38 | 74,216 | 6,422,528 | 6,474,221 |
| 1,048,064 | 1 | 200 (n=1) | 79.658 | 79.658 | 79.658 | 12.55 | 63,844 | 6,098,944 | 8,518,676 |
| 1,048,064 | 2 | 200 (n=2) | 58.521 | 80.932 | 80.932 | 24.71 | 71,300 | 7,471,104 | 8,538,666 |
| 1,048,064 | 4 | 200 (n=4) | 79.942 | 101.309 | 101.309 | 38.12 | 80,532 | 7,471,104 | 8,567,453 |

## Memory measurement and trends

`resource.getrusage(RUSAGE_SELF).ru_maxrss` is a process-level high-water mark. On this Linux platform its raw unit is KiB; the table reports the raw `ru_maxrss` after the request and the difference in normalized bytes between the pre-request and post-request high-water readings. The readings include interpreter and application memory, so the difference is an increase in the process high-water mark, not a standalone request allocation. Fresh processes keep the nine high-water readings independent.

`tracemalloc` reports Python allocations only, not native allocations or process RSS. Payload objects and bodies were constructed before tracing began; the reported peak increase is additional traced allocation from the request phase, not total memory occupied by the payload.

Latency generally rose with concurrency at a fixed payload size in these small samples. At concurrency 4, p95 rose from 80.970 ms for 256 KiB to 85.696 ms for 768 KiB and 101.309 ms near 1 MiB. The measured traced peak also rose with request size, from about 2.2 MB to about 8.6 MB. Process RSS high-water readings varied with interpreter/application baseline and should be interpreted alongside the reported deltas. These are descriptive results from a fake extraction service, not real LLM inference performance or a production capacity guarantee.
