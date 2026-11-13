# Danh mục test VT-060

H = apps/audio/test/http/audio-http.test.mjs; P = apps/audio/test/audio/media-provider.test.mjs. Các test đã có được giữ nguyên, không nhận là test mới.

| ID | AC/Risk | Mức | Input và kỳ vọng | Ưu tiên | Test thực tế |
|---|---|---|---|---|---|
| TC-01 | AC-01 | Unit | 503 rồi 200, hai request | P0 | P: provider retries a temporary 503 |
| TC-02 | AC-01 | Unit | 503 ba lần, exhausted | P0 | P: transient errors retry at most three times |
| TC-03 | AC-02 | Unit negative | 401/quota, một call | P0 | P: provider auth/quota errors |
| TC-04 | AC-02 | HTTP negative | failed, attempts=3, 409, không call | P0 | H: job retry cap stops repeated paid processing |
| TC-05 | AC-03 | HTTP/E2E audio | upload/process ba lần, cùng ID, hoàn thành | P0 | H: process is idempotent |
| TC-06 | AC-03 | HTTP | 40 request cùng asset, một job | P0 | H: 40 concurrent process requests |
| TC-07 | AC-04 | DB failure | chặn running và failure; queued/uploaded rollback | P0 | H: starting a job rolls back |
| TC-08 | AC-04 | DB failure | chặn asset failed; cả ghi failure rollback | P0 | H: failure status updates roll back together |
| TC-09 | AC-05 | HTTP | checkpoint đã lưu, retry không gọi provider | P0 | H: retry reuses a persisted diarization checkpoint |
| TC-10 | AC-05 | HTTP | restart running, dùng checkpoint | P0 | H: startup recovers an interrupted v2 job |
| TC-11 | AC-04 | HTTP failure | provider lỗi, job và asset failed, transcript null | P0 | H: provider failure records failed job |
| TC-12 | AC-02 | HTTP boundary | attempts=2, requeue cùng ID | P0 | H: failed job with two attempts |
| TC-13 | R-expiry | HTTP negative | hết hạn, từ chối đọc và cleanup | P1 | H: expiry refuses transcript/media |
| TC-14 | R-delete | HTTP cancellation | xóa khi provider active, không khôi phục output | P1 | H: DELETE aborts active provider work |
| TC-15 | AC-05 | HTTP negative | checkpoint cấu hình khác bị từ chối | P1 | H: configuration changes never reuse checkpoints |
| TC-16 | NFR-01 | HTTP | 40 assets độc lập, 40 jobs, đo latency | P1 | H: 40 independent audio tasks |
| TC-17 | AC-01 | Unit negative | abort trong retry, không gọi thêm | P1 | P: cancellation interrupts retries |

Attempts=1, >3 và failure giữa provider response và checkpoint commit chưa có test tự động riêng; không báo là pass.
