# Bảng test cases VT-060

P: unit test provider với mock fetch; H: kiểm thử audio-service qua HTTP và PostgreSQL test, dùng provider giả. Các kết quả dựa trên các lần chạy đã lưu; bảng mô tả assertion thực tế, không xem việc tính p95 là assertion ngưỡng hiệu năng. P0: ưu tiên cao; P1: ưu tiên tiếp theo.

| ID | Requirement/Risk | Test Level | Preconditions/Input | Expected Result | Priority |
|---|---|---|---|---|---|
| TC-01 | AC-01 | P: unit | Mock 503 rồi 200 | Trả kết quả; 2 request, 2 beforeCall | P0 |
| TC-02 | AC-01 | P: unit | Mock 503 liên tục | PROVIDER_UNAVAILABLE sau 3 attempt | P0 |
| TC-03 | AC-02 | P: negative | Mock 401 hoặc quota 429 | Lỗi tương ứng; chỉ 1 call | P0 |
| TC-04 | AC-02 | H: negative | Job failed; attempts = 3; POST process | 409 JOB_RETRY_LIMIT; job failed, providerCalls = 0 | P0 |
| TC-05 | AC-03 | H: E2E audio | Upload, gửi 3 process cho cùng audio | Cùng job ID; job completed, 1 provider call; đọc transcript | P0 |
| TC-06 | AC-03 | H: concurrency | 40 POST đồng thời cùng asset | 40 response 202; cùng ID; DB có 1 job | P0 |
| TC-07 | AC-04 | H: DB failure | Asset uploaded, job queued; trigger chặn running và failed | Rollback start: job queued, asset uploaded; attempts/call = 0, transcript null | P0 |
| TC-08 | AC-04 | H: DB failure | Provider lỗi; trigger chặn cập nhật asset failed | Rollback failure: job running, asset processing; 1 call, transcript null | P0 |
| TC-09 | AC-05 | H: retry | Sau failure đã lưu checkpoint; sửa metadata và process lại | Job completed, attempts = 2; providerCalls giữ 1 | P0 |
| TC-10 | AC-05 | H: restart | Job running có checkpoint v2; restart service | Job completed; providerCalls giữ 1 | P0 |
| TC-11 | AC-04 | H: failure | Provider giả gọi beforeCall rồi ném lỗi | Job và asset failed; 1 call; transcript null | P0 |
| TC-12 | AC-02 | H: boundary | Job failed; attempts = 2; POST process | 202, cùng job ID ở queued; DB có 1 job | P0 |
| TC-13 | R-expiry | H: negative | Asset hết hạn; GET metadata, transcript, media, export | Các GET trả 410; cleanup xóa asset và file | P1 |
| TC-14 | R-delete | H: cancellation | Provider đang đợi; gửi DELETE | DELETE 204; transcript 404 và file không còn | P1 |
| TC-15 | AC-05 | H: negative | Job queued có checkpoint khác cấu hình | Job failed, JOB_CONFIGURATION_CHANGED; providerCalls = 0 | P1 |
| TC-16 | NFR-01 | H: concurrency | 40 asset độc lập; 40 POST đồng thời | 40 response 202; 40 job ID và DB mapping đúng; ghi latency | P1 |
| TC-17 | AC-01 | P: cancellation | Mock 503 và abort khi request đang chạy | Promise bị từ chối; 1 beforeCall | P1 |

TC-07 được thêm trước patch; TC-16 bổ sung workload. Các test khác đã có tại snapshot db34fa5. Các mức attempts=1, >3 và crash sau response trước checkpoint chưa được chứng minh bằng test riêng.

P: apps/audio/test/audio/media-provider.test.mjs; H: apps/audio/test/http/audio-http.test.mjs.
