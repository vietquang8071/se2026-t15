# Hợp đồng API của LLM Service

**Phiên bản hợp đồng:** 1.0 · **Trạng thái:** Đề xuất thiết kế; chưa được triển khai trong repository · **Phạm vi:** Giao tiếp REST/JSON giữa Web Backend và LLM Service

## Mục lục

1. [Mục đích và trạng thái hiện tại](#1-mục-đích-và-trạng-thái-hiện-tại)
2. [HTTP API](#2-http-api)
3. [Request schema](#3-request-schema)
4. [Response schema](#4-response-schema)
5. [Quy tắc sáu business modules](#5-quy-tắc-sáu-business-modules)
6. [Temporal resolution](#6-temporal-resolution)
7. [Source grounding](#7-source-grounding)
8. [Error contract](#8-error-contract)
9. [Contract examples](#9-contract-examples)
10. [Contract test cases và acceptance criteria](#10-contract-test-cases-và-acceptance-criteria)
11. [Open questions và mâu thuẫn cần thống nhất](#11-open-questions-và-mâu-thuẫn-cần-thống-nhất)

## 1. Mục đích và trạng thái hiện tại

Tài liệu này định nghĩa request và response của LLM Service v1 để Web Backend, Audio Processing Service và LLM Service có thể phát triển độc lập. Request nhận transcript đã được chuẩn hóa; service không nhận audio, không chạy ASR/diarization và không truy cập PostgreSQL.

Tại commit hiện tại, repository chưa có implementation trong `apps/llm-service`. `apps/api` là NestJS skeleton với `GET /health`; Prisma hiện chỉ có model `Meeting` gồm `id`, `title`, `anchorDate` và timestamps. Không tìm thấy `docs/api-contract.md` trong working tree hoặc lịch sử của các branch local hiện có. Vì vậy, endpoint, schema, error envelope và phần mở rộng bên dưới là thiết kế mới, không phải API đang chạy.

Tài liệu liên quan:

- [Product Description](../../../docs/product-description.md)
- [Feature Overview](../../../docs/feature-overview.md)
- [Implementation Roadmap](../../../docs/implementation-roadmap.md)
- [README](../../../README.md)
- [AGENTS.md](../../../AGENTS.md)
- [Prisma schema hiện tại](../../../packages/database/prisma/schema.prisma)
- [API controller hiện tại](../../../apps/api/src/app.controller.ts)
- [Kiến trúc LLM Service](./llm-service-architecture.md)

## 2. HTTP API

### 2.1 Endpoint

Các endpoint dưới đây thuộc LLM Service. Chúng có base URL và process riêng với NestJS API, dù cùng dùng đường dẫn `/health`.

| Method | Path | Mục đích | Thành công |
|---|---|---|---|
| GET | `/health` | Kiểm tra process và cấu hình cơ bản; không gọi provider | `200 OK` |
| POST | `/v1/extractions` | Trích xuất đồng bộ các module được yêu cầu | `200 OK` |
| GET | `/openapi.json` | OpenAPI schema do FastAPI sinh từ Pydantic models | `200 OK` |

`GET /health` của LLM Service không phải bằng chứng provider đang hoạt động; endpoint không gửi request thử tới LLM provider. API Nest hiện cũng có `GET /health` nhưng trả `{"status":"ok","service":"api"}` và chỉ dành cho service đó.

Response health đề xuất:

~~~json
{
  "status": "ok",
  "service": "llm-service",
  "contract_version": "1.0"
}
~~~

### 2.2 HTTP semantics và content

- Request và response sử dụng UTF-8 JSON.
- `POST /v1/extractions` yêu cầu `Content-Type: application/json`; client nên gửi `Accept: application/json`.
- Request xử lý đồng bộ tại ranh giới service: giữ kết nối HTTP cho đến khi mọi module được yêu cầu hoàn tất hoặc request thất bại.
- Thành công chỉ trả `200`; service không tạo job, queue, database record hay endpoint polling riêng. Web Backend tạo job và gọi LLM Service trong background job của Web.
- Request chỉ thành công nếu mọi module trong `requested_modules` có kết quả hợp lệ. Service không trả extraction thành công khi một module được yêu cầu bị lỗi.
- `GET /openapi.json` phản ánh schema đang triển khai. Schema này phải được kiểm tra trong contract tests trước khi Web Backend tích hợp.

### 2.3 Versioning

- Path `/v1` xác định major API version.
- `contract_version` trong body phải bằng `"1.0"` ở contract này. Trường giúp phát hiện fixture/client không tương thích; nó không thay thế version trong path.
- Thêm field optional hoặc enum value tương thích có thể giữ `/v1`, sau khi cập nhật OpenAPI và contract tests.
- Đổi kiểu field, đổi ý nghĩa `null`, hoặc đổi cách xác định module là breaking change: tạo `/v2`, không âm thầm thay đổi `/v1`.
- `requested_modules` phải liệt kê rõ module; không có giá trị `all` hoặc mặc định ngầm.

### 2.4 Authentication giữa service

Đề xuất dùng bearer token riêng giữa Web Backend và LLM Service:

~~~http
Authorization: Bearer <LLM_SERVICE_TOKEN>
~~~

Token phải được cấp từ secret store/environment của deployment, so sánh an toàn, có quy trình rotate và không được ghi log. Production chỉ expose LLM Service trên network nội bộ có TLS tại boundary phù hợp; không public endpoint trích xuất trực tiếp. `GET /health` có thể không yêu cầu token nhưng chỉ mở trong network nội bộ/health-check path.

`401` nghĩa token thiếu hoặc sai; `403` nghĩa caller đã xác thực nhưng chưa được phép gọi. Đây là đề xuất; repository hiện chưa có service-to-service auth convention.

### 2.5 Timeout, retry và idempotency

Web Backend sở hữu lifecycle, retry và deduplication của job. LLM Service không giữ trạng thái giữa các request.

- Deployment phải cấu hình `provider_timeout_seconds` và `request_timeout_seconds`. Request budget bao gồm mọi provider call, evidence verification và một lần structured-output repair nếu có.
- Giá trị khởi đầu đề xuất, chưa phải SLA được phê duyệt: provider call tối đa 60 giây; toàn request tối đa 180 giây; HTTP client của Web chờ ít nhất 190 giây. Điều chỉnh bằng benchmark P11.
- Khi budget hết, trả `504 PROVIDER_TIMEOUT` hoặc `504 REQUEST_TIMEOUT`; không trả extraction một phần dưới dạng thành công.
- Khi provider rate-limit, ánh xạ thành `503 PROVIDER_RATE_LIMIT`, kèm `Retry-After` nếu provider có thông tin an toàn để chuyển tiếp.
- Web chỉ retry lỗi transient được đánh dấu `retryable: true`, dùng exponential backoff có jitter, giới hạn theo job policy và tôn trọng `Retry-After`. Không retry lỗi input, version, payload hay evidence không an toàn.
- `request_id` do Web tạo và giữ nguyên qua các lần retry của cùng một logical extraction. Đây là correlation identifier, không phải idempotency key.
- Vì LLM Service stateless, gửi lại cùng `request_id` vẫn có thể gọi provider và phát sinh chi phí lần nữa. Web phải dedupe job theo tối thiểu `meeting.id`, `transcript.revision_id`, module set và extraction config; không chạy đồng thời hai job giống nhau; không ghi kết quả trùng sau khi đã hoàn tất.
- Nếu HTTP timeout xảy ra sau khi provider đã xử lý nhưng trước khi client nhận response, kết quả lần gọi đó không thể tra lại ở LLM Service. Web có thể retry trong job policy nhưng phải chấp nhận khả năng provider xử lý hai lần.

### 2.6 Giới hạn request và transcript dài

- Giới hạn byte của body phải cấu hình theo deployment và được công bố trong mô tả OpenAPI. Vượt ngưỡng trả `413 PAYLOAD_TOO_LARGE`; client không retry nguyên payload.
- Transcript được kiểm tra token budget trước khi gọi provider. Transcript vượt context window phải được chia theo segment boundaries và tổng hợp theo chiến lược ở [Architecture](./llm-service-architecture.md#16-chiến-lược-transcript-dài).
- Nếu transcript vượt giới hạn body hoặc giới hạn xử lý đã cấu hình, hoặc không thể xử lý trong request budget sau khi chia cửa sổ, trả `413 TRANSCRIPT_TOO_LONG`. Không cắt bỏ transcript âm thầm và không retry payload nguyên trạng.
- Không có giới hạn token cố định trong contract vì model/provider chưa được nhóm chọn. Provider adapter phải cung cấp context limit; deployment phải cấu hình hard limit trước khi nhận traffic.
- Client không tự chia transcript thành các request độc lập để thay cho LLM Service: cách đó có thể làm mất deduplication, ngữ cảnh toàn cuộc họp và tính nhất quán temporal.

## 3. Request schema

### 3.1 Request mẫu đầy đủ

~~~json
{
  "contract_version": "1.0",
  "request_id": "req-20261005-001",
  "meeting": {
    "id": "meeting-42",
    "title": "Sprint planning",
    "anchor_date": "2026-10-05",
    "timezone": "Asia/Ho_Chi_Minh",
    "duration_seconds": 1900.5,
    "participants": [
      {
        "id": "participant-alex",
        "display_name": "Alex",
        "speaker_ids": ["speaker_1"]
      },
      {
        "id": "participant-maria",
        "display_name": "Maria",
        "speaker_ids": ["speaker_2"]
      }
    ]
  },
  "transcript": {
    "revision_id": "transcript-r3",
    "language": "vi-VN",
    "segments": [
      {
        "id": "seg-001",
        "start": 852.0,
        "end": 857.4,
        "speaker_id": "speaker_1",
        "text": "Tôi sẽ hoàn thiện bản OpenAPI trước thứ Sáu này."
      },
      {
        "id": "seg-002",
        "start": 858.0,
        "end": 862.1,
        "speaker_id": "speaker_2",
        "text": "Chốt dùng whisper-1 cho bản MVP vì có timestamp và triển khai nhanh."
      },
      {
        "id": "seg-003",
        "start": 900.0,
        "end": 905.2,
        "speaker_id": "speaker_1",
        "text": "Tuần sau deploy bản thử nghiệm."
      },
      {
        "id": "seg-004",
        "start": 1100.0,
        "end": 1103.5,
        "speaker_id": "speaker_2",
        "text": "Cuối tháng gửi báo cáo chất lượng."
      },
      {
        "id": "seg-005",
        "start": 1120.0,
        "end": 1125.0,
        "speaker_id": "speaker_1",
        "text": "Chưa biết diarization xử lý hai người nói cùng lúc thế nào."
      },
      {
        "id": "seg-006",
        "start": 1150.0,
        "end": 1153.0,
        "speaker_id": "speaker_2",
        "text": "Tuần sau, sau khi có bộ dữ liệu, kiểm tra lại độ chính xác diarization."
      },
      {
        "id": "seg-007",
        "start": 1200.0,
        "end": 1204.0,
        "speaker_id": "speaker_1",
        "text": "Thứ Sáu này demo bản MVP cho nhóm."
      }
    ]
  },
  "extraction": {
    "output_language": "vi",
    "requested_modules": [
      "meeting_summary",
      "action_items",
      "decision_log",
      "open_issues",
      "follow_up_items",
      "timeline_events"
    ]
  }
}
~~~

### 3.2 Field definitions

#### Request metadata

| Field | Type | Bắt buộc | Ràng buộc và ý nghĩa |
|---|---|---:|---|
| `contract_version` | string | Có | Giá trị `"1.0"`; version không hỗ trợ trả `400 UNSUPPORTED_CONTRACT_VERSION`. |
| `request_id` | string | Có | Caller-generated, 1–128 ký tự; không chứa transcript hay dữ liệu cá nhân; ổn định qua retry của cùng logical job. |

#### Meeting context

| Field | Type | Bắt buộc | Ràng buộc và ý nghĩa |
|---|---|---:|---|
| `meeting.id` | string | Có | Opaque ID do Web Backend cấp, 1–128 ký tự. Không dùng làm bằng chứng nội dung. |
| `meeting.title` | string | Có | Trimmed, 1–200 ký tự; metadata từ meeting, không để model tự viết lại. |
| `meeting.anchor_date` | string/date | Có | Ngày dân sự địa phương theo `YYYY-MM-DD`; bắt buộc để resolve thời gian tương đối. Không phải thời điểm bắt đầu audio. |
| `meeting.timezone` | string | Có | Tên IANA như `Asia/Ho_Chi_Minh`; không nhận offset mơ hồ như `UTC+7`. |
| `meeting.duration_seconds` | number | Có | Finite, lớn hơn 0; thời lượng transcript gốc theo giây. |
| `meeting.participants` | array | Có | Có thể là `[]` nếu chưa có danh sách đã xác nhận. Mỗi phần tử theo bảng participant bên dưới. |

| Participant field | Type | Bắt buộc | Ràng buộc và ý nghĩa |
|---|---|---:|---|
| `id` | string | Có | ID duy nhất trong meeting, 1–128 ký tự. |
| `display_name` | string | Có | Tên đã biết từ metadata, 1–200 ký tự; không được LLM tự suy đoán. |
| `speaker_ids` | string array | Có | Mapping đã được Web xác nhận; dùng `[]` khi chưa map. Một `speaker_id` không được map sang hai participant khác nhau. |

#### Transcript

| Field | Type | Bắt buộc | Ràng buộc và ý nghĩa |
|---|---|---:|---|
| `transcript.revision_id` | string | Có | ID bất biến cho đúng revision transcript này, 1–128 ký tự. Khi sửa transcript phải tạo revision mới. |
| `transcript.language` | string | Có | BCP-47, ví dụ `vi`, `vi-VN`, `en`, `en-US`; dùng `mul` nếu transcript trộn ngôn ngữ và không có một ngôn ngữ chính. |
| `transcript.segments` | array | Có | Tối thiểu một segment có text speech; nếu rỗng hoặc chỉ có text trắng trả `422 EMPTY_TRANSCRIPT`. |
| `segments[].id` | string | Có | ID duy nhất trong revision, 1–128 ký tự; giữ nguyên khi trích xuất. |
| `segments[].start` | number | Có | Số giây tính từ đầu audio gốc, finite và `>= 0`. |
| `segments[].end` | number | Có | Số giây tính từ đầu audio gốc, finite, lớn hơn `start` và `<= duration_seconds`. |
| `segments[].speaker_id` | string hoặc null | Có | ID opaque do Audio Processing Service cấp, ổn định trong transcript revision; `null` nghĩa chưa biết/không gán được. Không đồng nghĩa với danh tính participant. |
| `segments[].text` | string | Có | Nội dung transcript đã normalize, trim và không rỗng. Đây là text evidence; giữ nguyên ý và không gửi ASR provider payload/raw audio. |

Timestamp là giây dạng số thực trên audio gốc sau khi Audio Processing Service đã cộng offset khi stitch các chunk. Segment phải được gửi theo `start` không giảm dần. Segment overlap được chấp nhận vì hai speaker có thể nói đồng thời; overlap tự nó không phải validation error. Segment ID trùng, thời gian âm, `end <= start`, `end` vượt duration hoặc thứ tự không hợp lệ trả `400 VALIDATION_ERROR`.

Speaker thiếu được biểu diễn bằng `speaker_id: null`; không được tự tạo speaker hoặc gán participant dựa trên suy đoán ngôn ngữ. Speaker chưa map nhưng có ID vẫn hợp lệ. Nếu `speaker_id` có mapping trong participant, đó là mapping do Web Backend/Audio Processing Service xác nhận, không phải suy luận của LLM.

#### Extraction configuration

| Field | Type | Bắt buộc | Ràng buộc và ý nghĩa |
|---|---|---:|---|
| `extraction.output_language` | string | Có | MVP hỗ trợ `vi` hoặc `en`; field xác định ngôn ngữ văn bản artifact, không dịch transcript gốc. |
| `extraction.requested_modules` | string array | Có | Từ 1 đến 6 giá trị duy nhất trong enum dưới đây; không cho phép mảng rỗng hoặc giá trị `all`. |

Enum module: `meeting_summary`, `action_items`, `decision_log`, `open_issues`, `follow_up_items`, `timeline_events`.

### 3.3 Quy tắc validation tổng quát

- Field không được khai báo trong contract bị từ chối để tránh typo âm thầm; thay đổi tương thích phải đi kèm version/schema update.
- `request_id`, meeting ID, revision ID, participant ID và segment ID không được rỗng hoặc trùng trong phạm vi được quy định.
- `speaker_id` có thể null; segment text không thể null.
- Timestamps luôn thuộc bản ghi âm gốc, không phải thời gian tương đối trong audio chunk.
- Request hợp lệ không bảo đảm nội dung extraction thành công; provider, structured output và evidence được xử lý riêng theo error contract.
- Không nhận audio bytes, file path, diarization raw response, provider-specific ASR JSON hoặc database IDs của artifact trong request.

## 4. Response schema

### 4.1 Response thành công

`200 OK` chỉ được trả khi mọi module được yêu cầu đã chạy và response đã qua kiểm tra schema, temporal resolution và evidence checks.

~~~json
{
  "contract_version": "1.0",
  "request_id": "req-20261005-001",
  "status": "completed",
  "meeting_id": "meeting-42",
  "transcript_revision_id": "transcript-r3",
  "requested_modules": [
    "meeting_summary",
    "action_items",
    "decision_log",
    "open_issues",
    "follow_up_items",
    "timeline_events"
  ],
  "modules": {
    "meeting_summary": {},
    "action_items": [],
    "decision_log": [],
    "open_issues": [],
    "follow_up_items": [],
    "timeline_events": []
  },
  "processing": {
    "provider": "example-provider",
    "model_id": "example-model",
    "prompt_version": "extract-v1.0",
    "evidence_prompt_version": "evidence-v1.0",
    "started_at": "2026-10-05T09:00:00Z",
    "completed_at": "2026-10-05T09:00:03Z",
    "token_usage": {
      "input_tokens": 1200,
      "output_tokens": 500
    }
  }
}
~~~

Trong schema thực, object `meeting_summary` phải có đầy đủ field theo mục 5; `{}` ở đây chỉ minh họa vị trí module.

| Field | Type | Bắt buộc | Ý nghĩa |
|---|---|---:|---|
| `contract_version` | string | Có | `"1.0"`. |
| `request_id` | string | Có | Echo đúng ID trong request. |
| `status` | string | Có | Với HTTP 200 luôn bằng `"completed"`; không có `"partial"` hoặc `"failed"` trong success body. |
| `meeting_id` | string | Có | Echo `meeting.id`. |
| `transcript_revision_id` | string | Có | Echo đúng revision đã trích xuất. |
| `requested_modules` | string array | Có | Echo đúng tập module của request, giữ thứ tự request. |
| `modules` | object | Có | Luôn có đủ sáu key module; semantics theo mục 4.2. |
| `processing` | object | Có | Metadata giúp tái lập extraction; không chứa prompt bí mật, transcript hoặc chain-of-thought. |

`processing.provider`, `model_id`, `prompt_version` và `evidence_prompt_version` là bắt buộc. Verifier prompt version không thể null trong response thành công vì semantic evidence verification thuộc contract. Timestamp RFC 3339 UTC. `token_usage` là object hoặc null nếu provider không trả usage; nếu có, hai giá trị token phải là số nguyên không âm.

### 4.2 Module state, empty và null

| Giá trị | Ý nghĩa |
|---|---|
| List `[]` | Module đã được yêu cầu, chạy thành công, nhưng không tìm thấy item phù hợp. Đây là kết quả rỗng hợp lệ. |
| List có item | Module đã chạy; mỗi item phải thỏa schema và source-grounding rules. Item còn bất định có `needs_review: true`. |
| `null` | Module chưa chạy hoặc không có kết quả dùng được. Trong response thành công, chỉ module không có trong `requested_modules` mới được null; nếu module được yêu cầu nhưng không có kết quả dùng được, toàn request phải trả non-2xx error envelope. `requested_modules` phân biệt module không chạy với processing failure. |
| Processing failure | Không trả HTTP 200. Trả error envelope; không biểu diễn module lỗi bằng `[]` hoặc coi `null` là extraction thành công. |

Nếu module được yêu cầu nhưng không sinh được kết quả có thể dùng theo contract, toàn request thất bại bằng error code phù hợp. Không được trả `null` cho requested module trong response `status: "completed"`. `needs_review: true` dùng cho artifact có nội dung và evidence có thể dẫn tới nguồn nhưng cần người xác nhận; nó không thay thế processing failure khi output sai schema hoặc không có evidence hợp lệ.

### 4.3 Processing IDs và thứ tự

- `ACT-001`, `DEC-001`, `ISS-001`, `FLW-001`, `EVT-001` là ID hiển thị trong một response; service gán sau validation, không để model tự chọn ID.
- ID được gán sau khi sort từng module và đánh số liên tục theo đúng thứ tự item được trả về; đây không phải durable database ID. Web Backend tạo/persist ID riêng.
- `source_timestamp` là projection để hiển thị; được tính từ `start` nhỏ nhất trong `source_segment_ids` của item, format `HH:MM:SS.mmm`. Không dùng timestamp do model tự trả.
- `source_segment_ids` là định danh evidence ổn định hơn timestamp; client nên dùng ID để tìm segment rồi seek audio bằng `segments[].start`.
- Các list ngoài Timeline Events được xếp theo source time tăng dần. Timeline Events được xếp theo resolved date/range start, sau đó theo source time; item chưa resolve nằm sau item có ngày và được gắn review.

## 5. Quy tắc sáu business modules

Các module giữ định nghĩa trong [Product Description](../../../docs/product-description.md). Field được giữ từ schema gốc được đánh dấu **gốc**; field mới để hỗ trợ contract, nguồn hoặc trạng thái kiểm tra được đánh dấu **proposed extension**. Field nullable không có nghĩa model được phép đoán giá trị.

### 5.1 Meeting Summary

**Định nghĩa:** Tóm lược mục tiêu, chủ đề và kết quả chính để người vắng mặt hiểu cuộc họp. `title`, `date`, `duration_minutes` và `participants` lấy từ request, không do model suy ra.

| Field | Type | Bắt buộc | Quy tắc |
|---|---|---:|---|
| `title` | string | Có | **Gốc**; bằng `meeting.title`. |
| `date` | date string | Có | **Gốc**; bằng `meeting.anchor_date` theo `YYYY-MM-DD`. |
| `duration_minutes` | number | Có | **Gốc**; tính từ `duration_seconds / 60`, làm tròn 2 chữ số thập phân. |
| `participants` | string array | Có | **Gốc**; danh sách `display_name` trong request theo thứ tự; `[]` nếu không có metadata. |
| `overview` | string | Có | **Gốc**; 2–3 đoạn ngắn; mọi nhận định về thảo luận/kết quả phải có evidence ở cấp summary. |
| `key_topics` | object array | Có | **Gốc**; `[]` nếu transcript có nội dung nhưng không có topic đủ rõ. |
| `key_topics[].topic` | string | Có | **Gốc**; nhãn topic không thêm facts mới. |
| `key_topics[].brief_discussion` | string | Có | **Gốc**; tóm tắt nội dung được nói, không trình bày ý kiến như quyết định. |
| `key_topics[].source_segment_ids` | string array | Có | **Proposed extension**; segment chứng minh topic. |
| `key_topics[].needs_review` | boolean | Có | **Proposed extension**; đánh dấu mâu thuẫn hoặc diễn giải chưa chắc. |
| `key_topics[].review_reasons` | string array | Có | **Proposed extension**; mã lý do theo enum ở mục 5.8; `[]` nếu không cần review. |
| `source_segment_ids` | string array | Có | **Proposed extension**; evidence cho overview. Không dùng để dẫn nguồn metadata. |
| `needs_review` | boolean | Có | **Proposed extension**; true khi overview có claim chưa chắc nhưng vẫn hữu ích để review. |
| `review_reasons` | string array | Có | **Proposed extension**; mã lý do có kiểm soát; `[]` nếu không cần review. |

Ví dụ:

~~~json
{
  "title": "Sprint planning",
  "date": "2026-10-05",
  "duration_minutes": 31.68,
  "participants": ["Alex", "Maria"],
  "overview": "Nhóm rà soát kế hoạch demo, triển khai và chất lượng diarization. Nhóm thống nhất công nghệ được nêu trong thảo luận; thời điểm deploy vẫn chỉ được xác định trong phạm vi tuần kế tiếp.",
  "key_topics": [
    {
      "topic": "Kế hoạch demo và triển khai",
      "brief_discussion": "Nhóm dự kiến demo vào thứ Sáu và deploy bản thử nghiệm trong tuần tiếp theo.",
      "source_segment_ids": ["seg-003", "seg-007"],
      "needs_review": true,
      "review_reasons": ["date_range_needs_confirmation"]
    }
  ],
  "source_segment_ids": ["seg-001", "seg-002", "seg-003", "seg-007"],
  "needs_review": false,
  "review_reasons": []
}
~~~

### 5.2 Action Items

**Định nghĩa:** Công việc cụ thể có deliverable, được cam kết trong cuộc họp. Chỉ đưa thành Action Item khi có bằng chứng cho task. Nếu task rõ nhưng owner chưa xác định, có thể trả candidate `owner: null` và `needs_review: true`; không coi đó là task đã phân công. Đây là cách mở rộng có thể review so với tiêu chí gốc yêu cầu owner nhận diện được.

| Field | Type | Bắt buộc | Quy tắc |
|---|---|---:|---|
| `id` | string | Có | **Gốc**; ID response-local `ACT-nnn`. |
| `task` | string | Có | **Gốc**; deliverable diễn đạt rõ, không thêm scope ngoài transcript. |
| `owner` | string hoặc null | Có | **Gốc**; tên participant chỉ dùng khi mapping đã xác nhận hoặc transcript nêu rõ; role chỉ khi được nói rõ. |
| `due_date` | date string hoặc null | Có | **Gốc**; projection chỉ có ngày exact; range/unresolved/không có deadline đều là null. |
| `raw_due_expression` | string hoặc null | Có | **Proposed extension**; cụm từ gốc về hạn; null nếu không nói deadline. |
| `due_date_resolution` | TemporalResolution hoặc null | Có | **Proposed extension**; null nếu không có biểu thức thời gian; nếu có nhưng không rõ thì status `unresolved`. |
| `priority` | `High`, `Medium`, `Low` hoặc null | Có | **Gốc**; null nếu transcript không nêu hoặc không có business rule đã duyệt. |
| `source_timestamp` | string | Có | **Gốc**; tính từ segment evidence, không lấy từ model. |
| `context` | string hoặc null | Có | **Gốc**; câu giải thích ngắn, có evidence; null nếu không thêm được context. |
| `source_segment_ids` | string array | Có | **Proposed extension**; phải chứa evidence cho task và owner; có thể gồm nhiều segment. |
| `needs_review` | boolean | Có | **Proposed extension**; true nếu owner, hạn hoặc evidence cần xác nhận. |
| `review_reasons` | string array | Có | **Proposed extension**; mã lý do có kiểm soát. |

Không tự suy luận owner từ người đang phát biểu trừ khi participant-speaker mapping đã được xác nhận; “tôi” chỉ ánh xạ được qua mapping đó. Không gán priority từ ngữ khí, chức danh hoặc thời hạn. Nếu không có due expression, `raw_due_expression`, `due_date` và `due_date_resolution` đều null; nếu có expression nhưng mơ hồ, raw expression và resolution vẫn được giữ.

Ví dụ:

~~~json
[
  {
    "id": "ACT-001",
    "task": "Hoàn thiện bản OpenAPI",
    "owner": "Alex",
    "due_date": "2026-10-09",
    "raw_due_expression": "thứ Sáu này",
    "due_date_resolution": {
      "status": "exact_date",
      "resolved_date": "2026-10-09",
      "start_date": null,
      "end_date": null,
      "needs_review": false,
      "source_segment_ids": ["seg-001"]
    },
    "priority": null,
    "source_timestamp": "00:14:12.000",
    "context": null,
    "source_segment_ids": ["seg-001"],
    "needs_review": false,
    "review_reasons": []
  }
]
~~~

### 5.3 Decision Log

**Định nghĩa:** Lựa chọn đã được chốt bởi người có thẩm quyền hoặc consensus rõ ràng. Đề xuất, giả định, ý kiến cá nhân hoặc tranh luận chưa kết luận không phải decision.

| Field | Type | Bắt buộc | Quy tắc |
|---|---|---:|---|
| `id` | string | Có | **Gốc**; ID response-local `DEC-nnn`. |
| `decision` | string | Có | **Gốc**; diễn đạt lựa chọn đã chốt. |
| `rationale` | string hoặc null | Có | **Gốc**; chỉ ghi lý do đã được nói; null nếu không có. |
| `alternatives_considered` | string hoặc null | Có | **Gốc**; các lựa chọn thực sự được nhắc; null nếu không có. |
| `source_timestamp` | string | Có | **Gốc**; tính từ evidence. |
| `source_segment_ids` | string array | Có | **Proposed extension**; phải chứng minh trạng thái đã chốt; chỉ trích segment đề xuất là không đủ. |
| `needs_review` | boolean | Có | **Proposed extension**; true nếu consensus hoặc rationale chưa chắc. |
| `review_reasons` | string array | Có | **Proposed extension**; mã lý do có kiểm soát. |

Ví dụ:

~~~json
[
  {
    "id": "DEC-001",
    "decision": "Dùng whisper-1 cho bản MVP",
    "rationale": "Có timestamp và nhóm cho rằng triển khai nhanh hơn.",
    "alternatives_considered": null,
    "source_timestamp": "00:14:18.000",
    "source_segment_ids": ["seg-002"],
    "needs_review": false,
    "review_reasons": []
  }
]
~~~

### 5.4 Open Issues / Unresolved Questions

**Định nghĩa:** Câu hỏi, blocker hoặc bất đồng chưa được giải quyết. Nếu một kế hoạch cụ thể được thống nhất để xử lý vấn đề, nội dung đó có thể đồng thời là Follow-up Item nhưng phải có ý nghĩa khác và evidence riêng.

| Field | Type | Bắt buộc | Quy tắc |
|---|---|---:|---|
| `id` | string | Có | **Gốc**; ID response-local `ISS-nnn`. |
| `issue_or_question` | string | Có | **Gốc**; nêu rõ điều chưa biết/thiếu. |
| `raised_by` | string hoặc null | Có | **Gốc**; participant/role chỉ khi mapping hoặc lời nói xác nhận; nếu không rõ là null. |
| `blocker_severity` | `High`, `Medium`, `Low` hoặc null | Có | **Gốc**; null nếu không được nói rõ và chưa có rubric. |
| `status` | string | Có | **Gốc**; luôn `"Unresolved"` trong module này. |
| `source_timestamp` | string | Có | **Gốc**; tính từ evidence. |
| `source_segment_ids` | string array | Có | **Proposed extension**; hỗ trợ kiểm chứng câu hỏi/bất đồng. |
| `needs_review` | boolean | Có | **Proposed extension**; true nếu câu hỏi hoặc người nêu chưa xác định rõ. |
| `review_reasons` | string array | Có | **Proposed extension**. |

Ví dụ:

~~~json
[
  {
    "id": "ISS-001",
    "issue_or_question": "Chưa xác định diarization xử lý hai người nói đồng thời như thế nào.",
    "raised_by": "Alex",
    "blocker_severity": null,
    "status": "Unresolved",
    "source_timestamp": "00:18:40.000",
    "source_segment_ids": ["seg-005"],
    "needs_review": false,
    "review_reasons": []
  }
]
~~~

### 5.5 Follow-up Items

**Định nghĩa:** Bước điều phối, kiểm tra lại, lịch sync hoặc phụ thuộc được lên lịch để xử lý sau. Follow-up không thay thế Action Item có owner và deliverable; Open Issue mô tả vấn đề, Follow-up mô tả bước tiếp theo.

| Field | Type | Bắt buộc | Quy tắc |
|---|---|---:|---|
| `id` | string | Có | **Gốc**; ID response-local `FLW-nnn`. |
| `item` | string | Có | **Gốc**; hành động theo dõi/điểm cần quay lại. |
| `responsible_party` | string hoặc null | Có | **Gốc**; chỉ nếu được xác định; nếu không là null. |
| `target_trigger_or_date` | string hoặc null | Có | **Gốc**; biểu thức/trigger gốc như “sau khi có bộ dữ liệu”; null nếu không nêu. |
| `target_temporal_resolution` | TemporalResolution hoặc null | Có | **Proposed extension**; chỉ có khi target chứa biểu thức thời gian. |
| `source_timestamp` | string | Có | **Gốc**; tính từ evidence. |
| `source_segment_ids` | string array | Có | **Proposed extension**. |
| `needs_review` | boolean | Có | **Proposed extension**; true khi owner, trigger hoặc ngày còn cần xác nhận. |
| `review_reasons` | string array | Có | **Proposed extension**. |

Ví dụ:

~~~json
[
  {
    "id": "FLW-001",
    "item": "Kiểm tra lại độ chính xác diarization sau khi có bộ dữ liệu.",
    "responsible_party": null,
    "target_trigger_or_date": "Tuần sau, sau khi có bộ dữ liệu",
    "target_temporal_resolution": {
      "status": "date_range",
      "resolved_date": null,
      "start_date": "2026-10-12",
      "end_date": "2026-10-18",
      "needs_review": true,
      "source_segment_ids": ["seg-006"]
    },
    "source_timestamp": "00:19:10.000",
    "source_segment_ids": ["seg-006"],
    "needs_review": true,
    "review_reasons": ["date_range_needs_confirmation", "owner_unconfirmed"]
  }
]
~~~

### 5.6 Timeline / Event Extraction

**Định nghĩa:** Milestone, demo, release, deadline hoặc event dự án được nói trong cuộc họp. Không phải timeline playback/runtime của audio. Không tạo event chỉ từ metadata meeting; nội dung phải được nói và có source segment hợp lệ.

| Field | Type | Bắt buộc | Quy tắc |
|---|---|---:|---|
| `id` | string | Có | **Gốc**; ID response-local `EVT-nnn`. |
| `event` | string | Có | **Gốc**; tên event ngắn, không thêm chi tiết. |
| `resolved_date` | date string hoặc null | Có | **Gốc**; chỉ có khi resolution là `exact_date`; null với range/unresolved/không dùng được. |
| `event_type` | string | Có | **Gốc**; **proposed extension** enum `milestone`, `deadline`, `demo`, `release`, `review`, `other`. |
| `raw_statement` | string | Có | **Gốc**; đoạn phát biểu nguyên văn liên quan đến event. |
| `temporal_resolution` | TemporalResolution | Có | **Proposed extension**; trạng thái ngày exact/range/unresolved. |
| `source_timestamp` | string | Có | **Gốc**; tính từ evidence. |
| `source_segment_ids` | string array | Có | **Proposed extension**. |
| `needs_review` | boolean | Có | **Proposed extension**; true với range, unresolved hoặc evidence chưa chắc. |
| `review_reasons` | string array | Có | **Proposed extension**. |

Ví dụ:

~~~json
[
  {
    "id": "EVT-001",
    "event": "Deploy bản thử nghiệm",
    "resolved_date": null,
    "event_type": "milestone",
    "raw_statement": "Tuần sau deploy bản thử nghiệm.",
    "temporal_resolution": {
      "status": "date_range",
      "resolved_date": null,
      "start_date": "2026-10-12",
      "end_date": "2026-10-18",
      "needs_review": true,
      "source_segment_ids": ["seg-003"]
    },
    "source_timestamp": "00:15:00.000",
    "source_segment_ids": ["seg-003"],
    "needs_review": true,
    "review_reasons": ["date_range_needs_confirmation"]
  }
]
~~~

### 5.7 TemporalResolution dùng chung

`TemporalResolution` là proposed extension dùng trong Action Items, Follow-ups và Timeline Events. Field raw được giữ ở module cha: `raw_due_expression`, `target_trigger_or_date` hoặc `raw_statement`.

| Field | Type | Bắt buộc | Ý nghĩa |
|---|---|---:|---|
| `status` | string | Có | Một trong `exact_date`, `date_range`, `unresolved`. |
| `resolved_date` | date string hoặc null | Có | Ngày exact theo `YYYY-MM-DD`, chỉ có với `exact_date`. |
| `start_date` | date string hoặc null | Có | Đầu khoảng bao gồm cả ngày bắt đầu, chỉ có với `date_range`. |
| `end_date` | date string hoặc null | Có | Cuối khoảng bao gồm cả ngày kết thúc, chỉ có với `date_range`. |
| `needs_review` | boolean | Có | false chỉ khi ngày exact đã được resolve rõ; true với range/unresolved để UI không trình bày thành deadline giả. |
| `source_segment_ids` | string array | Có | Evidence của biểu thức thời gian; là subset của source IDs ở artifact. |

Invariant:

- `exact_date`: `resolved_date` có giá trị; `start_date` và `end_date` null; `needs_review` false.
- `date_range`: `resolved_date` null; cả `start_date` và `end_date` có giá trị, `start_date <= end_date`; `needs_review` true.
- `unresolved`: tất cả ngày null; `needs_review` true.
- Nếu không có biểu thức thời gian, resolution object null; không tạo object `unresolved` thay cho việc không có deadline.
- `due_date` bằng `due_date_resolution.resolved_date` chỉ ở trạng thái exact; các trạng thái khác là null.
- IDs temporal là evidence subset, không được tạo từ segment ngoài request.

### 5.8 Quy tắc chung cho mọi module

- Không tự bịa owner, due date, priority, rationale, alternatives, blocker severity hoặc danh tính speaker.
- Không đổi proposal/opinion thành decision; không đổi Open Issue thành Action Item nếu không có commitment; không đổi Follow-up thành task chỉ vì có động từ.
- Không đặt claim không có evidence vào field bình thường rồi chỉ dựa vào một confidence score. Nếu claim còn hữu ích nhưng chưa thể xác minh, gắn `needs_review: true`; nếu không có source ID hợp lệ thì bỏ claim hoặc trả processing error khi module không còn kết quả dùng được.
- `needs_review` phải bằng true khi `review_reasons` không rỗng; khi false, `review_reasons` phải là `[]`.
- Với array module, không có item phù hợp là `[]`, không phải null. Summary vẫn là object nếu được yêu cầu; metadata đã biết được copy/tính từ request.
- Các danh sách artifact ngoài Timeline Events được sort theo `source_timestamp` tăng dần. Timeline Events được sort theo ngày exact hoặc ngày bắt đầu của range, sau đó theo `source_timestamp`; item unresolved đứng sau item có ngày. ID do service gán tuần tự theo thứ tự trả về của từng module.
- `review_reasons` chỉ nhận các mã: `owner_unconfirmed`, `date_range_needs_confirmation`, `temporal_unresolved`, `evidence_unverified`, `conflicting_statements`, `speaker_unmapped` và `claim_uncertain`. Dùng mảng rỗng khi không cần review; client nên xử lý mã chưa biết theo hướng tương thích khi contract được mở rộng.

## 6. Temporal resolution

### 6.1 Nguồn ngày và timezone

- Chỉ dùng `meeting.anchor_date` làm ngày tham chiếu; tuyệt đối không dùng ngày hiện tại của server, container hoặc provider.
- `anchor_date` là ngày dân sự địa phương của cuộc họp, không có giờ.
- Calendar arithmetic thực hiện trên ngày địa phương theo `meeting.timezone` (IANA). Không đổi timezone của transcript timestamps; chúng là số giây từ đầu audio.
- `timezone` bắt buộc để diễn giải mốc ngày/giờ và đổi sang datetime ở lớp khác. v1 chỉ trả ngày; không tự tạo giờ trong ngày khi transcript không nêu.
- Nếu timezone không hợp lệ hoặc thiếu anchor date, request bị từ chối trước LLM.

### 6.2 Quy tắc resolve v1

| Biểu thức | Quy tắc |
|---|---|
| Ngày ISO hoặc ngày cụ thể có đủ ngày/tháng/năm | Parse nguyên văn; kiểm tra ngày lịch hợp lệ; trả `exact_date`. |
| “Thứ Sáu này” | Ngày thứ Sáu đầu tiên từ anchor date trở đi trong lịch địa phương; nếu anchor đã là thứ Sáu thì là cùng ngày. Với anchor `2026-10-05`, kết quả `2026-10-09`. |
| “Tuần sau” | Khoảng từ thứ Hai đến Chủ nhật của ISO week kế tiếp, inclusive. Với anchor `2026-10-05`, khoảng `2026-10-12` đến `2026-10-18`; không gán thành thứ Hai. |
| “Tuần này” | Khoảng thứ Hai–Chủ nhật chứa anchor date. |
| “Cuối tháng” | Ngày cuối cùng của tháng chứa anchor date; “cuối tháng sau” là ngày cuối tháng kế tiếp. Với anchor `2026-10-05`, ngày là `2026-10-31`. Đây là policy đề xuất dựa trên ví dụ trong tài liệu gốc. |
| “Ngày 12” không có tháng/năm | Resolve chỉ khi ngữ cảnh transcript xác định duy nhất tháng/năm; nếu không, `unresolved`. Không dùng ngày hệ thống để chọn năm. |
| Mốc thời gian mâu thuẫn hoặc không đủ thông tin | Giữ raw phrase, trả `unresolved`, tất cả date field null và `needs_review: true`. |
| Ngày không tồn tại, ví dụ 30/02 | Không tự sửa; trả `unresolved` hoặc lỗi output nếu model đã tạo date không hợp lệ. |

`date_range` biểu thị đúng độ chính xác của câu nói; không được ép thành exact date để tiện sắp lịch. Range/unresolved luôn `needs_review: true` trong v1 để UI thể hiện rõ ngày chưa được chốt.

### 6.3 Nhất quán giữa modules

LLM chỉ trích raw phrase, event/task context và source segment IDs. Python `TemporalResolver` tính calendar result. Cùng một expression trong Action Item, Follow-up và Timeline phải dùng cùng hàm resolve và cùng anchor/timezone; không để mỗi prompt tự tính một ngày khác.

Với dữ liệu mẫu `anchor_date = 2026-10-05`, `timezone = Asia/Ho_Chi_Minh`:

~~~json
{
  "status": "date_range",
  "resolved_date": null,
  "start_date": "2026-10-12",
  "end_date": "2026-10-18",
  "needs_review": true,
  "source_segment_ids": ["seg-003"]
}
~~~

Các test lịch phải có cuối tháng 2 ở năm nhuận/không nhuận, đổi tháng/năm, anchor vào đúng weekday, timezone IANA hợp lệ, range qua năm và phrase thiếu ngữ cảnh. Không đặt quality threshold cho temporal accuracy trước khi nhóm có baseline.

## 7. Source grounding

### 7.1 Ràng buộc evidence

- Artifact và từng key topic phải có `source_segment_ids` trỏ tới ID tồn tại trong `transcript.segments` của đúng request/revision.
- ID trùng, ID không tồn tại hoặc reference sang meeting/revision khác là output không hợp lệ.
- Mỗi source list không lặp ID; thứ tự theo `start` tăng dần. Temporal source IDs phải là subset evidence của artifact chứa nó.
- `source_timestamp` được service tính bằng `min(segments[id].start)` rồi format `HH:MM:SS.mmm`; không chấp nhận timestamp do LLM tự tính.
- ID tồn tại chỉ chứng minh reference hợp lệ về mặt cấu trúc, không chứng minh câu nói hỗ trợ claim về nghĩa.
- Evidence verifier phải kiểm tra entailment giữa claim và text được trích dẫn. Nếu không hỗ trợ: loại claim, hoặc giữ item có `needs_review: true` và lý do `evidence_unverified` nếu phần còn lại vẫn hữu ích. Nếu module không còn output dùng được, trả `502 UNVERIFIED_EVIDENCE`, không trả empty list để giả như không tìm thấy item.
- Speaker identity chỉ được đưa thành participant name khi participant-speaker mapping có trong request hoặc transcript nêu rõ; `speaker_id` đơn thuần là nhãn kỹ thuật.
- Không suy luận owner, priority, deadline, rationale hoặc identity từ ngữ cảnh chung nếu source không nói.

### 7.2 Click-to-play

Web Backend lưu nguyên segments theo transcript revision. UI nhận `source_segment_ids`, tìm segment tương ứng trong đúng revision, rồi seek audio gốc tới `segments[].start`. Không seek theo timestamp do model tự tạo, không dùng offset cục bộ chunk, không dùng ID từ meeting khác. Nếu revision hiện tại khác `transcript_revision_id` trong response, Web không được gắn evidence cũ vào transcript/audio mới.

## 8. Error contract

Mọi lỗi dùng cùng envelope. `request_id` bằng ID đã parse được hoặc null nếu body không có ID hợp lệ; response nên lặp ID an toàn trong log/header correlation. `errors` chứa zero hoặc nhiều field issues; không trả raw provider body, API key, prompt nội bộ, transcript, stack trace hoặc SQL.

~~~json
{
  "statusCode": 400,
  "code": "VALIDATION_ERROR",
  "message": "Yêu cầu trích xuất không hợp lệ.",
  "request_id": "req-invalid-01",
  "retryable": false,
  "retry_after_seconds": null,
  "errors": [
    {
      "path": "meeting.anchor_date",
      "code": "FIELD_REQUIRED",
      "message": "Trường này là bắt buộc."
    }
  ]
}
~~~

| HTTP | Error code | Khi nào | Retry policy |
|---:|---|---|---|
| 400 | `VALIDATION_ERROR` | JSON/schema/type, enum, timestamp, ID, timezone hoặc field constraint sai. | Không retry nguyên request; caller sửa input. |
| 400 | `UNSUPPORTED_CONTRACT_VERSION` | `contract_version` không hỗ trợ. | Không retry; client phải dùng version được hỗ trợ. |
| 401 | `AUTHENTICATION_REQUIRED` | Token thiếu/sai. | Không tự retry; sửa secret/config. |
| 403 | `SERVICE_FORBIDDEN` | Caller hợp lệ nhưng không được phép. | Không retry. |
| 413 | `PAYLOAD_TOO_LARGE` | Body vượt byte limit deployment. | Không retry payload nguyên; giảm/chia request theo hướng dẫn contract. |
| 413 | `TRANSCRIPT_TOO_LONG` | Token/context/request budget vượt giới hạn sau chính sách windowing. | Không retry nguyên request; Web báo lỗi hoặc yêu cầu workflow xử lý lại theo policy. |
| 422 | `EMPTY_TRANSCRIPT` | Không có segment hoặc tất cả text rỗng/whitespace; bao gồm transcript không có speech text dùng được. | Không retry; yêu cầu transcript hợp lệ. |
| 429 | `CAPACITY_LIMIT` | LLM Service đang giới hạn concurrency/rate nội bộ. | Có thể retry sau `Retry-After`; exponential backoff có jitter và giới hạn job. |
| 502 | `PROVIDER_FAILURE` | Provider lỗi hoặc trả lỗi không dùng được. | Retry chỉ khi error được phân loại transient; tối đa theo Web job policy. |
| 502 | `INVALID_STRUCTURED_OUTPUT` | Provider không tạo output đúng schema sau tối đa một lần repair có giới hạn. | Mặc định không tự retry; retry một lần chỉ khi job policy cho phép và chấp nhận chi phí lặp. |
| 502 | `UNVERIFIED_EVIDENCE` | Module được yêu cầu không còn claim nào dùng được sau evidence verification. | Không retry tự động; cần human review hoặc thay đổi prompt/model. |
| 503 | `PROVIDER_RATE_LIMIT` | Provider rate-limit; không expose quota detail/headers nhạy cảm. | Retry khi có `Retry-After`, tối đa theo Web job policy. |
| 503 | `PROVIDER_CONFIGURATION_ERROR` | Provider credential/config không hợp lệ hoặc thiếu. | Không retry cho đến khi cấu hình được sửa. |
| 504 | `PROVIDER_TIMEOUT` | Provider call vượt giới hạn. | Có thể retry có giới hạn nếu job còn active; kết quả lần gọi có thể không biết nên có thể phát sinh chi phí lặp. |
| 504 | `REQUEST_TIMEOUT` | Tổng request budget hết. | Retry có giới hạn theo Web job policy; không tự tạo background job tại LLM Service. |
| 500 | `INTERNAL_ERROR` | Lỗi nội bộ không phân loại được. | Chỉ retry có giới hạn nếu server đánh dấu `retryable: true`; không gửi stack trace. |

`retryable` và `retry_after_seconds` là phần mở rộng đề xuất để Web quyết định thống nhất; không thay cho HTTP status. Với lỗi provider không xác định được transient/permanent, mặc định `retryable: false`. LLM Service không trả `200` có status `failed`.

## 9. Contract examples

### 9.1 Request đầy đủ

Request đầy đủ ở mục 3.1 là fixture cho cả sáu module. Timestamps đều nằm trong duration, speaker mapping được cung cấp, và thời gian là offset audio gốc.

### 9.2 Response thành công cho cả sáu module

~~~json
{
  "contract_version": "1.0",
  "request_id": "req-20261005-001",
  "status": "completed",
  "meeting_id": "meeting-42",
  "transcript_revision_id": "transcript-r3",
  "requested_modules": [
    "meeting_summary",
    "action_items",
    "decision_log",
    "open_issues",
    "follow_up_items",
    "timeline_events"
  ],
  "modules": {
    "meeting_summary": {
      "title": "Sprint planning",
      "date": "2026-10-05",
      "duration_minutes": 31.68,
      "participants": ["Alex", "Maria"],
      "overview": "Nhóm rà soát kế hoạch demo, triển khai và chất lượng diarization. Nhóm thống nhất lựa chọn được nêu trong cuộc họp; ngày deploy mới được xác định trong phạm vi tuần kế tiếp.",
      "key_topics": [
        {
          "topic": "Kế hoạch demo và deploy",
          "brief_discussion": "Nhóm dự kiến demo vào thứ Sáu và deploy bản thử nghiệm trong tuần kế tiếp.",
          "source_segment_ids": ["seg-003", "seg-007"],
          "needs_review": true,
          "review_reasons": ["date_range_needs_confirmation"]
        },
        {
          "topic": "Đánh giá diarization",
          "brief_discussion": "Nhóm nêu câu hỏi về hai người nói đồng thời và dự kiến kiểm tra lại sau khi có bộ dữ liệu.",
          "source_segment_ids": ["seg-005", "seg-006"],
          "needs_review": false,
          "review_reasons": []
        }
      ],
      "source_segment_ids": ["seg-002", "seg-003", "seg-005", "seg-006", "seg-007"],
      "needs_review": false,
      "review_reasons": []
    },
    "action_items": [
      {
        "id": "ACT-001",
        "task": "Hoàn thiện bản OpenAPI",
        "owner": "Alex",
        "due_date": "2026-10-09",
        "raw_due_expression": "thứ Sáu này",
        "due_date_resolution": {
          "status": "exact_date",
          "resolved_date": "2026-10-09",
          "start_date": null,
          "end_date": null,
          "needs_review": false,
          "source_segment_ids": ["seg-001"]
        },
        "priority": null,
        "source_timestamp": "00:14:12.000",
        "context": null,
        "source_segment_ids": ["seg-001"],
        "needs_review": false,
        "review_reasons": []
      }
    ],
    "decision_log": [
      {
        "id": "DEC-001",
        "decision": "Dùng whisper-1 cho bản MVP",
        "rationale": "Có timestamp và nhóm cho rằng triển khai nhanh.",
        "alternatives_considered": null,
        "source_timestamp": "00:14:18.000",
        "source_segment_ids": ["seg-002"],
        "needs_review": false,
        "review_reasons": []
      }
    ],
    "open_issues": [
      {
        "id": "ISS-001",
        "issue_or_question": "Chưa xác định diarization xử lý hai người nói đồng thời như thế nào.",
        "raised_by": "Alex",
        "blocker_severity": null,
        "status": "Unresolved",
        "source_timestamp": "00:18:40.000",
        "source_segment_ids": ["seg-005"],
        "needs_review": false,
        "review_reasons": []
      }
    ],
    "follow_up_items": [
      {
        "id": "FLW-001",
        "item": "Kiểm tra lại độ chính xác diarization sau khi có bộ dữ liệu.",
        "responsible_party": null,
        "target_trigger_or_date": "Tuần sau, sau khi có bộ dữ liệu",
        "target_temporal_resolution": {
          "status": "date_range",
          "resolved_date": null,
          "start_date": "2026-10-12",
          "end_date": "2026-10-18",
          "needs_review": true,
          "source_segment_ids": ["seg-006"]
        },
        "source_timestamp": "00:19:10.000",
        "source_segment_ids": ["seg-006"],
        "needs_review": true,
        "review_reasons": ["date_range_needs_confirmation", "owner_unconfirmed"]
      }
    ],
    "timeline_events": [
      {
        "id": "EVT-001",
        "event": "Demo bản MVP cho nhóm",
        "resolved_date": "2026-10-09",
        "event_type": "demo",
        "raw_statement": "Thứ Sáu này demo bản MVP cho nhóm.",
        "temporal_resolution": {
          "status": "exact_date",
          "resolved_date": "2026-10-09",
          "start_date": null,
          "end_date": null,
          "needs_review": false,
          "source_segment_ids": ["seg-007"]
        },
        "source_timestamp": "00:20:00.000",
        "source_segment_ids": ["seg-007"],
        "needs_review": false,
        "review_reasons": []
      },
      {
        "id": "EVT-002",
        "event": "Deploy bản thử nghiệm",
        "resolved_date": null,
        "event_type": "milestone",
        "raw_statement": "Tuần sau deploy bản thử nghiệm.",
        "temporal_resolution": {
          "status": "date_range",
          "resolved_date": null,
          "start_date": "2026-10-12",
          "end_date": "2026-10-18",
          "needs_review": true,
          "source_segment_ids": ["seg-003"]
        },
        "source_timestamp": "00:15:00.000",
        "source_segment_ids": ["seg-003"],
        "needs_review": true,
        "review_reasons": ["date_range_needs_confirmation"]
      },
      {
        "id": "EVT-003",
        "event": "Gửi báo cáo chất lượng",
        "resolved_date": "2026-10-31",
        "event_type": "deadline",
        "raw_statement": "Cuối tháng gửi báo cáo chất lượng.",
        "temporal_resolution": {
          "status": "exact_date",
          "resolved_date": "2026-10-31",
          "start_date": null,
          "end_date": null,
          "needs_review": false,
          "source_segment_ids": ["seg-004"]
        },
        "source_timestamp": "00:18:20.000",
        "source_segment_ids": ["seg-004"],
        "needs_review": false,
        "review_reasons": []
      }
    ]
  },
  "processing": {
    "provider": "example-provider",
    "model_id": "example-model",
    "prompt_version": "extract-v1.0",
    "evidence_prompt_version": "evidence-v1.0",
    "started_at": "2026-10-05T09:00:00Z",
    "completed_at": "2026-10-05T09:00:03Z",
    "token_usage": {
      "input_tokens": 1200,
      "output_tokens": 500
    }
  }
}
~~~

Các giá trị provider/model trong fixture là tên giả lập để kiểm tra schema, không chọn hoặc xác nhận provider thật.

### 9.3 Chỉ Summary và Actions

Request:

~~~json
{
  "contract_version": "1.0",
  "request_id": "req-summary-actions-01",
  "meeting": {
    "id": "meeting-43",
    "title": "Planning",
    "anchor_date": "2026-10-05",
    "timezone": "Asia/Ho_Chi_Minh",
    "duration_seconds": 30.0,
    "participants": [
      {
        "id": "participant-alex",
        "display_name": "Alex",
        "speaker_ids": ["speaker_1"]
      }
    ]
  },
  "transcript": {
    "revision_id": "transcript-r1",
    "language": "vi",
    "segments": [
      {
        "id": "seg-a1",
        "start": 12.5,
        "end": 18.2,
        "speaker_id": "speaker_1",
        "text": "Tôi sẽ gửi bản ghi chú vào thứ Sáu này."
      },
      {
        "id": "seg-a2",
        "start": 18.3,
        "end": 22.0,
        "speaker_id": "speaker_1",
        "text": "Hôm nay chủ yếu rà lại tiến độ."
      }
    ]
  },
  "extraction": {
    "output_language": "vi",
    "requested_modules": ["meeting_summary", "action_items"]
  }
}
~~~

Response:

~~~json
{
  "contract_version": "1.0",
  "request_id": "req-summary-actions-01",
  "status": "completed",
  "meeting_id": "meeting-43",
  "transcript_revision_id": "transcript-r1",
  "requested_modules": ["meeting_summary", "action_items"],
  "modules": {
    "meeting_summary": {
      "title": "Planning",
      "date": "2026-10-05",
      "duration_minutes": 0.5,
      "participants": ["Alex"],
      "overview": "Cuộc họp rà soát tiến độ và ghi nhận cam kết gửi bản ghi chú.",
      "key_topics": [
        {
          "topic": "Rà soát tiến độ",
          "brief_discussion": "Nhóm rà lại tiến độ hiện tại.",
          "source_segment_ids": ["seg-a2"],
          "needs_review": false,
          "review_reasons": []
        }
      ],
      "source_segment_ids": ["seg-a1", "seg-a2"],
      "needs_review": false,
      "review_reasons": []
    },
    "action_items": [
      {
        "id": "ACT-001",
        "task": "Gửi bản ghi chú",
        "owner": "Alex",
        "due_date": "2026-10-09",
        "raw_due_expression": "thứ Sáu này",
        "due_date_resolution": {
          "status": "exact_date",
          "resolved_date": "2026-10-09",
          "start_date": null,
          "end_date": null,
          "needs_review": false,
          "source_segment_ids": ["seg-a1"]
        },
        "priority": null,
        "source_timestamp": "00:00:12.500",
        "context": null,
        "source_segment_ids": ["seg-a1"],
        "needs_review": false,
        "review_reasons": []
      }
    ],
    "decision_log": null,
    "open_issues": null,
    "follow_up_items": null,
    "timeline_events": null
  },
  "processing": {
    "provider": "example-provider",
    "model_id": "example-model",
    "prompt_version": "extract-v1.0",
    "evidence_prompt_version": "evidence-v1.0",
    "started_at": "2026-10-05T09:00:00Z",
    "completed_at": "2026-10-05T09:00:02Z",
    "token_usage": null
  }
}
~~~

### 9.4 Response có danh sách rỗng

Request:

~~~json
{
  "contract_version": "1.0",
  "request_id": "req-empty-lists-01",
  "meeting": {
    "id": "meeting-44",
    "title": "Status review",
    "anchor_date": "2026-10-05",
    "timezone": "Asia/Ho_Chi_Minh",
    "duration_seconds": 20.0,
    "participants": []
  },
  "transcript": {
    "revision_id": "transcript-r1",
    "language": "vi",
    "segments": [
      {
        "id": "seg-e1",
        "start": 1.0,
        "end": 7.0,
        "speaker_id": null,
        "text": "Hôm nay chúng ta chủ yếu trao đổi tình hình chung, chưa có việc hay mốc lịch nào cần chốt."
      }
    ]
  },
  "extraction": {
    "output_language": "vi",
    "requested_modules": [
      "meeting_summary",
      "action_items",
      "decision_log",
      "open_issues",
      "follow_up_items",
      "timeline_events"
    ]
  }
}
~~~

Response:

~~~json
{
  "contract_version": "1.0",
  "request_id": "req-empty-lists-01",
  "status": "completed",
  "meeting_id": "meeting-44",
  "transcript_revision_id": "transcript-r1",
  "requested_modules": [
    "meeting_summary",
    "action_items",
    "decision_log",
    "open_issues",
    "follow_up_items",
    "timeline_events"
  ],
  "modules": {
    "meeting_summary": {
      "title": "Status review",
      "date": "2026-10-05",
      "duration_minutes": 0.33,
      "participants": [],
      "overview": "Cuộc họp trao đổi tình hình chung; transcript không ghi nhận công việc, quyết định, câu hỏi còn mở, follow-up hoặc mốc dự án được chốt.",
      "key_topics": [
        {
          "topic": "Tình hình chung",
          "brief_discussion": "Người nói nêu rằng cuộc họp chủ yếu trao đổi tình hình chung.",
          "source_segment_ids": ["seg-e1"],
          "needs_review": false,
          "review_reasons": []
        }
      ],
      "source_segment_ids": ["seg-e1"],
      "needs_review": false,
      "review_reasons": []
    },
    "action_items": [],
    "decision_log": [],
    "open_issues": [],
    "follow_up_items": [],
    "timeline_events": []
  },
  "processing": {
    "provider": "example-provider",
    "model_id": "example-model",
    "prompt_version": "extract-v1.0",
    "evidence_prompt_version": "evidence-v1.0",
    "started_at": "2026-10-05T09:00:00Z",
    "completed_at": "2026-10-05T09:00:01Z",
    "token_usage": null
  }
}
~~~

### 9.5 Request không hợp lệ

Ví dụ request thiếu `meeting.anchor_date` phải bị từ chối trước khi gọi provider:

~~~json
{
  "statusCode": 400,
  "code": "VALIDATION_ERROR",
  "message": "Yêu cầu trích xuất không hợp lệ.",
  "request_id": "req-invalid-01",
  "retryable": false,
  "retry_after_seconds": null,
  "errors": [
    {
      "path": "meeting.anchor_date",
      "code": "FIELD_REQUIRED",
      "message": "Trường này là bắt buộc."
    }
  ]
}
~~~

### 9.6 Lỗi provider

~~~json
{
  "statusCode": 503,
  "code": "PROVIDER_RATE_LIMIT",
  "message": "LLM provider tạm thời giới hạn request.",
  "request_id": "req-20261005-001",
  "retryable": true,
  "retry_after_seconds": 15,
  "errors": []
}
~~~

### 9.7 Temporal range và mơ hồ

Với anchor `2026-10-05`, cụm “tuần sau deploy” giữ nguyên phạm vi cả tuần, không ép thành thứ Hai:

~~~json
{
  "status": "date_range",
  "resolved_date": null,
  "start_date": "2026-10-12",
  "end_date": "2026-10-18",
  "needs_review": true,
  "source_segment_ids": ["seg-003"]
}
~~~

## 10. Contract test cases và acceptance criteria

Contract tests không cần provider thật; dùng fixtures và fake provider để kiểm tra API/schema. Bộ integration với provider thật thuộc P11 và phải ghi rõ dữ liệu, model/config, chi phí và giới hạn.

- `GET /health` trả đúng service name/version và không gọi provider.
- `GET /openapi.json` thể hiện request, response và error schemas hiện tại.
- Request đủ sáu module trả đủ sáu key, đúng schema, echo request/revision IDs.
- Request Summary + Actions chỉ chạy hai module; bốn module còn lại null; empty result cho list module là `[]`.
- Output có module requested null, thiếu source hoặc field sai phải không được trả `status: completed`.
- `contract_version` không hỗ trợ, module enum sai/trùng, required field thiếu, timezone sai và unknown field trả `400`.
- `segments: []`, text trắng hoặc không có text speech dùng được trả `422 EMPTY_TRANSCRIPT`.
- `segment.id` trùng, timestamp âm, `end <= start`, segment ngoài duration, hoặc start đảo thứ tự trả `400`.
- Overlap hợp lệ giữa hai segment được nhận; `speaker_id: null` được nhận và không bị tự gán.
- Participant-speaker mapping trùng một speaker sang hai người bị từ chối.
- Byte limit trả `413 PAYLOAD_TOO_LARGE`; transcript vượt token budget sau windowing trả `413 TRANSCRIPT_TOO_LONG`.
- `anchor_date=2026-10-05`: “thứ Sáu này” → `2026-10-09`; “tuần sau” → `2026-10-12` đến `2026-10-18`; “cuối tháng” → `2026-10-31`.
- Ngày tháng/năm, năm nhuận, timezone địa phương và biểu thức mơ hồ được test; không test nào phụ thuộc ngày hệ thống.
- Exact temporal state có đúng một `resolved_date`; range có đủ hai đầu và không có `resolved_date`; unresolved không có ngày.
- `source_segment_ids` không tồn tại/khác revision, source timestamp không khớp segment start hoặc evidence verifier bác claim phải bị loại, đánh review hoặc trả structured failure theo quy tắc.
- `needs_review` phải nhất quán với `review_reasons`; provider không được ghi stack trace/API key vào envelope.
- Provider timeout/rate-limit/structured output lỗi ánh xạ đúng status, code, retry flag và `Retry-After`; không trả 200 một phần.
- Retry giữ `request_id`; test Web Backend chứng minh dedupe theo meeting/revision/module/config thay vì dựa vào LLM Service.
- Full JSON examples trong tài liệu phải parse được bằng JSON parser và khớp field tables.

Acceptance cho contract v1: ba service có thể xây fixture tương thích; mọi artifact có source IDs kiểm tra được; relative date giữ đúng độ chính xác; module chưa yêu cầu có null, module chạy không có item có []; processing failure luôn là non-2xx error envelope.

## 11. Open questions và mâu thuẫn cần thống nhất

| Vấn đề | Quan sát từ repository/tài liệu | Cách xử lý đề xuất trong contract | Cần nhóm chốt |
|---|---|---|---|
| Meeting date examples | Product Description/Feature Overview có ví dụ `2026-10-05` → “Thứ 6” là `2026-10-08` hoặc `2026-10-09`; ngày 08/10/2026 thực tế là thứ Năm. Roadmap sửa thành `2026-10-09`. | Dùng quy tắc và ví dụ của Roadmap: `2026-10-09`; P00-06 nên đồng bộ tài liệu nguồn sau khi được giao riêng. | Có. |
| “Tuần sau” | Feature Overview từng gợi ý ngày đầu tuần; Roadmap yêu cầu giữ khoảng tuần, không tự gán thứ Hai. | Contract trả range 12–18/10/2026 và `needs_review: true`. | Có; cần xác nhận week definition ISO Monday–Sunday. |
| “Cuối tháng” | Schema gốc minh họa ngày cuối tháng; từ ngữ có thể chỉ một khoảng cuối tháng. | Policy v1 đề xuất ngày cuối tháng theo anchor month; giữ raw expression và review khi ngữ cảnh không nói rõ. | Có; P08-01. |
| Meeting anchor trong Timeline | Product Description có event tổng hợp “Meeting (Anchor)” kèm timestamp `00:00:00`, nhưng Timeline được định nghĩa là milestone dự án được nói và source grounding yêu cầu evidence. | Không tạo event tổng hợp trong `timeline_events`; meeting date đã có ở Summary/metadata. Muốn hiển thị anchor thì Web render từ meeting metadata. | Có; nếu chọn event tổng hợp cần quy định nguồn metadata thay vì source segment. |
| Owner của Action Item | Product schema nói phải có owner; Roadmap cho phép field chưa rõ/null và item cần review. | Chỉ trả candidate có task/deliverable rõ; owner null thì `needs_review`, không coi là đã phân công. | Có; P03-04/P07-02. |
| Error conventions | API Nest hiện chỉ có health route, chưa có `docs/api-contract.md` hoặc custom error envelope. | Dùng envelope có `statusCode`, `code`, `message`, `errors`; đây là đề xuất, cần đồng bộ với Nest trong contract riêng. | Có; P00-04. |
| Metadata được lưu | Prisma hiện chỉ có `Meeting.title` và `anchorDate`; chưa có timezone, participants, duration, transcript revision hoặc artifacts. | Contract yêu cầu Web gửi đủ context; không giả định LLM Service lưu/persist các field này. | Có; Backend cần xác định persistence/default timezone trong task riêng. |
| Provider, timeout và limits | LLM provider/model, token window, timeout SLA và byte limit chưa được chốt trong code. | Adapter configurable; các giá trị ví dụ được đánh dấu đề xuất/configurable, không phải benchmark hay SLA. | Có; P00-03 và P00-05. |
| Service authentication và data retention | Chưa có service-to-service auth hoặc policy provider retention trong repository. | Bearer token nội bộ là baseline đề xuất; transcript không log/persist ở LLM Service. | Có; cần duyệt secret/retention/region trước provider thật. |
| Repository guidance | Root `AGENTS.md` còn mô tả workspace chỉ có planning docs, trong khi README và tree hiện có web/API/Prisma source. | Tài liệu này phân biệt trạng thái theo file thực tế; không sửa AGENTS ngoài phạm vi task. | Có; cập nhật tài liệu hướng dẫn trong task riêng. |
