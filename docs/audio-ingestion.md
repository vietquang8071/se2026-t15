# P02 — Audio inspection và bàn giao tích hợp

## 1. Phân công và phạm vi

- **Sơn — Audio:** kiểm tra file, đọc metadata bằng FFprobe, kiểm tra giải mã bằng FFmpeg, fixture và tests audio.
- **Việt Quang — LLM:** trích xuất nghiệp vụ từ transcript ở các phase sau.
- **App:** API meeting/upload, database/storage, giao diện, quyền truy cập và nối hàm audio vào luồng upload.

Phần audio của P02 cung cấp `inspectAudio` cho App gọi sau khi lưu file tạm. Chưa làm ASR, thu âm trình duyệt, chuẩn hóa/chia chunk hoặc LLM. Giới hạn upload lớn hơn 25 MB để P05 có thể xử lý file dài; P02 chưa gửi file lên provider.

## 2. Quy tắc đã chốt

| Nội dung     | Quy tắc                                                                                                    |
| ------------ | ---------------------------------------------------------------------------------------------------------- |
| Định dạng    | WAV, MP3, M4A, WebM; kiểm tra extension và container thực, không tin filename/MIME riêng lẻ                |
| Dung lượng   | Tối đa **100 MB = 100.000.000 bytes**, tính từ file thật; file rỗng bị từ chối                             |
| Thời lượng   | Lớn hơn 0, tối đa **3.600 giây**; từ chối file không xác định được duration                                |
| Nội dung     | Một audio stream, không có video stream; đọc được codec/sample rate/channels và giải mã được toàn bộ audio |
| Nơi lưu      | Local trên máy chạy API; đường dẫn nằm trong thư mục upload do App cấu hình                                |
| File/meeting | Một file, chưa thay thế; App kiểm tra/chặn upload lần hai, kể cả request đồng thời                         |
| Luồng        | Tạo meeting → upload ở trang chi tiết; upload lỗi giữ meeting và cho thử lại                               |
| Sau reload   | App đọc metadata từ database; không phụ thuộc state của form                                               |

MIME thường gặp: WAV `audio/wav`, `audio/x-wav`, `audio/wave`, `audio/vnd.wave`; MP3 `audio/mpeg`, `audio/mp3`; M4A `audio/mp4`, `audio/x-m4a`, `audio/m4a`; WebM `audio/webm`. MIME thiếu hoặc `application/octet-stream` có thể được chấp nhận **sau kiểm tra nội dung**. MIME khai báo cụ thể nhưng không khớp extension/container bị từ chối. Không nhận file video có phần âm thanh chỉ bằng cách đổi đuôi.

Với M4A, chấp nhận container MP4-family có audio AAC hoặc ALAC; WebM dùng Opus hoặc Vorbis; MP3 phải có codec MP3; WAV dùng codec audio mà FFmpeg giải mã được. Không yêu cầu mọi file phải là mono/16 kHz; đó là bước chuẩn hóa P04.

## 3. Giao diện bàn giao cho App

Hàm [`inspectAudio(input, uploadDirectory)`](../apps/api/src/audio/audio-inspection.ts) nhận:

| Tham số              | Ý nghĩa                                                                                           |
| -------------------- | ------------------------------------------------------------------------------------------------- |
| `input.filePath`     | File tạm local đã lưu, tên do server tạo; không truyền URL hoặc đường dẫn lấy trực tiếp từ client |
| `input.originalName` | Tên gốc từ upload, chỉ dùng xác định extension                                                    |
| `input.mimeType`     | MIME client khai báo, có thể bỏ qua; dùng như thông tin đối chiếu                                 |
| `uploadDirectory`    | Thư mục local được phép đọc, do server cấu hình                                                   |

Kết quả dự kiến:

```json
{
  "format": "wav",
  "mime_type": "audio/wav",
  "size_bytes": 32078,
  "duration_sec": 1,
  "codec": "pcm_s16le",
  "sample_rate": 16000,
  "channels": 1
}
```

