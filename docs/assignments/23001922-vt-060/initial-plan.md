# VT-060: kế hoạch AI trước thay đổi mã mới

Thời điểm lập: 2026-11-14; baseline mới `db34fa50cf98730f4adf733dd4937585915acb71`. Baseline dự án trước ba commit BT3: `34455552b6ebcef4ea155b2ba6dc86719a14220d`. Không coi merge-base với main là baseline riêng của BT3.

## Vấn đề và phạm vi

Provider có thể lỗi tạm thời; retry phải có giới hạn, tái sử dụng kết quả đã lưu và không nhân bản job hay transcript. Failure giữa các thao tác DB có thể để trạng thái job/asset không nhất quán. Lát cắt đề xuất: đảm bảo hai thay đổi khi bắt đầu xử lý được commit hoặc rollback cùng nhau, kiểm chứng bằng PostgreSQL và failure injection. Giữ nguyên retry, checkpoint và transaction ghi kết quả/thất bại đã có.

## Assumptions và review bởi AI

| Giả định ban đầu | Kiểm tra thực tế | Kết luận và thay đổi kế hoạch |
|---|---|---|
| Cần xây lại retry từ đầu | `audio-provider.ts` retry tối đa ba lần; `audio.service.ts` có job retry | Sai: giữ cơ chế hiện tại, bổ sung invariant còn thiếu. |
| Checkpoint đảm bảo provider exactly-once | README audio mô tả crash sau response trước ghi checkpoint | Sai: chỉ đảm bảo tái sử dụng checkpoint đã commit; không hứa exactly-once bên ngoài. |
| 40 request cùng audio đại diện 40 job | schema unique audioId; process tái sử dụng job | Không phù hợp: đo riêng request trùng và 40 asset độc lập. |
| Hai trạng thái bắt đầu được ghi nguyên tử | `run` cập nhật asset rồi job bằng hai lệnh riêng | Cần thử failure injection; nếu được chứng minh sẽ dùng transaction nhỏ. |

Bản review ban đầu do AI thực hiện; sau đó, sinh viên xác nhận đã review; chưa ghi nhận xác nhận riêng về cam kết trách nhiệm. Không sửa AGENTS.md: quy ước `son_branch` ở đó được chỉ định nhánh VT-060 cụ thể trong yêu cầu hiện tại thay thế cho bài này.

## Trình tự và rủi ro

1. Chạy baseline test trên PostgreSQL test riêng; không gửi audio cá nhân hoặc gọi provider thật.
2. Viết test trước: chặn ghi job khi bắt đầu và khi ghi failure; kiểm tra asset/job vẫn ở trạng thái trước khi chạy, không có transcript hoặc provider call. Chạy RED trước khi sửa production.
3. Nếu RED đúng nguyên nhân, dùng một transaction cho hai cập nhật bắt đầu; không đổi schema/API. Kiểm tra trạng thái bị xóa, hết hạn và race trước khi chấp nhận patch.
4. Chạy lại test và regression, review diff, mutation trên bản cô lập, kiểm tra coverage/flaky, đo tải 40 request trùng và 40 asset độc lập.
5. Ghi các kết quả thật, giới hạn, lệnh và SHA; tạo báo cáo và PDF; chỉ push đúng nhánh.

Risk cao: ghi dở giữa asset/job, nhân bản side effect, checkpoint bị mất trước khi commit; risk trung bình: retry vượt giới hạn, concurrency và cancellation. Cân nhắc xử lý bằng startup reconciliation nhưng chọn transaction vì phòng ngừa partial commit thay vì sửa trạng thái sau khi xảy ra; cần kiểm chứng không làm xấu delete/restart. File dự kiến: `apps/audio/src/audio/audio.service.ts`, `apps/audio/test/http/audio-http.test.mjs`, tài liệu và harness assignment. Điều kiện nghiệm thu: RED vì invariant, GREEN với patch, regression chạy được, không tuyên bố provider exactly-once.
