# Đối chiếu yêu cầu — không phải tự chấm điểm

| Nhóm rubric | Vị trí nội dung chính | Kết luận kiểm tra phạm vi |
|---|---|---|
| A — 20 điểm | Trang 1; trade-off/retention/CR ở trang 7 | 3 drivers; 1 scenario đủ 6 thành phần; đúng 709 đồng thời, p95 5.0s cho core read; 70 ngày ops; 22 giờ phản hồi CR. SLO thêm được gắn nhãn đề xuất. |
| B — 25 điểm | Trang 2–4 | Hai sơ đồ vector; 8 module/component; dependency và runtime khác nhau; ownership/contract; invariant, deploy/rollback, schema, in-flight jobs. Enforcement/lease/migration chưa triển khai được ghi planned. |
| C — 20 điểm | Trang 4 | 2 phương án triển khai cụ thể; ADR đề xuất cá nhân, alternatives/consequences/trigger. Không khẳng định nhóm thông qua. |
| D — 20 điểm | Trang 5–6 | Module thật dẫn commit; 3 vấn đề khác nhau; before minh họa gắn nhãn; code excerpt nguyên văn; after; characterization giữ behavior và tách behavior changes. |
| E — 5 điểm | Trang 6 | 3 debt entries, Impact/Urgency/Effort 1–5, thứ tự và completion criteria. Shortcut sample tách khỏi trạng thái repo. |
| F — 10 điểm | Trang 7 và phụ lục log | Initial output thật lưu trước source review; 3 đề xuất sửa có evidence; traceability; không ghi sinh viên đã xác nhận. |

Đây là kiểm tra các nội dung đã có, không phải khẳng định đạt 100 điểm hoặc giảng viên chấp nhận kịch bản thay code nghiệp vụ thực.

Kiểm tra artifact: 7 trang chính + 9 trang AI Usage Log, một PDF đúng tên; IDs/cam kết; 23 permalink links; font hỗ trợ toàn bộ ký tự đã render, sơ đồ có mũi tên vector; source repository sạch. Kiểm tra bằng script tại pdf-check.json và xem ảnh render.

Đã chạy: 17 tests local (11 unit/characterization + 6 integration/fault), PostgreSQL test isolated. Chưa chạy: production NestJS, vendor/LLM thật, 709 concurrent load, p95 benchmark, deploy/rollback image, migration compatibility, job restart/lease. Chưa có Lecture 04/05. Các hạn chế có trong 7 trang chính, không giấu ở phụ lục.
