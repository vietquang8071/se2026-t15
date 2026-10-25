# Báo cáo tiến độ audio — 25/10/2026

## Hiện tại repo đang làm gì?

Meeting Minutes Assistant hướng tới chuyển file họp thành transcript có timestamp,
nhãn người nói và biên bản gồm sáu module nghiệp vụ. Repo hiện ở giai đoạn dựng
khung ứng dụng và phát triển audio độc lập trước khi nối App/LLM.

- `apps/web`: Next.js, trang chủ vẫn là giao diện mẫu.
- `apps/api`: NestJS, controller hiện có `GET /health`.
- `packages/database`: Prisma/PostgreSQL, schema hiện chỉ có model `Meeting`.
- `apps/api/src/audio/audio-inspection.ts`: helper đọc/kiểm tra media và tách MP4;
  chưa được đăng ký thành HTTP controller/service trong `AppModule`.
- `docs`: yêu cầu sản phẩm, phân công, roadmap và contract audio dự kiến.

Phân công trong tài liệu: Sơn làm audio; Việt Quang làm LLM; App phụ trách
meeting/UI, liên kết `audio_id` và thông báo gần hết hạn.

## Phần đã có và bằng chứng

Mốc kiểm tra: nhánh `feature/son-audio-inspection`, HEAD `aac19dd`.
Sau `git fetch origin`, nhánh có 5 commit so với `origin/develop` (`e7854d5`).

| Hạng mục                                | Trạng thái                   | Bằng chứng / giới hạn                                                      |
| --------------------------------------- | ---------------------------- | -------------------------------------------------------------------------- |
| Kiểm tra WAV/MP3/M4A/WebM/MP4           | Đã có helper và test         | `inspectAudio`: extension/MIME/container/codec, decode toàn bộ audio       |
| Giới hạn nguồn 100 MB / 60 phút         | Đã kiểm tra                  | Có test đúng biên, vượt biên, file rỗng và file hỏng                       |
| Path và công cụ xử lý                   | Đã kiểm tra các case hiện có | Chặn path/symlink ngoài root; `execFile`; phân biệt thiếu tool và timeout  |
| Tách MP4                                | Đã có helper và test         | `extractAudioFromMp4`: WAV PCM 16-bit, mono, 16 kHz; giữ nguyên nguồn      |
| Offset audio trong MP4                  | Đã có helper và test         | Trả `source_audio_start_sec`; chưa có transcript để kiểm tra seek đầu cuối |
| Dọn output tách lỗi                     | Đã có test                   | Xóa thư mục trung gian khi extraction lỗi/timeout                          |
| HTTP upload và metadata theo `audio_id` | Chưa triển khai              | Contract trong `audio-service-api.md` là kế hoạch                          |
| Storage metadata / retention 30–60 ngày | Chưa triển khai              | Chưa có model Audio, migration hay scheduler                               |
| Chuẩn hóa mọi format / playback         | Chưa triển khai              | Hiện chỉ có tách MP4 thành WAV                                             |
| Job, chunking, ASR, diarization         | Chưa triển khai              | Chưa có code gọi provider hoặc lưu transcript                              |
| Tích hợp App/LLM                        | Chưa triển khai              | Chưa có luồng upload → biên bản                                            |

Không đánh dấu toàn bộ P02/P04 hoàn thành: helper chỉ đáp ứng một phần các task
P02-03, P04-01, P04-02, P04-03 và test liên quan.

## Kiểm tra thực hiện trong lần rà soát

- Compile module audio và chạy Node test runner: **29/29 pass**, không skip;
  gồm **8 test MP4**.
- ESLint `apps/api/src` và `apps/api/test`: **pass**.
- Typecheck toàn app API: **pass**.
- Đọc lại helper, test, `AppModule`, controller, Prisma schema và trang chủ.
- Môi trường chạy: Node **25.8.2**, FFmpeg/FFprobe **6.1.1**; fixture tổng hợp,
  không dùng ghi âm riêng tư.

Node mặc định trên máy là 18.19.1, thấp hơn yêu cầu repo (>=22.18); `pnpm`
chưa có trên PATH của shell kiểm tra. Lần này dùng Node có sẵn tại
`/home/sonnh/.codex/tools/nodejs/bin` và gọi trực tiếp binary workspace:

```sh
cd /home/sonnh/Documents/btvn/SE_final/se2026-t15
export PATH=/home/sonnh/.codex/tools/nodejs/bin:$PATH
node_modules/.bin/tsc -p apps/api/tsconfig.audio-test.json
node --test apps/api/test/audio/*.test.mjs
cd apps/api
../../node_modules/.bin/eslint src test
../../node_modules/.bin/tsc --noEmit -p tsconfig.json
```

Khi môi trường Node/pnpm theo README đã sẵn sàng, có thể dùng các script:

```sh
pnpm --filter @meeting-minutes/api test:audio
pnpm --filter @meeting-minutes/api lint
pnpm --filter @meeting-minutes/api typecheck
```

