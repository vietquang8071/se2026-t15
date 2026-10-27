# Audio — kết quả kiểm tra 25/10/2026

## Kiểm tra sau khi chuyển vào apps — 27/10/2026

- Audio service được chuyển từ `services/audio` vào `apps/audio`; API, database
  và storage vẫn độc lập, chưa nối frontend hoặc LLM.
- Build, lint, typecheck, 40 test audio và 12 test HTTP đều pass. Test HTTP dùng
  PostgreSQL thật và provider giả; không coi đó là kiểm tra provider thật.
- Kiểm tra riêng với provider thật trên 60 giây đầu của mẫu VietMed ghép mô tả
  bên dưới: job hoàn thành trong khoảng 47 giây, 2 provider calls; transcript
  có 17 segment, 261 word timestamps và không có word timestamp ngoài khoảng
  audio. Một số từ có speaker `unknown`.
- Đã tải được JSON, TXT, SRT, Markdown, XLSX và PDF; đọc lại các sheet Excel và
  trích được chữ từ PDF. Kết quả là transcript, không phải biên bản LLM.
- Đây là một lần chạy trên một mẫu ghép, không chứng minh độ ổn định hoặc chất
  lượng tổng quát. Kết quả riêng lưu tại `artifacts/private/audio-move-check-result`,
  không đưa transcript vào Git.

## Phạm vi đã triển khai

Service độc lập `apps/audio`, port 3002, database `meeting_minutes_audio`,
schema/migration và storage riêng. App API không chứa endpoint audio.

Đã có upload 5 định dạng, kiểm tra metadata/decode, chuẩn hóa/chunking, job có
checkpoint và retry/restart, OpenAI Whisper + diarization, transcript theo từ/
segment/speaker, sửa tên speaker, media Range, export JSON/TXT/SRT/MD/XLSX/PDF,
DELETE và expiry 30/60 ngày **xóa cả transcript/checkpoint**.

App/LLM, thông báo, auth người dùng và biên bản sáu module vẫn thuộc đợt tích hợp
sau. Đây là hoàn thành phạm vi service audio, không phải nghiệm thu toàn sản phẩm.

## Kiểm tra chức năng

| Nhóm                                                    | Kết quả                                                           |
| ------------------------------------------------------- | ----------------------------------------------------------------- |
| Helper/FFmpeg/chunk/provider contract/transcript/export | **40/40 pass**, không skip                                        |
| HTTP với PostgreSQL riêng, provider giả                 | **12/12 pass**, không skip                                        |
| Lint/build/typecheck toàn workspace                     | Pass                                                              |
| Docker build độc lập                                    | Pass                                                              |
| Docker health/upload/source Range/delete                | Pass trên cổng kiểm tra 3003                                      |
| Provider thật                                           | Hoàn thành mẫu tiếng Việt 604,2 giây                              |
| File xuất thật                                          | Đủ 6 định dạng; XLSX đọc lại được, PDF trích xuất được tiếng Việt |

Test HTTP gồm: auth, năm format, UTC 30/60 ngày, file thiếu/sai, path không lộ,
đúng biên 100 MB và vượt biên, process đồng thời/idempotent, sửa speaker,
download/export, Range, persist qua restart, retry tái dùng checkpoint,
expiry xóa transcript, DELETE khi provider đang chạy, khôi phục running job,
chặn đổi cấu hình checkpoint, giới hạn retry và singleton worker lock.

Môi trường local: Node 25.8.2, FFmpeg/FFprobe 6.1.1, PostgreSQL 17.
Docker: Node 24, FFmpeg 5.1.x từ Debian, PostgreSQL 17. Không yêu cầu GPU local.
Test provider contract dùng stub có kiểm soát, không được tính là provider thật.

## Dữ liệu kiểm thử thật

