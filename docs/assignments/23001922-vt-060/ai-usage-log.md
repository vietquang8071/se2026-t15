# Nhật ký sử dụng AI

Nhật ký mô tả hoạt động có evidence; các phase không có timestamp độc lập không được gán thời điểm giả. Thời gian commit theo Git, múi giờ +07. Codex hỗ trợ viết và review; sau đó sinh viên đã xác nhận đã review; chưa ghi nhận xác nhận riêng về cam kết trách nhiệm.

| Thời gian/phase | Công cụ và task | Output và quyết định | Evidence |
|---|---|---|---|
| 14/11/2026 02:48 | Codex: plan và assumptions | Giữ retry; chọn transaction start; review AI bác bỏ giả định retry chưa có và exactly-once | [plan](initial-plan.md), commit 409fa7d |
| 02:48 | Codex: test trước patch | Chèn DB trigger, chấp nhận RED vì sai trạng thái thực | f55a0d1, [red](evidence/red.log) |
| 02:49 | Codex: patch và diff review | Transaction cho hai update; chấp nhận sau GREEN | 12e9cdc, [green](evidence/green.log) |
| 14/11, phase verification | Codex: regression, mutation, coverage, tải | Chấp nhận kết quả trong giới hạn được đo | [evidence](evidence/) |
| 14/11, lượt hoàn thiện | Codex: audit, lặp test và viết báo cáo | Báo cáo AI-assisted; sinh viên sau đó xác nhận đã review | Các tài liệu cùng thư mục |
| Lượt cập nhật reflection | Sinh viên cung cấp trực tiếp nội dung reflection; Codex cập nhật báo cáo | Giữ nguyên văn; sinh viên sau đó xác nhận đã review | reflection.md và báo cáo |
| Lượt cập nhật liên kết | Sinh viên xác nhận đã review; chưa ghi nhận xác nhận riêng về cam kết | Cập nhật trạng thái review, khôi phục hyperlink và dàn trang | Báo cáo và xác nhận trong hội thoại |

Prompt chính và yêu cầu tiếp tục có trong cuộc hội thoại; không có transcript độc lập đầy đủ của mọi thao tác trước trong repo. Không tự suy diễn nội dung hoặc cách review vượt ngoài lời xác nhận của sinh viên.

Hai output AI dễ gây tin nhầm: (1) kiểm tra 503→200 chỉ chứng minh provider retry, không chứng minh DB không trùng; bổ sung TC-05–09. (2) 40 request cùng một ID nhìn như tải 40 người nhưng unique/row lock chỉ tạo một job; bổ sung TC-16 với 40 asset. Checkpoint không bảo đảm external exactly-once, coverage cao không bảo đảm mọi crash window.