Chưa chạy build toàn monorepo, HTTP/database runtime, ASR provider thật,
benchmark tiếng Việt hay kiểm thử trình duyệt. Kết quả trên chỉ xác nhận phạm vi
helper và các kiểm tra tĩnh của API.

## Đợt tiếp theo: API upload/storage độc lập

Ưu tiên **P02-04 + P02-06**, kèm metadata retention của P04-05.
Tái sử dụng helper hiện có, giữ NestJS/Prisma; chưa cần nối UI/LLM.

1. Thêm model lưu media và migration: `audio_id`, storage key nội bộ, metadata
   nguồn, trạng thái, `retention_days`, `created_at`, `expires_at`.
2. Cấu hình local storage volume; tên/thư mục do server sinh, không dùng filename
   hoặc path client để quyết định vị trí ghi.
3. Thêm multipart `POST /api/audio`: bắt buộc một file và retention 30/60;
   giới hạn 100.000.000 bytes ngay khi nhận request; gọi `inspectAudio` trước
   khi công nhận asset hợp lệ.
4. Persist metadata và trả 201 + `audio_id`; dọn file tạm nếu validation hoặc
   database thất bại. Không trả absolute path ra response/lỗi.
5. Thêm `GET /api/audio/{audio_id}`: đọc metadata sau restart; ID không tồn tại
   trả 404; media hết hạn bị từ chối ngay cả khi chưa cleanup vật lý.
6. Test HTTP bằng fixture tổng hợp; kiểm tra thêm file thiếu/nhiều file, MIME
   giả, retention thiếu/sai, file lỗi/quá giới hạn, lỗi persist và dữ liệu sau restart.

**Điều kiện hoàn thành:** upload và đọc lại metadata thành công cho đủ 5 format;
file bị từ chối không để lại asset hợp lệ/file rác; expiry UTC đúng 30/60 × 24 giờ;
không lộ đường dẫn server. Upload xong chưa đồng nghĩa đã chuẩn bị WAV hoặc có ASR.

Auth/ownership cần có quyết định rõ trước khi mở service công khai. Audio API
không bắt buộc `meeting_id`; App liên kết sau.

## Các đợt sau audio

| Thứ tự | Đầu ra                                   | Điều kiện kiểm tra chính                                                                                                                                 |
| ------ | ---------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2      | Job preprocessing + chuẩn hóa các format | POST process trả 202/job_id; trạng thái lưu bền; tái dùng helper MP4, giữ nguồn/offset; lỗi không để lại output dở                                       |
| 3      | Chunking và Whisper external             | Giới hạn chunk theo bytes sau encode theo contract provider khi tích hợp; segment/word timestamps; timeout/retry có giới hạn; không tạo transcript trùng |
| 4      | Ghép transcript về nguồn                 | Timestamp nguồn = timestamp chunk + chunk offset + source audio offset; xử lý trùng overlap; test boundary và restart/retry                              |
| 5      | Diarization external                     | Chốt provider, thử audio có quyền sử dụng với 2–3 người; ghép speaker bằng timestamp, cho phép unknown; đo lỗi tự động riêng                             |
| 6      | Playback, DELETE và cleanup expiry       | Test seek về nguồn, xóa nguồn/WAV/chunk cùng asset; phối hợp job đang chạy để không tái tạo file đã xóa/hết hạn                                          |
| 7      | Bàn giao App/LLM                         | Contract và test service ổn định; App nối meeting/audio_id và thông báo theo expires_at; LLM nhận transcript có nguồn                                    |

Không cần đợi ASR mới thiết kế vòng đời xóa: từ đợt upload cần giữ storage key
và expiry nhất quán để bổ sung DELETE/cleanup an toàn. Thông báo do App sở hữu;
không tự áp chính sách xóa media sang transcript, biên bản hoặc meeting.

Trước đợt ASR cần API key/quota và mẫu tiếng Việt có quyền sử dụng kèm transcript
đối chiếu. Trước diarization cần chốt provider. Chưa có bằng chứng provider thật
hoặc đánh giá chất lượng ASR/speaker trong repo hiện tại.

## Bàn giao Git

5 commit audio hiện tại có thể gom thành một PR về `develop`, mô tả đúng phạm vi
helper + tests + tài liệu. Tiêu đề đề xuất:

`feat(audio): validate uploaded media and extract timestamped MP4 audio`

Trước khi mở PR audio, GitHub có PR #7
(`docs/son-requirements-scope` → `develop`). PR audio cần bao gồm helper, tests,
tài liệu phạm vi và báo cáo này; bổ sung link PR khi bàn giao. Không merge thay reviewer.

Tài liệu đối chiếu:
[Audio ingestion](audio-ingestion.md),
[Audio service API plan](audio-service-api.md),
[Implementation roadmap](implementation-roadmap.md),
[Contributing](../CONTRIBUTING.md).
