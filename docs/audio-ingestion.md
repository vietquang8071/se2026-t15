# P02 — Upload audio/MP4 và tiền xử lý

## 1. Phân công và trạng thái

- **Sơn — Audio:** audio API độc lập, upload/storage media, kiểm tra metadata, tách/chuẩn hóa audio và tests; ASR qua dịch vụ Whisper bên ngoài ở phase sau.
- **Việt Quang — LLM:** nhận transcript để trích xuất nghiệp vụ ở giai đoạn tích hợp sau.
- **App:** giao diện/meeting, ánh xạ audio_id vào meeting, thông báo gần hạn lưu trữ; chưa nối App vào audio trong đợt này.

**Đầu vào chỉ là file upload**, không thu âm trực tiếp trong trình duyệt. Đã có helper `inspectAudio` và `extractAudioFromMp4` cùng tests. Chưa có HTTP upload, kho media theo audio_id, storage scheduler, ASR hoặc thông báo; xem [Audio service API plan](audio-service-api.md).

## 2. Quy tắc file

| Nội dung               | Quy tắc                                                                                                                                                 |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Định dạng nguồn        | WAV, MP3, M4A, WebM và MP4; đối chiếu extension/MIME với container thật                                                                                 |
| Dung lượng nguồn       | Tối đa **100 MB = 100.000.000 bytes**; không nhận file rỗng                                                                                             |
| Thời lượng             | Lớn hơn 0, tối đa **3.600 giây**, phải xác định được duration                                                                                           |
| Audio stream           | Đúng một audio track giải mã được; nhiều track bị từ chối để tránh chọn nhầm ngôn ngữ/nội dung                                                          |
| Video                  | Chỉ cho phép trong MP4; MP4 không có audio bị từ chối. WebM video vẫn chưa được hỗ trợ                                                                  |
| Bản gốc                | Giữ nguyên, không overwrite khi tách/chuẩn hóa                                                                                                          |
| Bản MP4 dẫn xuất       | WAV PCM 16-bit, mono, 16 kHz, tên/thư mục do server tạo                                                                                                 |
| Giới hạn file dẫn xuất | Không áp lại giới hạn upload 100 MB: WAV 60 phút ở cấu hình trên có thể khoảng 115,2 MB; vẫn giới hạn thời lượng và dung lượng đầu ra theo cấu hình này |

MIME chuẩn: WAV `audio/wav`, MP3 `audio/mpeg`, M4A `audio/mp4`, WebM `audio/webm`, MP4 `video/mp4`. Alias được kiểm soát trong [source](../apps/api/src/audio/audio-inspection.ts). MIME thiếu hoặc `application/octet-stream` chỉ được chấp nhận sau xác minh nội dung. Với MP4, chấp nhận thêm MIME `audio/mp4`/`application/mp4`; container MP4 chỉ có audio cũng dùng được. Không nhận WAV/MKV đổi đuôi thành MP4/WebM.

M4A dùng audio AAC/ALAC; MP3 dùng MP3; WebM dùng Opus/Vorbis và phải có EBML DocType WebM. MP4/WAV chấp nhận audio codec mà FFmpeg giải mã được. MP4 chỉ kiểm tra/giải mã phần âm thanh, không cam kết video phát được hoặc được chuyển mã.

## 3. Hàm kiểm tra file nguồn

[`inspectAudio(input, uploadDirectory, options?)`](../apps/api/src/audio/audio-inspection.ts) nhận file local đã lưu:

| Tham số              | Ý nghĩa                                                                  |
| -------------------- | ------------------------------------------------------------------------ |
| `input.filePath`     | File local có tên do server tạo, không phải URL/path trực tiếp từ client |
| `input.originalName` | Tên gốc, dùng xác định extension                                         |
| `input.mimeType`     | MIME khai báo để đối chiếu, có thể bỏ qua                                |
| `uploadDirectory`    | Thư mục được phép đọc, do server cấu hình                                |

Kết quả MP4 ví dụ:

```json
{
  "format": "mp4",
  "mime_type": "video/mp4",
  "size_bytes": 6041,
  "duration_sec": 0.75,
  "codec": "aac",
  "sample_rate": 16000,
  "channels": 1,
  "audio_start_sec": 0.186
}
```

`duration_sec` của MP4 là duration container, dùng kiểm tra giới hạn nguồn. `audio_start_sec` là mốc bắt đầu audio tính từ đầu timeline container, có thể khác 0; các format audio trước đó giữ nguyên response, không thêm field này. Các giá trị cụ thể phụ thuộc encoder/container, không hard-code offset AAC.

FFprobe đọc metadata với timeout mặc định 10 giây. FFmpeg giải mã toàn bộ audio với timeout 60 giây. `AudioInspectionOptions` cho phép cấu hình binary/timeout từ server, không lấy từ request client. Hàm dùng execFile không qua shell, kiểm tra path thật trong upload root và chỉ cho protocol file/pipe.

## 4. Tách audio từ MP4

`extractAudioFromMp4(input, uploadDirectory, outputDirectory, options?)`:

