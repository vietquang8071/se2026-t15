# Independent Audio API

Service NestJS riêng cho upload → chuẩn hóa → OpenAI transcription +
diarization → transcript → export. Không khởi động App, không dùng model Meeting
hoặc database của App, không chạy model/GPU local.

## Cấu trúc

- `src/audio`: controller, worker, media, provider, transcript và export.
- `prisma`: schema/migration riêng (`AudioAsset`, `AudioJob`).
- `test/audio`: fixture tổng hợp và kiểm tra FFmpeg/provider contract/export.
- `test/http`: HTTP với PostgreSQL thật, provider giả; tạo/xóa database test riêng.
- `scripts`: client xử lý file và benchmark VietMed có transcript đối chiếu.

## Chạy local từ root repo

Yêu cầu Node >=22.18, pnpm 11, PostgreSQL, FFmpeg/FFprobe và font DejaVu Sans.
Giữ API key trong `.env` root; hỗ trợ cả `OPENAI_API_KEY` và `OpenAI_API_KEY`.
`AUDIO_API_KEY` là secret **khác** với key OpenAI, tối thiểu 24 ký tự.

```sh
pnpm install
docker compose up -d postgres
# Chỉ chạy một lần nếu database chưa tồn tại:
docker compose exec -T postgres psql -U meeting_minutes -d postgres -c 'CREATE DATABASE meeting_minutes_audio'
pnpm audio:db:deploy
pnpm audio:build
pnpm --filter @meeting-minutes/audio start
```

Database local dùng `AUDIO_DATABASE_URL`; không dùng `DATABASE_URL` của App.
Đặt các biến sau trong `.env` root (xem `.env.example`):

```dotenv
AUDIO_PORT=3002
AUDIO_HOST=127.0.0.1
AUDIO_DATABASE_URL=postgresql://meeting_minutes:meeting_minutes@localhost:5432/meeting_minutes_audio?schema=public
AUDIO_API_KEY=<secret-rieng-toi-thieu-24-ky-tu>
OPENAI_API_KEY=<openai-key>
```

Mặc định media ở `data/audio` tại root repo, đã gitignore. Có thể đặt
`AUDIO_STORAGE_DIR` bằng absolute path. `AUDIO_PDF_FONT` trỏ tới font hỗ trợ
tiếng Việt; mặc định `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`.

Chỉ chạy một instance service trên cùng database/storage. Advisory lock của
PostgreSQL chặn instance thứ hai; nếu mất kết nối lock, service ngừng nhận việc
và health trả 503, cần restart. Đây là worker local có trạng thái bền vững,
chưa phải hệ thống worker phân tán.

## Docker độc lập

Từ root repo:

```sh
docker compose --env-file .env -f apps/audio/compose.yaml up --build -d
docker compose --env-file .env -f apps/audio/compose.yaml logs -f audio
docker compose --env-file .env -f apps/audio/compose.yaml down
```

Compose này chạy **audio + PostgreSQL riêng**, không khởi động App. Có volume
riêng cho database/media, bind cổng vào localhost. Không chạy đồng thời bản local
và Docker trên cùng cổng. Lệnh `down` giữ dữ liệu; không thêm `-v` nếu muốn giữ volume.
Trước khi public cần HTTPS/reverse proxy và App kiểm soát quyền người dùng;
API key hiện là quyền của service tin cậy, không phải hệ thống tài khoản nhiều người.

## Chạy một file và nhận đủ kết quả

Sau khi service sẵn sàng:

```sh
pnpm audio:file /duong/dan/cuoc-hop.mp4 artifacts/private/audio-result 30
# Tiếp tục poll/tải audio_id có sẵn, không upload bản mới:
pnpm audio:file audio:<audio_id> artifacts/private/audio-result
```

Client upload, gọi process, poll job và tải:
`transcript.json`, `.txt`, `.srt`, `.md`, `.xlsx`, `.pdf`, cùng `metadata.json`.
Excel v2 có hai sheet Transcript/Metadata; transcript v1 cũ vẫn có sheet Words. PDF được render từ cùng Markdown
do service sinh ra và nhúng font tiếng Việt. Đây là **bản chép lời**, chưa phải
biên bản sáu module của LLM.

