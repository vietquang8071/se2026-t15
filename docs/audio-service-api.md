# Audio service API — độc lập với App

Implementation: [`services/audio`](../services/audio/README.md), NestJS riêng,
port 3002 mặc định. App API vẫn ở `apps/api`/3001. Audio có Prisma schema/database,
storage và worker riêng; không phụ thuộc meeting_id hoặc LLM.

## Xác thực và endpoint

`GET /health` không cần key: 200 `{ "status": "ok", "service": "audio" }`,
503 nếu mất DB/worker lock. Mọi route dưới cần header `X-API-Key: <AUDIO_API_KEY>`.
Đây là key cho service nội bộ; App phải kiểm tra quyền sở hữu của người dùng.
Không trả filesystem path, storage key, checkpoint hoặc raw provider error ra API.

| Method | Route                                            | Kết quả                                                                                 |
| ------ | ------------------------------------------------ | --------------------------------------------------------------------------------------- |
| POST   | `/api/audio`                                     | Multipart `file` + `retention_days` (30/60), 201 metadata                               |
| GET    | `/api/audio/{audio_id}`                          | Metadata, trạng thái, job_id                                                            |
| POST   | `/api/audio/{audio_id}/process`                  | 202 + job_id; gọi lặp trả cùng ID; failed cho retry có giới hạn                         |
| GET    | `/api/audio/jobs/{job_id}`                       | Stage/progress/error, attempts/provider_calls                                           |
| GET    | `/api/audio/{audio_id}/transcript`               | Transcript có segment/word timestamps và speaker; 409 nếu chưa có                       |
| PATCH  | `/api/audio/{audio_id}/speakers/{speaker_id}`    | JSON `{ "name": "Sơn" }`, trả danh sách speaker; tên 1–100 ký tự, không control/newline |
| GET    | `/api/audio/{audio_id}/media?variant=source`     | Nguồn, hỗ trợ single HTTP Range 206/416                                                 |
| GET    | `/api/audio/{audio_id}/media?variant=normalized` | WAV khi job completed; 409 nếu chưa sẵn sàng                                            |
| GET    | `/api/audio/{audio_id}/export?format=json`       | Download json/txt/srt/md/xlsx/pdf; mặc định json                                        |
| DELETE | `/api/audio/{audio_id}`                          | 204 sau khi xóa media/transcript/checkpoint/job; 404 nếu không tồn tại                  |

## Upload

WAV/MP3/M4A/WebM/MP4, tối đa 100.000.000 bytes / 3.600 giây, đúng một audio
track giải mã được. Chỉ upload, không thu âm trình duyệt. Thiếu/sai retention
bị từ chối; không mặc định. Tối đa hai upload đồng thời, stream xuống disk.
MP4 không tiếng/nhiều track bị từ chối. Nguồn không bị overwrite.

Response minh họa:

```json
{
  "audio_id": "00000000-0000-0000-0000-000000000001",
  "status": "uploaded",
  "source": {
    "format": "mp4",
    "mime_type": "video/mp4",
    "size_bytes": 6041,
    "duration_sec": 0.75,
    "codec": "aac",
    "sample_rate": 16000,
    "channels": 1,
    "audio_start_sec": 0.186
  },
  "retention_days": 30,
  "created_at": "2026-10-25T09:00:00.000Z",
  "expires_at": "2026-11-24T09:00:00.000Z",
  "job_id": null
}
```

Upload chưa gọi provider. POST process trả
`{ "audio_id": "...", "job_id": "...", "status": "queued" }`.
Mỗi audio có một job; các request đồng thời được serialize bằng row lock.

## Job và khôi phục

GET job trả `job_id`, `audio_id`, `status`, `stage`, `progress`, `attempts`,
`provider_calls`, `error`, `created_at`, `updated_at`, `transcript_url`.
Ngày giờ UTC ISO 8601. Stages: queued/recovered → preparing → transcribing →
diarizing → completed hoặc failed. Progress theo stage, không phải ETA.

Một worker xử lý tuần tự. DB lưu checkpoint từng chunk/diarization; restart
khôi phục running thành queued. Mỗi job tối đa ba lượt chạy; từng request provider
tối đa ba attempt cho network/429/5xx, không retry auth/quota/request sai.
`provider_calls` đếm mọi attempt; crash trước persist checkpoint có thể cần gọi lại.
Không có cam kết exactly-once phía provider. Không có chế độ provider mock qua API.

## Transcript và timestamp

JSON trả `schema_version`, `audio_id`, `language`, `timeline`,
`source_audio_start_sec`, `duration_sec`, `text`, `speakers`, `segments`,
`warnings`, `models`. Segment ví dụ:

