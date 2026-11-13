# Performance: API acceptance

Môi trường: 14/11/2026, local Intel i5-13500H, 16 CPU logic, RAM 15 GiB, Node 25.8.2, pnpm 11.1.1, PostgreSQL 17 Alpine Docker, FFmpeg; synthetic WAV và provider giả. Client và server cùng máy. Harness là test HTTP; mỗi lượt tạo 40 audio qua upload tuần tự trước phép đo, phát đồng thời 40 POST process tới 40 asset khác nhau, đo performance.now() từ trước fetch đến sau đọc JSON. Worker có thể chạy trong lúc đo; không đo queue wait hay completion.

Nearest-rank: sort 40 mẫu, p95 = phần tử thứ ceil(0,95×40) = 38. Từng log lưu đủ 40 mẫu; thời gian total là từ phát batch đến khi đọc đủ response, không gồm upload. Một warm-up và ba lượt độc lập, mỗi lượt tạo database test mới, vì vậy warm-up không làm ấm cùng tiến trình/DB của các lượt sau.

| Lượt | HTTP 202 | Job DB | min ms | p50 ms | p95 ms | p99 ms | max ms | batch ms | p95 ≤ 1500 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| warmup | 40/40 | 40 | 75.43 | 201.39 | 248.80 | 249.69 | 249.69 | 262.85 | PASS |
| run1 | 40/40 | 40 | 90.19 | 260.46 | 366.80 | 368.65 | 368.65 | 376.79 | PASS |
| run2 | 40/40 | 40 | 73.47 | 274.45 | 316.95 | 317.58 | 317.58 | 323.00 | PASS |
| run3 | 40/40 | 40 | 75.45 | 206.16 | 248.08 | 248.29 | 248.29 | 258.72 | PASS |

Các lượt đo độc lập 40/40, 40 job ID khác nhau và mapping asset/job khớp; p95 từng lượt dưới 1500 ms: PASS cho API acceptance local. Dải p95 thay đổi giữa các lượt, ba mẫu tổng thể chưa phản ánh tail production. Raw [warmup](evidence/performance/warmup.log), [run1](evidence/performance/run1.log), [run2](evidence/performance/run2.log), [run3](evidence/performance/run3.log), thời gian và exit code [metadata](evidence/repeated-runs.json).

Scenario A đo 40 request cùng một asset: [regression cũ](evidence/regression-http.log) 40 thành công, một job, p95 289,44 ms; scenario B [lượt cũ](evidence/independent.log) 40 job, p95 200,75 ms. Không gộp hai loại workload. Fake provider không đại diện latency OpenAI; một máy và một worker tuần tự không chứng minh 40 phiên âm chạy đồng thời, cũng không chứng minh p95 hoàn thành hoặc production.