File đã tải về máy nằm ngoài vòng đời dữ liệu của server; DELETE/expiry trên
server không xóa các bản download của client. Không commit audio/transcript thật.

## API

`GET /health` không cần key; các route `/api/audio` đều cần header `X-API-Key`.
Xem [contract đầy đủ](../../docs/audio-service-api.md), bao gồm lỗi và timestamp.

Upload giới hạn 100.000.000 bytes / 3.600 giây, WAV/MP3/M4A/WebM/MP4. Chỉ upload,
không thu âm trình duyệt. `retention_days` bắt buộc là 30 hoặc 60. Hạn gốc áp dụng
nguồn, WAV, MP3, checkpoint và **transcript**; không gia hạn khi đọc/xử lý lại.
App chịu trách nhiệm thông báo gần hạn.

## Pipeline và giới hạn

1. Upload kiểm tra container/MIME/codec, một audio track và full decode trước persist.
2. POST process trả 202 + job_id. Mỗi audio có một job, gọi lặp trả cùng ID.
3. Worker tạo WAV PCM16 mono/16 kHz và MP3 32 kbps toàn audio; giữ file gốc.
4. Một request `gpt-4o-transcribe-diarize` nhận MP3 với `diarized_json`,
   `chunking_strategy=auto` và `language=vi`. Không chia audio thành nhiều
   request trong ứng dụng. File MP3 phải nhỏ hơn 24.000.000 bytes, nếu không
   service trả `PROVIDER_FILE_TOO_LARGE`.
5. Validate segment, giữ text và ranh giới của provider, gán ID người nói theo
   thứ tự xuất hiện, cộng source offset cho MP4. Transcript mới là schema v2,
   có timestamp theo segment, không có timestamp theo từ.
6. Lưu checkpoint và transcript trong PostgreSQL; các export dùng transcript
   hiện tại nên đổi tên speaker phản ánh vào mọi định dạng.

Provider timeout mặc định 600 giây/request, có thể đổi qua `OPENAI_TIMEOUT_MS`
(tối đa 600 giây). Retry tối đa ba attempt cho lỗi network/429/5xx; auth,
quota và request lỗi không retry âm thầm. Job thất bại có thể gọi process lại,
tối đa ba lần chạy. Checkpoint được tái sử dụng khi retry/restart và
`provider_calls` đếm từng attempt thật. Crash sau provider trả nhưng trước khi
commit checkpoint có thể phải gọi lại; không cam kết exactly-once.

Transcript v1 đã hoàn thành vẫn đọc, đổi tên và export theo cấu trúc cũ. Job
cũ chưa hoàn thành có checkpoint không tương thích thất bại với
`LEGACY_PIPELINE_CHECKPOINT`; file nguồn và checkpoint được giữ lại. Để chạy
pipeline mới, upload lại file thành asset mới; không đổi cấu trúc dữ liệu cũ.
Job v2 từ chối checkpoint cấu hình khác bằng `JOB_CONFIGURATION_CHANGED`.

Speaker là nhãn suy luận, không xác minh danh tính và có thể gán sai. Dữ liệu
không chắc chắn cần được review; không có timestamp từng từ trong transcript v2.
Model `gpt-4o-transcribe-diarize` đã được OpenAI thông báo ngừng hoạt động ngày
26/02/2027. Đây là lựa chọn ngắn hạn; cần thay provider và kiểm thử contract
trước thời điểm đó. [Tài liệu OpenAI](https://developers.openai.com/api/docs/guides/speech-to-text#speaker-diarization).

## Kiểm thử

```sh
pnpm --filter @meeting-minutes/audio db:generate
pnpm --filter @meeting-minutes/audio test:audio
pnpm --filter @meeting-minutes/audio test:http
pnpm --filter @meeting-minutes/audio lint
pnpm --filter @meeting-minutes/audio typecheck
```

Test HTTP cần PostgreSQL và user có quyền tạo database test. Provider được thay
bằng fixture trong test code, không có chế độ mock bật qua HTTP/biến môi trường
production. Không dùng số test pass để kết luận chất lượng ASR thật.

Benchmark thật và các giới hạn dữ liệu được ghi riêng tại
[Audio validation](../../docs/audio-validation.md).
