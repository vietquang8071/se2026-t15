# Mô hình chuyển trạng thái

Status là chuỗi trong schema, không phải enum DB; bảng mô tả đường đi service chứ không chứng minh mọi chuỗi sai bị DB từ chối. Asset failed có thể tồn tại trong lúc job đã requeue, trước khi worker chạy lại.

| Job / asset hiện tại | Sự kiện, guard | Job / asset tiếp theo | Side effect | Hợp lệ |
|---|---|---|---|---|
| Không job / uploaded | process, asset hợp lệ và có key | queued / uploaded | Tạo job duy nhất | Có |
| queued hoặc running / trạng thái phù hợp | process lại | giữ job và status | Trả cùng ID | Có |
| completed / completed | process lại | completed / completed | Trả cùng ID | Có |
| queued / uploaded hoặc failed | worker, attempts < 3 | running / processing | Transaction; attempts +1 | Có |
| queued / uploaded | ghi running và ghi failure đều lỗi | queued / uploaded | Rollback, không gọi provider | Có; TC-07 |
| running / processing | thành công, asset còn hạn | completed / completed | Transcript và trạng thái commit chung | Có |
| running / processing | lỗi worker, ghi failure thành công | failed / failed | Ghi errorCode trong transaction | Có |
| running / processing | ghi failure không thành công | running / processing | Rollback, log; cần recovery | Có; TC-08 |
| failed / failed | process, attempts < 3 | queued / failed | Giữ job, xóa errorCode | Có |
| failed / failed | process, attempts ≥ 3 | failed / failed | HTTP 409, không enqueue | Không cho retry |
| running / processing | restart | queued / processing | Stage recovered; worker tiếp tục | Có |
| bất kỳ / expired hoặc deleted | process | không tạo job mới | 410 trước lock hoặc 404 nếu mất hợp lệ trong lock/deleted | Không |
| running / processing | DELETE | tombstone, abort, xóa asset/job | Cascade | Có |

Chọn attempts 0 và 1 cho trạng thái đầu/lần thử; 2 cho lần cuối còn được phép, 3 cho biên từ chối. Test hiện có chứng minh 2 và 3 trực tiếp, 0 trong test rollback; biên 1 và >3 chưa có test độc lập. So sánh checkpoint có/không và tương thích/không; 503 khác auth/quota; request đồng thời cùng asset khác 40 asset độc lập.