`mime_type` là MIME chuẩn của format đã xác minh. Thời lượng tính bằng giây, không làm tròn thành phút. Không trả absolute path, không xóa/chuyển đổi file của caller và không đưa filename riêng tư vào lỗi trả về.

FFprobe có timeout mặc định 10 giây; bước giải mã FFmpeg là 60 giây. Có thể cấu hình qua tham số thứ ba `AudioInspectionOptions` (`probeTimeoutMs`, `decodeTimeoutMs`, `ffprobePath`, `ffmpegPath`), chỉ lấy cấu hình từ server. Inspector không phải NestJS controller/provider nên App có thể import hàm trực tiếp, chưa cần thay `AppModule`.

| Mã lỗi                     | HTTP gợi ý cho App | Ý nghĩa                                                                      |
| -------------------------- | ------------------ | ---------------------------------------------------------------------------- |
| `INVALID_AUDIO_PATH`       | 400                | File thiếu, không phải file thường hoặc nằm ngoài thư mục upload             |
| `EMPTY_AUDIO`              | 400                | File không có dữ liệu                                                        |
| `AUDIO_TOO_LARGE`          | 413                | Vượt 100 MB                                                                  |
| `UNSUPPORTED_AUDIO_FORMAT` | 415                | Extension, MIME, container hoặc codec không phù hợp                          |
| `INVALID_AUDIO`            | 422                | Không đọc/giải mã được audio, metadata sai, có video hoặc nhiều audio stream |
| `AUDIO_TOO_LONG`           | 422                | Vượt 60 phút                                                                 |
| `AUDIO_INSPECTION_TIMEOUT` | 503                | Công cụ xử lý vượt thời gian cho phép                                        |
| `AUDIO_TOOL_UNAVAILABLE`   | 503                | Chưa cài FFprobe/FFmpeg hoặc cấu hình công cụ lỗi                            |

Hàm ném `AudioInspectionError` có `code`, `statusCode` và `message`; App ánh xạ sang envelope lỗi của endpoint upload khi thiết kế API. Các HTTP status trên chưa xác nhận endpoint đã tồn tại.

## 4. Trình tự tích hợp

1. App xác minh meeting tồn tại và chưa có audio. Chặn upload quá 100 MB ngay trong lớp nhận multipart để tránh ghi file không giới hạn.
2. Lưu tạm vào thư mục riêng, tên ngẫu nhiên do server tạo; không dùng original filename làm storage path. Không cho client thay đổi file trong lúc kiểm tra.
3. Gọi `inspectAudio`, đợi kết quả trước khi đánh dấu upload thành công. Thư mục và file phải là local; hàm giới hạn protocol của FFmpeg/FFprobe ở file/pipe.
4. Nếu hợp lệ, App lưu storage key và metadata trong database, bảo đảm ràng buộc một audio/meeting và xử lý tranh chấp hai upload cùng lúc.
5. Nếu lỗi, App dọn file tạm; nếu bước lưu metadata thất bại thì dọn cả file vừa nhận. Giữ meeting để người dùng upload lại. Inspector không quản lý transaction/storage.
6. App trả metadata để hiển thị tên file, dung lượng, thời lượng. Thu âm, playback endpoint, ASR/chunking thuộc phase khác.

## 5. Điều kiện kiểm tra phần audio

- Kiểm tra thật cả WAV/MP3/M4A/WebM bằng fixture tổng hợp, không có giọng nói hay dữ liệu cá nhân.
- File lỗi, file rỗng, vượt dung lượng/thời lượng, đổi đuôi, MIME giả, không có audio, có video và nhiều audio stream phải bị từ chối.
- Path ngoài upload root, symlink trỏ ra ngoài và tên chứa ký tự shell không được làm chạy lệnh ngoài ý muốn.
- Thiếu công cụ hoặc timeout phải báo lỗi rõ, không gọi là upload thành công.
- Đây là kiểm tra audio ingestion; không dùng kết quả này để kết luận chất lượng ASR/diarization.