1. Kiểm tra MP4 nguồn bằng cùng policy 100 MB/60 phút.
2. Tạo thư mục đầu ra riêng dưới outputDirectory đã tồn tại, không dùng original filename làm path.
3. Tách đúng audio track thành WAV PCM 16-bit mono/16 kHz, bỏ video, giữ nguyên nguồn.
4. Kiểm tra metadata WAV và giới hạn đầu ra; dọn thư mục trung gian nếu tách lỗi/timeout.
5. Trả `filePath` local, `metadata` của WAV, `source` metadata MP4 và `source_audio_start_sec`.

Đây là kết quả **nội bộ service**: HTTP API tương lai chỉ trả audio_id/storage key và metadata được phép, không lộ absolute filePath. Các lần gọi tách audio dùng thư mục khác nhau, không overwrite kết quả trước. Bản đầu ra thành công do caller quản lý; bản đầu ra lỗi được helper dọn.

Timestamp transcript từ WAV phải được cộng `source_audio_start_sec` để về timeline MP4; nếu chia chunk thì cộng thêm chunk offset. Chưa có ASR/chunking trong helper này.

| Mã lỗi                     | HTTP gợi ý | Ý nghĩa                                                                                             |
| -------------------------- | ---------- | --------------------------------------------------------------------------------------------------- |
| `INVALID_AUDIO_PATH`       | 400        | File thiếu, không phải file thường hoặc ngoài upload root                                           |
| `EMPTY_AUDIO`              | 400        | File rỗng                                                                                           |
| `AUDIO_TOO_LARGE`          | 413        | Nguồn vượt 100 MB                                                                                   |
| `UNSUPPORTED_AUDIO_FORMAT` | 415        | Extension/MIME/container/codec không phù hợp                                                        |
| `INVALID_AUDIO`            | 422        | Không đọc/giải mã được audio, không có audio hoặc nhiều audio track; video trong format chưa hỗ trợ |
| `AUDIO_TOO_LONG`           | 422        | Nguồn vượt 60 phút                                                                                  |
| `AUDIO_INSPECTION_TIMEOUT` | 503        | Probe/decode/extraction timeout                                                                     |
| `AUDIO_TOOL_UNAVAILABLE`   | 503        | Thiếu FFmpeg/FFprobe hoặc không có quyền thực thi                                                   |
| `AUDIO_EXTRACTION_FAILED`  | 500        | Không tạo được output, tách lỗi hoặc output không hợp lệ                                            |

`AudioInspectionError` có code/statusCode/message; không đưa tên file riêng tư/absolute path vào lỗi public. Inspector không xóa file nguồn hoặc quản lý transaction database.

## 5. Vòng đời và tích hợp sau

- Audio service sẽ nhận upload, cấp audio_id, quản lý local storage và job riêng; upload lỗi dọn file tạm. Không bắt buộc có meeting_id ở audio API.
- App sau này liên kết audio_id với meeting; ràng buộc một media/meeting được kiểm soát ở bước tích hợp App.
- Khi upload cần chọn retention_days **30 hoặc 60**; service sẽ trả created_at/expires_at UTC. Nguồn MP4 và audio dẫn xuất/chunk có cùng hạn; đọc hoặc xử lý lại không tự gia hạn.
- Audio service sẽ chịu trách nhiệm dọn media hết hạn. **App gửi thông báo cho người dùng gần hạn**, dựa trên expires_at; thời điểm/kênh thông báo do App quyết định. Chưa có scheduler hoặc thông báo trong code hiện tại.
- Chưa tự áp chính sách xóa audio cho transcript, biên bản hay dữ liệu meeting; phần đó cần thống nhất riêng với App/LLM.
- Giữ video gốc giúp truy nguồn, nhưng không gửi hình ảnh/video cho LLM; Whisper sẽ nhận phần audio qua dịch vụ bên ngoài khi triển khai ASR.

## 6. Chạy kiểm tra

Yêu cầu Node/pnpm theo [README](../README.md), FFmpeg/FFprobe trên PATH; sau pnpm install:

```sh
pnpm --filter @meeting-minutes/api test:audio
pnpm --filter @meeting-minutes/api lint
```

Tests dùng Node test runner, không thêm thư viện test. Compile riêng module audio nên không cần database, Prisma Client hoặc API key để chạy test audio. Fixture sine tone/video màu được tạo trong thư mục tạm rồi xóa; không commit binary hay ghi âm người thật.

Các case thực gồm bốn format audio và MP4, tách/giữ bản gốc, offset âm thanh, file lỗi, video không tiếng, nhiều track, đổi đuôi, MIME giả, path/symlink ngoài root, dung lượng/thời lượng đúng biên và quá biên. Case timeout/malformed probe dùng tool giả cục bộ và được phân biệt với kiểm tra FFmpeg/FFprobe thật.

Xác minh ngày 25/10/2026: **29 tests pass**, gồm 8 case MP4; không coi đây là bằng chứng HTTP upload, retention tự động, ASR hay thông báo đã chạy.
