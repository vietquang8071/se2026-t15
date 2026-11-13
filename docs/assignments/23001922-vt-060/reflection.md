# Reflection

Qua bài tập này, tôi nhận ra độ tin cậy của một thay đổi không chỉ đến từ số lượng test pass mà từ việc kiểm chứng đúng rủi ro. Minh chứng rõ nhất là test RED dùng trigger PostgreSQL giả lập lỗi ghi dữ liệu: AudioAsset chuyển sang `processing`, trong khi AudioJob vẫn `queued`. Trạng thái không nhất quán này cho thấy nguy cơ failure từng phần mà kiểm thử chỉ dựa vào HTTP response có thể bỏ sót. Sau khi hai thao tác cập nhật được đặt trong cùng một transaction, test chuyển sang GREEN, xác nhận khả năng rollback đồng bộ khi ghi dữ liệu thất bại.

Các mức kiểm thử cung cấp những bằng chứng khác nhau. Unit test kiểm tra retry và phân loại lỗi; integration test với HTTP, worker và PostgreSQL thật kiểm chứng trạng thái lưu trữ; provider giả giúp tái hiện lỗi mà không phát sinh chi phí. Mutation testing đảo điều kiện giới hạn retry và bị hai test biên phát hiện, chứng tỏ các assertion có khả năng phát hiện sai lệch nghiệp vụ này. Tuy vậy, line coverage 96,67% và branch coverage 76,69% không có nghĩa mọi tình huống đều an toàn.

Ba lượt đo với 40 tác vụ độc lập đều có p95 tiếp nhận dưới 1,5 giây, nhưng không chứng minh 40 phiên âm chạy đồng thời do worker xử lý tuần tự. Ba lượt kiểm tra lặp cũng chưa loại trừ hết nguy cơ flaky test.

Rủi ro lớn còn lại là provider trả kết quả thành công nhưng tiến trình dừng trước khi lưu checkpoint, khiến request có thể bị gửi lại. Kiểm thử tiếp theo có giá trị nhất là tiêm crash đúng thời điểm này, khởi động lại và đối chiếu số lần gọi provider, checkpoint cùng transcript. AI hỗ trợ lập kế hoạch, tạo test, đề xuất patch và tổng hợp evidence. Tôi đã review nội dung AI hỗ trợ và chịu trách nhiệm về các kết luận dựa trên code, diff và log thực thi.