Nguồn người dùng đưa: [Twine Vietnamese General Conversation](https://www.twine.net/dataset/vietnamese-general-conversation-data).
Trang này chỉ có request sample/quote, link download trỏ `#`. Sau khi người dùng
đồng ý nguồn công khai khác, dùng [VietMed của tác giả](https://huggingface.co/datasets/leduckhai/VietMed),
split dev, dataset card khai báo MIT; [repo tác giả](https://github.com/leduckhai/MultiMed/tree/master/VietMed).

- Tạo mẫu **604,2 giây** từ **96 clip**, hai người `VietMed_006_a`/`VietMed_006_b`.
- Giữ thứ tự số clip riêng từng speaker, luân phiên block 5 clip, gap 0,2 giây;
  không lặp utterance, không chèn lời TTS.
- Đây là **mẫu ghép hai người nói**, không phải hội thoại liên tục nguyên bản;
  domain y tế, một recording gốc, audio điện thoại 8 kHz.
- SHA256 parquet nguồn: `ddbce77039a150053a3a6dbe7c92c8f07a7924537a4681a1a1788aa2f917b18b`.
- Manifest từng clip, gold text/speaker/timeline và toàn bộ kết quả ở
  `artifacts/private`, đã gitignore. Không commit recording/transcript thật.

Script tái tạo: `apps/audio/scripts/prepare-vietmed.py` (Python với
numpy/pyarrow/soundfile). Đánh giá: `apps/audio/scripts/evaluate-vietmed.py`.
Đường dẫn mặc định chạy từ root repo:

```sh
python3 apps/audio/scripts/prepare-vietmed.py
pnpm audio:file artifacts/private/vietmed/conversation-10min.wav artifacts/private/audio-result
python3 apps/audio/scripts/evaluate-vietmed.py
```

## Kết quả chất lượng mẫu này

| Chỉ số                                                   | Kết quả                     |
| -------------------------------------------------------- | --------------------------- |
| Model transcription                                      | `whisper-1`                 |
| Model diarization                                        | `gpt-4o-transcribe-diarize` |
| Gold whitespace tokens                                   | 2.583                       |
| Output whitespace tokens / word entries                  | 2.397                       |
| WER theo token cách nhau bằng khoảng trắng               | **19,28%**                  |
| CER (không tính khoảng trắng)                            | **14,89%**                  |
| Nhãn speaker được model phát hiện                        | 2                           |
| Speaker agreement tại midpoint từ có gold clip tương ứng | **84,10%** trên 2.340 từ    |
| Từ chưa rõ speaker trong 2.340 từ đối chiếu              | 48                          |
| Word timestamp ngoài `[0, duration]` hoặc đảo chiều      | 0                           |
| Segment sau ghép                                         | 101                         |

Chuẩn hóa WER/CER: Unicode NFC, lowercase, punctuation → spaces, gộp khoảng
trắng, giữ dấu tiếng Việt; CER bỏ khoảng trắng. Whitespace-token WER tiếng Việt
thường gần mức âm tiết, không phải word segmentation ngôn ngữ học.

Speaker mapping tối ưu sau inference để bỏ khác biệt tên nhãn. Điểm speaker dùng
metadata clip tại midpoint **từ đã nhận dạng**, bỏ qua gap; không có gold VAD/turn
liên tục, không phạt từ bị ASR bỏ mất. Vì vậy **84,10% không phải DER hoặc độ
chính xác speaker tổng quát**. Không dùng phép so sánh này để suy ra chất lượng
cuộc họp tự nhiên/chồng tiếng hoặc nhận diện danh tính.

Trước khi sửa xử lý từ có timestamp start=end, speaker score cùng dữ liệu là
77,74%, 228 từ unknown. Bản cuối giữ timestamp, dùng point containment với một
turn duy nhất; vùng nhiều turn vẫn unknown. Không thay đổi gold, audio hoặc
Whisper text/timing. Đây là sửa quy tắc hợp lệ cho zero-duration words, được test
riêng; mẫu này đã được dùng debug nên cần một tập holdout khác trước nghiệm thu.

**Kết luận chất lượng:** pipeline chạy đầy đủ nhưng transcript vẫn cần nghe/sửa;
WER 19,28% chưa phù hợp để coi văn bản tự động là hoàn toàn chính xác. Chưa có
ngưỡng chất lượng được chốt trước test. Chưa đo DER/WER trên tập holdout hoặc
benchmark đủ nhiều vùng miền, tiếng ồn và họp tự nhiên.

## Latency, retry và bằng chứng provider

- Audio ID: `90b47720-e48e-441b-92dd-44dbc6e1d07f`.
- Job ID: `bdd17939-a344-4c3e-8f8a-0fcabea010d9`.
- Queue lúc `2026-10-25T11:39:42.262Z`, hoàn thành provider lần đầu
  `2026-10-25T11:51:24.321Z`: khoảng **11 phút 42 giây**, gồm timeout/retry và
  restart chủ động; không phải baseline inference latency ổn định.
- Job ghi nhận **6 provider attempts**: hai request Whisper cho hai chunk,
  bốn attempt diarization (có timeout/hủy trước khi thành công).
- Timeout diarization 180 giây không đủ trong lần chạy này; bản cuối mặc định
  diarization 600 giây, Whisper 180 giây, override tối đa 600 giây.
- Hai lượt chạy job để hoàn thành provider; lượt thứ ba chỉ rebuild từ checkpoint
  sau sửa zero-duration mapping, **không gọi provider thêm**, count vẫn 6.
- Có thêm **một diagnostic diarization 30 giây** ngoài job: HTTP 200, 15,506 giây,
  request ID `req_7571bcd4fd7d42efb7afea5826fbc743`. Tổng thí nghiệm gồm 7 attempt,
  không được báo chỉ có các request thành công.
- Chưa có số tiền billing xác nhận; không suy ra chi phí thực tế từ test count.

Không tự retry lại toàn bộ mẫu thật để cải thiện số đo latency. Checkpoint nằm
trong DB và sẽ bị xóa cùng audio; các bản download/manifest local là artifact
kiểm thử riêng, server không tự xóa được bản client đã tải.

## Giới hạn bàn giao

- Chỉ một instance worker/database/storage, phù hợp demo/dev nội bộ; không scale
  ngang hoặc cam kết exactly-once provider.
- Biên chunk, từ zero-duration, tiếng nói chồng và nhãn unknown cần review.
- API key service không thay thế auth/ownership của App và HTTPS khi public.
- File nguồn tối đa 100 MB/60 phút; chưa benchmark thực tế file dài 60 phút qua
  provider. Biên duration/bytes và multi-chunk đã có test local.
- OpenAI thông báo vòng đời hai model hiện dùng đến 26/02/2027; cần kế hoạch
  thay provider contract trước mốc đó. [Tài liệu OpenAI](https://developers.openai.com/api/docs/guides/speech-to-text).
