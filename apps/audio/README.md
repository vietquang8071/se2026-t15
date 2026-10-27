# Independent Audio API

Service NestJS riêng cho upload → chuẩn hóa → chunking → OpenAI Whisper →
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
Excel có ba sheet Transcript/Words/Metadata. PDF được render từ cùng Markdown
do service sinh ra và nhúng font tiếng Việt. Đây là **bản chép lời**, chưa phải
biên bản sáu module của LLM.

File đã tải về máy nằm ngoài vòng đời dữ liệu của server; DELETE/expiry trên
server không xóa các bản download của client. Không commit audio/transcript thật.

## API

`GET /health` không cần key; các route `/api/audio` đều cần header `X-API-Key`.
Xem [contract đầy đủ](../../docs/audio-service-api.md), bao gồm lỗi và timestamp.

Upload giới hạn 100.000.000 bytes / 3.600 giây, WAV/MP3/M4A/WebM/MP4. Chỉ upload,
không thu âm trình duyệt. `retention_days` bắt buộc là 30 hoặc 60. Hạn gốc áp dụng
nguồn, WAV, chunk, checkpoint và **transcript**; không gia hạn khi đọc/xử lý lại.
App chịu trách nhiệm thông báo gần hạn.

## Pipeline và giới hạn

1. Upload kiểm tra container/MIME/codec, một audio track và full decode trước persist.
2. POST process trả 202 + job_id. Mỗi audio có một job, gọi lặp trả cùng ID.
3. Worker tạo WAV PCM16 mono/16 kHz, giữ nguồn. Nguồn MP4 giữ audio start offset.
4. Whisper nhận MP3 64 kbps theo chunk (mặc định 600 giây, context overlap 2 giây).
   Kiểm tra **bytes sau encode** dưới 24 MB, không dựa riêng thời lượng.
5. Diarization nhận MP3 32 kbps của toàn cuộc họp, dưới 24 MB với giới hạn nguồn
   60 phút. Một lần gọi toàn nguồn giữ speaker ID nhất quán giữa các chunk ASR.
6. Ghép từ theo core interval không chồng, cộng chunk offset và audio start offset
   về source. Speaker gán theo overlap thời gian; vùng không rõ dùng `unknown`.
   Segment cuối được nhóm lại theo speaker, khoảng nghỉ và độ dài; không giả
   danh đó là nguyên xi segmentation của Whisper.
7. Lưu kết quả trong PostgreSQL; các bản export sinh từ transcript hiện tại,
   nên sửa tên speaker phản ánh vào mọi định dạng.

Provider có timeout mặc định Whisper 180 giây, diarization 600 giây/request;
`OPENAI_TIMEOUT_MS` có thể override cả hai (tối đa 600 giây). Tối đa ba lần gọi cho lỗi
network/429/5xx. Auth/quota/request lỗi không retry âm thầm. Job thất bại được
gọi process lại, tối đa ba lần chạy tổng cộng. Checkpoint từng chunk/diarization
được lưu DB; retry/restart tái dùng kết quả đã persist. Provider calls là tổng
số attempt thực tế. Crash sau provider trả nhưng trước khi commit checkpoint
có thể cần gọi lại; không cam kết exactly-once ở phía provider.

Không đổi model/chunk/overlap giữa các lượt retry của cùng job; service từ chối
checkpoint khác cấu hình bằng `JOB_CONFIGURATION_CHANGED`. Nếu muốn thử cấu hình
mới, upload thành asset mới để giữ nguồn gốc kết quả rõ ràng.

Giới hạn chất lượng: cắt theo thời gian có thể sai/mất/trùng từ ở biên khi model
cho timestamp khác nhau; overlap chỉ giảm rủi ro, không bảo đảm đúng tuyệt đối.
Speaker là nhãn suy luận, không xác minh danh tính. Chưa xử lý voiceprint hoặc
âm thanh chồng tiếng bằng model local. Giữ `unknown` khi không đủ bằng chứng.

Mặc định dùng `whisper-1` và `gpt-4o-transcribe-diarize` theo contract hiện tại.
Tài liệu OpenAI ngày rà soát thông báo shutdown ngày 26/02/2027; cần thay đổi
provider contract có kiểm thử trước mốc đó, không chỉ đổi tên model tùy ý vì
response/timestamp có thể khác. [Nguồn chính thức](https://developers.openai.com/api/docs/guides/speech-to-text).

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
