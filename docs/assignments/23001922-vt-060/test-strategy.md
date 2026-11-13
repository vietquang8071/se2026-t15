# Chiến lược kiểm thử theo rủi ro

| ID | Rủi ro | Khả năng | Tác động | Ưu tiên | Kiểm soát và test |
|---|---|---|---|---|---|
| R1 | Partial DB write | Trung bình | Cao | P0 | Transaction, TC-07/08/11 |
| R2 | Job/transcript lặp khi request trùng | Trung bình | Cao | P0 | Unique, row lock, TC-05/06 |
| R3 | Retry sai loại hoặc quá budget | Trung bình | Cao | P0 | Giới hạn, TC-02/03/04/12 |
| R4 | Mất hoặc reuse checkpoint sai | Trung bình | Cao | P0 | TC-09/10/15; cửa sổ crash còn lại |
| R5 | Đồng thời process/delete | Trung bình | Cao | P1 | Row lock, abort, TC-14; chưa chứng minh mọi lịch xen kẽ |
| R6 | Restart hoặc cancellation | Trung bình | Cao | P1 | TC-10/14/17 |
| R7 | Provider thành công rồi persist thất bại | Thấp | Cao | P1 | Chưa test crash đúng cửa sổ |

Unit Node test runner dùng mock fetch cho retry/classification và abort; TC-01–03,17 không chứng minh DB. HTTP integration dùng NestJS, PostgreSQL thật riêng, provider giả, fixtures tổng hợp; TC-04–16 đo lock, transaction, states. Audio-service E2E giới hạn: upload → process → worker → fake provider → persist → đọc transcript (TC-05); không phải full-system App/LLM/OpenAI.

Không chọn browser visual E2E vì không trực tiếp kiểm tra transaction/retry; benchmark độ chính xác ASR không chứng minh idempotency; load paid provider không cần thiết và phát sinh chi phí. Dữ liệu chọn theo state/guard, attempts 0/2/3, checkpoint compatible/incompatible, provider temporary/permanent, một/nhiều asset. Xem [state transitions](state-transitions.md) và [test cases](test-cases.md).
