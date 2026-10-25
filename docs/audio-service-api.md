# Audio service — API và vòng đời dự kiến

## 1. Trạng thái và phạm vi

Tài liệu này là **kế hoạch API**, không phải endpoint đang hoạt động. Hiện đã có helper kiểm tra audio, tách MP4 sang WAV và tests. HTTP upload/storage/job/retention chưa được triển khai; `GET /health` ở NestJS vẫn là endpoint hiện có của bộ khung.

Phần audio phát triển độc lập trước khi tích hợp App và LLM. Đầu vào **chỉ upload** WAV/MP3/M4A/WebM/MP4, tối đa 100 MB / 60 phút. Không có thu âm microphone/trình duyệt. MP4 phải có một audio track hợp lệ; giữ video nguồn và tạo WAV riêng. Xem [Audio ingestion](audio-ingestion.md) cho policy và code đã có.

ASR sẽ dùng **Whisper qua dịch vụ bên ngoài**, không chạy Whisper local hoặc yêu cầu GPU local. Chưa gọi API thật trong task upload/MP4. Diarization qua dịch vụ ngoài cần chốt provider riêng; không mặc định Whisper trả được speaker labels.

## 2. Các API sẽ triển khai

Audio service có base URL riêng khi chạy độc lập. Đây là các route tương đối dự kiến, chưa thay đổi API meeting của App:

| Method | Route                              | Kết quả dự kiến                                                                                                        |
| ------ | ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| POST   | `/api/audio`                       | Multipart `file` và `retention_days` bắt buộc (30 hoặc 60); 201 sau khi lưu/kiểm tra metadata thành công, trả audio_id |
| GET    | `/api/audio/{audio_id}`            | Metadata, trạng thái xử lý và expires_at; 404 với ID không tồn tại                                                     |
| DELETE | `/api/audio/{audio_id}`            | Xóa media nguồn/dẫn xuất/chunk theo cùng audio_id; xử lý job đang chạy an toàn; không xóa meeting/LLM artifacts        |
| POST   | `/api/audio/{audio_id}/process`    | Phase tiếp theo: 202 + job_id cho normalization/chunk/ASR/diarization, không chờ model trong HTTP request              |
| GET    | `/api/audio/jobs/{job_id}`         | Phase tiếp theo: stage/progress/error/result references                                                                |
| GET    | `/api/audio/{audio_id}/transcript` | Phase tiếp theo: segment/word timestamps, speaker labels, offset về nguồn                                              |

Job được lưu trạng thái thay vì chỉ giữ trong RAM; retry không tạo transcript/chunk trùng. Audio_id độc lập meeting_id, giúp kiểm thử audio service trước khi App nối vào. Auth/storage adapter cụ thể được thiết kế khi triển khai API; helper local hiện tại không đồng nghĩa service đã sẵn sàng public.

Response metadata dự kiến, chưa phải output HTTP thật:

```json
{
  "audio_id": "audio-example-001",
  "status": "uploaded",
  "source_format": "mp4",
  "source_size_bytes": 6041,
  "source_duration_sec": 0.75,
  "audio_start_sec": 0.186,
  "retention_days": 30,
  "created_at": "2026-10-25T09:00:00.000Z",
  "expires_at": "2026-11-24T09:00:00.000Z"
}
```

Upload không có nghĩa ASR đã xong. MP4 có thể được tách ở job preprocessing sau upload; chỉ trả trạng thái prepared khi file dẫn xuất đã kiểm tra được. Không trả absolute path ra HTTP response.

## 3. Chính sách lưu 30/60 ngày

- retention_days chỉ nhận **30 hoặc 60**, caller chọn rõ khi upload; chưa mặc định âm thầm nếu thiếu.
- expires_at = created_at + retention_days × 24 giờ, tính bằng UTC từ lúc upload được chấp nhận/persist. Upload/validation lỗi không tạo asset hợp lệ hay thời hạn lưu giả.
- Bản gốc, WAV dẫn xuất và các chunk dùng cùng hạn gốc. Xem/tải/xử lý lại không tự gia hạn; tính năng gia hạn nếu cần sẽ là task riêng.
- Metadata expiry phải được lưu bền vững. API từ chối đọc/xử lý media đã hết hạn ngay cả khi job cleanup vật lý chưa chạy.
- Cleanup của audio service sẽ dọn nguồn và dẫn xuất, phối hợp với job đang chạy để không tạo lại media sau khi xóa; file tạm thất bại được dọn sớm, không chờ 30/60 ngày.
- **App** đọc expires_at và gửi thông báo gần hạn. Audio service chưa gửi email/push và chưa tự chọn số ngày nhắc trước. App cần bảo đảm người dùng biết hạn lưu ngay từ khi upload.
- Audio retention chỉ áp dụng media; không tự xóa transcript, biên bản hoặc meeting của App/LLM nếu chưa có chính sách riêng.

## 4. Thứ tự task tiếp theo

1. Đóng API upload/storage độc lập với audio_id và retention metadata; test HTTP bằng file tổng hợp.
2. Job preprocessing: tách MP4, chuẩn hóa audio, giữ source offset; helper tách MP4 đã có, cần nối vào job.
3. Chunking theo dung lượng sau encode; ghép segment/word timestamps về nguồn.
4. Whisper external API, job/retry và lưu transcript; benchmark tiếng Việt bằng provider thật.
5. Diarization external provider và ghép nhãn người nói; không thay thế bằng phỏng đoán danh tính từ LLM.
6. Cleanup media 30/60 ngày và API xóa có test; bàn giao expires_at cho App làm thông báo.
7. Hoàn thiện contract/test audio service rồi mới nối App + audio + LLM.

Mỗi task có commit riêng. Không đánh dấu HTTP upload, ASR hoặc retention hoàn thành chỉ vì helper/contract đã có.
