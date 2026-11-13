# Đặc tả VT-060

Dịch vụ đã có retry provider và retry job. Lỗi tạm thời cần được xử lý có giới hạn, giữ một job cho mỗi asset và tái sử dụng checkpoint đã ghi. Hai cập nhật bắt đầu job trước đây có thể commit dở; cần bảo vệ cặp trạng thái khi persistence gặp lỗi.

| ID | Điều kiện và kích hoạt | Hành vi mong đợi và kiểm chứng | Nguồn gốc |
|---|---|---|---|
| AC-01 | Provider trả 503 rồi 200 | Tối đa ba request, trả kết quả; mock fetch và số lần gọi (TC-01, TC-02) | Đã có |
| AC-02 | Lỗi 401/quota hoặc job failed đã chạy 3 lần | Không retry auth/quota; process trả 409 khi attempts ≥ 3, không gọi provider (TC-03, TC-04) | Đã có |
| AC-03 | Cùng asset nhận process lặp/đồng thời | Cùng job ID, DB tối đa một job/asset (TC-05, TC-06) | Đã có |
| AC-04 | Ghi start job thất bại và ghi failure cũng thất bại | Hai cập nhật start rollback; attempts/providerCalls không tăng (TC-07). Ghi failure terminal cập nhật cả job/asset trong transaction (TC-08) | Start mới, failure đã có |
| AC-05 | Retry/restart có checkpoint tương thích | Dùng checkpoint đã commit, không gọi provider lần nữa (TC-09, TC-10) | Đã có |

NFR-01: 40 request đồng thời, p95 tiếp nhận POST process ≤ 1.500 ms, không gồm upload và hoàn tất phiên âm. NFR-02: không có job trùng và commit dở trong các kịch bản đã thử; không suy rộng ra mọi lỗi hệ thống.

DB unique AudioJob.audioId bảo đảm tối đa một job cho asset; row lock serialize process/delete. Transaction bắt đầu ghi AudioAsset.processing và AudioJob.running cùng attempts; transaction khác ghi transcript/completed; transaction ghi terminal failure cập nhật cả hai. Chỉ bảo đảm atomicity các ghi trong từng transaction, không có transaction xuyên provider/filesystem.

attempts tăng khi worker bắt đầu một lượt job; providerCalls tăng tại beforeCall trước mỗi request và không phải số job attempts. Có cửa sổ crash giữa tăng counter và request. Checkpoint ghi sau response validate, trước transcript; chỉ tái sử dụng checkpoint tương thích đã persist. Crash sau provider trả và trước commit checkpoint có thể gọi lại; không đảm bảo external exactly-once hay không thu phí trùng. Nếu ghi failure cũng thất bại, transaction rollback; trạng thái trước transaction được giữ, cần restart recovery nếu job đang running.