```json
{
  "id": "SEG-0001",
  "start": 1.25,
  "end": 2.5,
  "speaker": "speaker_1",
  "text": "Xin chào",
  "words": [
    { "word": "Xin", "start": 1.25, "end": 1.8, "speaker": "speaker_1" },
    { "word": "chào", "start": 1.8, "end": 2.5, "speaker": "speaker_1" }
  ]
}
```

Timestamps tính bằng giây trên **file nguồn**, đã cộng chunk offset và MP4 audio
offset. Seek nguồn dùng trực tiếp `start`; seek normalized WAV trừ
`source_audio_start_sec`. SRT cũng theo timeline nguồn.

Whisper cung cấp từ/timing; segment cuối được nhóm lại theo speaker, khoảng nghỉ
và độ dài (~20 giây), không giả danh segmentation gốc của Whisper. Diarization
gọi trên toàn audio MP3 nén để giữ speaker ID nhất quán giữa chunk ASR.
Vùng mơ hồ/chồng tiếng dùng `unknown`. Speaker không phải danh tính xác thực.
PATCH chỉ đổi tên hiển thị, không sửa timing hoặc nhãn tự động.

Mọi export dùng transcript hiện tại sau sửa tên. Excel có Transcript/Words/Metadata;
PDF render từ cùng Markdown do service tạo. Đây là bản chép lời, chưa phải biên bản LLM.

## Retention và xóa

- `expires_at = created_at + retention_days × 24 giờ` UTC, không tự gia hạn.
- Quyết định mới: xóa **cả transcript/checkpoint** cùng nguồn/WAV/chunk; không xóa
  meeting/biên bản của App/LLM. App sở hữu thông báo gần hạn.
- Hết hạn trả 410 ngay cho đọc/xử lý, dù chưa cleanup; sau khi xóa DB trả 404.
- Cleanup chạy startup và mỗi tick (~1 giây), retry nếu IO/DB lỗi.
- DELETE tombstone trước để cấm đọc, hủy/chờ job đang chạy rồi xóa file và DB row
  (cascade jobs). Nếu IO lỗi, không trả thành công; tombstone để cleanup thử lại.
- Restart dọn incoming và thư mục không có asset DB; xử lý lại derived files,
  tái dùng checkpoint đã persist. Service chỉ chạy một instance cho một database/storage.
- Bản client đã download nằm ngoài khả năng cleanup của server.

## Lỗi

Lỗi nghiệp vụ: `{ "error": { "code": "..." } }`. Auth/parser/framework có thể
dùng envelope NestJS. Lỗi worker nằm trong `job.error`, không đổi HTTP response
202 đã trả. Không biến lỗi provider thành kết quả thành công giả.

| HTTP | Code tiêu biểu                                                                                                                                                                                       |
| ---- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 400  | FILE_REQUIRED, INVALID_RETENTION_DAYS, INVALID_SPEAKER_NAME, INVALID_EXPORT_FORMAT, INVALID_MEDIA_VARIANT, INVALID_AUDIO_PATH, EMPTY_AUDIO, lỗi multipart                                            |
| 401  | Thiếu/sai service key                                                                                                                                                                                |
| 404  | AUDIO_NOT_FOUND, JOB_NOT_FOUND, SPEAKER_NOT_FOUND, MEDIA_NOT_FOUND                                                                                                                                   |
| 409  | TRANSCRIPT_NOT_READY, MEDIA_NOT_READY, JOB_RETRY_LIMIT, JOB_CONFIGURATION_CHANGED                                                                                                                    |
| 410  | AUDIO_EXPIRED                                                                                                                                                                                        |
| 413  | AUDIO_TOO_LARGE                                                                                                                                                                                      |
| 415  | UNSUPPORTED_AUDIO_FORMAT                                                                                                                                                                             |
| 416  | Range không hợp lệ                                                                                                                                                                                   |
| 422  | INVALID_AUDIO, AUDIO_TOO_LONG, PROVIDER_FILE_TOO_LARGE                                                                                                                                               |
| 429  | UPLOAD_BUSY                                                                                                                                                                                          |
| 502  | PROVIDER_AUTH_FAILED, PROVIDER_REQUEST_REJECTED, PROVIDER_INVALID_RESPONSE, PROVIDER_INVALID_TRANSCRIPT, PROVIDER_INVALID_TIMESTAMPS, PROVIDER_WORD_TIMESTAMPS_MISSING, PROVIDER_INVALID_DIARIZATION |
| 503  | OPENAI_KEY_MISSING, PROVIDER_QUOTA_EXHAUSTED, PROVIDER_UNAVAILABLE, AUDIO_TOOL_UNAVAILABLE, AUDIO_INSPECTION_TIMEOUT, AUDIO_PROCESSING_TIMEOUT, AUDIO_PROCESSING_FAILED, PDF_FONT_UNAVAILABLE        |

Xem [README service](../services/audio/README.md) về cấu hình, giới hạn chất lượng,
model/provider lifecycle, chạy Docker và kiểm thử thực tế.
