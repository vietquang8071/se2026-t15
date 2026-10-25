# AD-060 — bằng chứng và kế hoạch

Tất cả mã trong `scenario/` là mở rộng cá nhân, không phải implementation repository chính thức. Module gốc: `apps/api/src/prisma.service.ts`, `packages/database/` tại commit trong `evidence/snapshot.json`.

## Đã chạy

`python3 scenario/run-tests.py` chạy 11 unit/characterization và 6 integration/fault tests. Kết quả và thời gian thực nằm ở `evidence/test-results.json`, raw output ở `evidence/test-output.txt`. Container PostgreSQL dùng dữ liệu tổng hợp, không mount volume, không mở port host, tự xóa khi dừng.

- So before/after: kết quả đầy đủ, status/code, thứ tự đọc quyền/ghi và số dòng đã lưu; input sai vẫn được kiểm trước quyền.
- Mapping milliseconds → seconds, giữ text/null speaker; từ chối version sai/đoạn sai/quá số lượng.
- API harness HTTP trực tiếp: quyền sai 403, canonical payload sai 400; hai request đồng thời 201/200, một revision; cùng khóa khác nội dung 409, dữ liệu cũ còn nguyên.
- Repository transaction kiểm quyền lại, chặn actor giả ngay tại hàm store.
- Gateway treo giả lập: timeout test 50 ms; 202 PENDING không là hoàn tất nghiệp vụ; GET minutes trả fixture. Khi fake gateway phục hồi, retry không ghi trùng.
- Retention fake clock: đúng biên 70 ngày, xử lý cả reference job pending trên bản sao, không xóa dữ liệu thật.

Giới hạn: HTTP server dùng Node chuẩn để kiểm contract, chưa phải NestJS. Header `x-test-user` chỉ cho harness, không phải auth. Minutes là seed fixture; job map trong RAM. SQL function là minh họa constraint/transaction, chưa phải Prisma migration của sản phẩm. Mã `pg-repository.ts` gọi psql chỉ là test bridge; production dùng Prisma và parameters. Không khẳng định vendor thật/LLM/production hoạt động.

## Planned — staging trước rollout

| Test | Chuẩn bị/thao tác | Kết quả mong đợi |
|---|---|---|
| T-AV | API/DB còn chạy, dừng gateway process; gọi core GET với user hợp lệ; khởi tạo import | Core GET trả đủ biên bản; import PENDING có mã lỗi; không dữ liệu thiếu |
| T-CON | Gateway N và N−1 nhận fixture vendor v1; canonical API nhận cả hai | Cùng mapping/unit/ID/error contract; version không hỗ trợ bị từ chối |
| T-INV | Nest auth token thật; gọi trực tiếp API với user khác, concurrent retry, mất response sau commit | 403; unique key giữ một revision, replay 200; changed body 409 |
| T-DEP | Lint domain chỉ import canonical/port; kiểm environment và DB role | Không SDK/vendor DTO/Prisma; gateway không có credentials DB |
| T-RB | Seed data từ N−1; migrate additive; deploy N, tạo revision/job; ngắt call, tắt nguồn mới, drain ≤2s, quay image/config N−1 | GET core và write mới còn hoạt động; N−1 đọc revision/job của N; in-flight retry đúng một revision; không restore/xóa dữ liệu |
| T-LEASE | Dừng worker giữa lấy kết quả và commit; lease hết hạn; chạy lại từ worker khác | PENDING không mất; fencing/attempt token ngăn worker cũ cập nhật job; revision/job commit cùng transaction |
| T-RET | DB tạm + fake clock 69 ngày, 70 ngày−1ms, 70 ngày, 70 ngày+1ms | Cảnh báo pending; chuyển EXPIRED; purge log/reference; giữ dữ liệu nghiệp vụ theo policy riêng và key gắn revision |
| T-CR | Ghi thời điểm nhận CR, phân loại vendor/schema/rollback, chỉ định người phản hồi | Phản hồi có đánh giá tác động trong 22 giờ; không coi đây là deadline triển khai |

Timeout production đề xuất: gateway→vendor 1.5 s, API→gateway 2 s. Gateway phải hủy call bằng AbortSignal/budget, tránh công việc mồ côi. Sample Promise.race chỉ minh họa quan sát timeout, không chứng minh remote call bị hủy.

Retry production do API quyết định: tối đa 3 attempts/job, backoff 1s và 2s+jitter, giữ khóa; không retry input/version/quyền. Không có queue/event bus hoặc exactly-once assumption. Persist job + lease là debt phải trả trước khi triển khai thật.

## Planned — tải 709 đồng thời

- Môi trường dự kiến: staging 8 vCPU/16 GiB cho hệ thống (giả định), load generator riêng; phải ghi số instance/image/DB pool/config thực trước chạy.
- Seed 100 biên bản tổng hợp ~100 KiB/bản, đủ dữ liệu import hợp lệ; không dữ liệu cá nhân.
- 709 virtual users vòng kín, think time 1 s; 90% GET minutes, 10% submit/fetch import, report concurrency thực; không suy từ đồng thời thành RPS.
- Warm-up 2 phút; đo 10 phút; dừng gateway phút 3–8, sau đó phục hồi. Không gọi vendor thật hoặc endpoint production.
- Core-read availability: numerator = số GET hợp lệ trả 200 và nội dung đúng; denominator = toàn bộ GET hợp lệ được phát trong cửa sổ fault, gồm 5xx, timeout, incomplete. Đề xuất ≥99%, chưa đo.
- p95 core read: end-to-end từ lúc client phát request đến nhận đủ JSON hợp lệ. Nearest rank: `sorted_latencies[ceil(.95*n)-1]`. Báo riêng p95 thành công và success/total; mục tiêu ≤5.0 s. Timeout không được biến thành response thành công nhanh; denominator giữ mọi request hợp lệ. Báo số request còn pending khi đóng cửa sổ và chờ đến client deadline để phân loại.
- Import: ghi ACK latency, queue/job age và completion latency riêng. 202 PENDING không được tính là completed import hoặc suy ra nghiệp vụ hoàn tất ≤5s.
- Lưu raw latency, status, request/job key, số retry, thời điểm inject/recover và kiểm nội dung; không log transcript body. Chưa có kết quả latency/load hoặc RTO được xác nhận.

## Contract và dữ liệu

Vendor giả định V-Transcript `v1` được map sang `TranscriptInput 1.0`. `external_id` là JSON string của cặp `[document, revision]`; namespace `source_id` lấy từ cấu hình adapter tin cậy. Khóa DB `(meeting_id, source_id, external_id)`. Gateway chỉ trả canonical input cho API, không có quyền ghi DB. API resolve meeting/actor từ context được xác thực; không tin meeting/vendor identity do client tự gửi mà không kiểm ownership.

Phiên bản minor chỉ thêm optional field khi consumer compatibility được kiểm chứng; breaking change dùng `/v2`. Sample validator cho phép unknown field và chỉ persist trường canonical được sử dụng; cần thống nhất strictness với API contract nhóm trước production. Trước khi chuyển transcript cho LLM phải bổ sung duration/order/metadata đầy đủ theo tài liệu LLM; sample này chỉ chứng minh import revision, không thực hiện extraction.
