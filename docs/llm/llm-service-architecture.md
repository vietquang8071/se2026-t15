# Kiến trúc LLM Service

**Phiên bản:** 1.0 · **Trạng thái:** Thiết kế đề xuất; chưa có source implementation · **Phạm vi:** Service trích xuất sáu business modules từ normalized transcript

## Mục lục

1. [Mục tiêu, trạng thái repository và ranh giới](#1-mục-tiêu-trạng-thái-repository-và-ranh-giới)
2. [System context và deployment](#2-system-context-và-deployment)
3. [Internal processing pipeline](#3-internal-processing-pipeline)
4. [LLM extraction design](#4-llm-extraction-design)
5. [Temporal resolution engine](#5-temporal-resolution-engine)
6. [Chiến lược transcript dài](#6-chiến-lược-transcript-dài)
7. [Reliability và security](#7-reliability-và-security)
8. [Observability và evaluation](#8-observability-và-evaluation)
9. [Cấu trúc project đề xuất](#9-cấu-trúc-project-đề-xuất)
10. [Implementation roadmap cho LLM Service](#10-implementation-roadmap-cho-llm-service)
11. [Architecture Decisions và trade-offs](#11-architecture-decisions-và-trade-offs)
12. [Open questions và phụ thuộc tích hợp](#12-open-questions-và-phụ-thuộc-tích-hợp)

## 1. Mục tiêu, trạng thái repository và ranh giới

LLM Service nhận meeting context và transcript đã normalize, trích xuất Meeting Summary, Action Items, Decision Log, Open Issues, Follow-up Items và Timeline Events, resolve thời gian theo anchor date, kiểm tra structured output/evidence rồi trả JSON đồng bộ cho Web Backend. Contract chi tiết nằm tại [llm-service-contract.md](./llm-service-contract.md).

### 1.1 Trạng thái hiện tại và trạng thái mục tiêu

| Hạng mục | Trạng thái quan sát được ở repository | Trạng thái mục tiêu trong thiết kế |
|---|---|---|
| Web Application | Có Next.js App Router skeleton trong apps/web. | Quản lý UI/meeting/audio, job lifecycle, persistence và gọi hai service xử lý. |
| Web Backend | Có NestJS API skeleton; hiện chỉ có GET /health. | Orchestrate processing jobs, gọi Audio Processing Service/LLM Service và lưu artifacts. |
| Database | Prisma/PostgreSQL hiện chỉ định nghĩa Meeting với title, anchor date và timestamps. | Web Backend sở hữu meeting, transcript revisions và artifacts; LLM Service không kết nối database. |
| Audio Processing Service | Chưa có implementation trong repository hiện tại. | Validate/preprocess audio, ASR, diarization, timestamp alignment, chunking/stitching và trả normalized transcript. |
| LLM Service | Chưa có implementation; thư mục hiện được dành cho hai tài liệu thiết kế. | Python 3.12+, FastAPI, Pydantic v2, REST/JSON, provider adapter và pytest theo baseline yêu cầu. |
| Docker Compose | Hiện chỉ chạy PostgreSQL với volume và healthcheck. | LLM Service có thể build/deploy thành container riêng; thêm service vào Compose là thay đổi cấu hình khác và không thuộc task tài liệu này. |
| API contract chung | Không có docs/api-contract.md trong working tree hoặc history của refs local đã kiểm tra. | Hai service tích hợp theo [LLM Service contract](./llm-service-contract.md); conventions dùng chung với Nest API cần được nhóm chốt. |

Root AGENTS.md còn mô tả repository chỉ có tài liệu kế hoạch; README và source tree hiện cho thấy Web/API/Prisma skeleton đã có. Thiết kế này lấy trạng thái từ file source/config hiện tại, không xem roadmap là bằng chứng tính năng đã hoàn thành.

### 1.2 Service boundaries

| Service | Nhận và sở hữu | Trách nhiệm | Không làm |
|---|---|---|---|
| Web Application / Backend | User input, meeting metadata, audio references, job state, transcript và artifacts lưu bền. | UI, meeting/anchor date, upload/recording, orchestration, persistence, export và API cho client. Gọi LLM Service trong background job. | Không giao database ownership cho service AI. |
| Audio Processing Service | Audio input và metadata cần cho transcription. | File validation/preprocessing, speech-to-text, diarization, timestamp alignment, chunking/stitching; trả segment times tính trên audio gốc và speaker labels. | Không trích xuất business modules hoặc resolve deadline nghiệp vụ. |
| LLM Service | JSON request có meeting context và normalized transcript revision. | Prompt orchestration, sáu module, temporal resolution, structured parsing, evidence validation và evaluation support. | Không nhận raw audio, chạy ASR/diarization, ghi PostgreSQL hoặc tự quản lý job/queue. |
| LLM provider | Prompt và transcript text cần cho một lần generation/verification. | Trả structured candidate output theo capability đã cấu hình. | Không sở hữu contract với Web, meeting persistence hoặc source timestamps. |

Transcript, participant mapping và meeting metadata có nguồn chuẩn ở Web Backend. Speaker ID là nhãn transcript, không phải identity. Chỉ mapping đã xác nhận trong request cho phép LLM dùng participant display name.

## 2. System context và deployment

### 2.1 System Context Diagram

~~~mermaid
flowchart LR
    User["Người dùng"] --> Web["Web Application<br/>Next.js + NestJS"]
    Web -->|upload / metadata| Audio["Audio Processing Service"]
    Audio -->|normalized transcript<br/>segments + timestamps + speaker_id| Web
    Web -->|lưu meeting, jobs,<br/>transcript, artifacts| DB[("PostgreSQL<br/>Web-owned")]
    Web -->|POST /v1/extractions<br/>synchronous HTTP trong job nền| LLM["LLM Service<br/>FastAPI"]
    LLM -->|structured generation / verification| Provider["LLM Provider<br/>configurable"]
    Provider -->|candidate JSON| LLM
    LLM -->|200 response hoặc error envelope| Web
    Web -->|minutes, transcript, export| User
~~~

Web Backend là điểm điều phối duy nhất giữa Audio Processing Service và LLM Service. Audio Processing Service không gọi trực tiếp LLM Service; LLM Service không đọc PostgreSQL hoặc audio storage.

### 2.2 LLM Processing Pipeline

~~~mermaid
flowchart TD
    A["POST /v1/extractions"] --> B["1. Request Validation<br/>Pydantic + auth"]
    B -->|valid| C["2. Transcript Context Building<br/>meeting, participants, segment map"]
    B -->|invalid| E["Structured Error"]
    C --> D["3. LLM Extraction<br/>prompt + provider adapter"]
    D -->|candidate JSON| F["4. Temporal Resolution<br/>deterministic Python rules"]
    D -->|provider error| E
    F --> G["5. Evidence Verification<br/>IDs + semantic support"]
    G -->|unverified item| H["Drop or mark needs_review"]
    H --> I["6. Output Validation<br/>Pydantic + invariants"]
    G -->|module unusable| E
    I -->|valid| J["7. Response Construction<br/>IDs + source_timestamp + metadata"]
    I -->|invalid after one repair| E
    J --> K["200 completed"]
~~~

### 2.3 End-to-end sequence

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant Web as Web Backend
    participant Audio as Audio Processing
    participant DB as PostgreSQL
    participant LLM as LLM Service
    participant Provider as LLM Provider
    User->>Web: Tạo meeting, upload/record audio
    Web->>DB: Lưu metadata, audio reference, job queued
    Web->>Audio: Gửi audio để xử lý
    Audio-->>Web: Normalized transcript + speaker labels
    Web->>DB: Lưu transcript revision và segments
    Web->>LLM: POST /v1/extractions (JSON)
    LLM->>LLM: Validate, build context, budget tokens
    LLM->>Provider: Structured extraction
    Provider-->>LLM: Candidate modules + evidence IDs
    LLM->>LLM: Resolve dates, verify evidence, validate output
    alt Output hợp lệ
        LLM-->>Web: 200 completed + six module slots
        Web->>DB: Lưu artifacts gắn meeting/revision
        Web-->>User: Hiển thị minutes, source và trạng thái job
    else Provider/validation lỗi
        LLM-->>Web: Non-2xx error envelope
        Web->>DB: Lưu job error và retry state
        Web-->>User: Trạng thái lỗi hoặc yêu cầu review
    end
~~~

### 2.4 Deployment đề xuất

- Chạy LLM Service thành container độc lập, expose HTTP trên private network nội bộ; chỉ Web Backend gọi POST /v1/extractions.
- Container nhận provider credentials từ secret manager/runtime environment và chỉ cần network egress tới provider đã cấu hình.
- Không mount PostgreSQL credentials hoặc database volume vào LLM container. Không cần Redis, Celery, Kafka, queue hay vector database cho MVP.
- Vì service stateless, có thể scale ngang theo CPU/provider concurrency; giới hạn concurrency theo instance để tránh vượt quota/cost.
- Health check chỉ kiểm tra process/config cơ bản. Không gọi LLM provider ở mỗi health probe.
- Local Compose hiện tại chỉ chạy Postgres. Việc thêm FastAPI container, environment variables, private networking và healthcheck vào Compose cần một task implementation riêng.
- Python app nằm dưới apps/llm-service nhưng không phải pnpm workspace package. Root pnpm-workspace.yaml glob apps/* không thay thế pyproject.toml/Python toolchain; Turborepo chỉ quản lý service nếu nhóm cấu hình package/task tương thích riêng.

## 3. Internal processing pipeline

Pipeline phải chạy theo thứ tự trong bảng. Mỗi bước nhận model nội bộ có kiểu rõ, trả output có thể kiểm tra; lỗi provider/output được đổi sang error envelope trong [contract](./llm-service-contract.md#8-error-contract).

| Bước/component | Trách nhiệm | Input → Output | Dependencies | Error handling | Unit/contract tests |
|---|---|---|---|---|---|
| 1. RequestValidator | Xác thực bearer token, contract version, field, enum, IDs, date/timezone, segment ordering/duration và payload limit. | JSON body → typed request hoặc validation errors. | FastAPI, Pydantic v2, config. | Input sai trả 400; body quá lớn trả 413; transcript rỗng trả 422. Chưa gọi provider. | Field thiếu/sai, unknown field, duplicate IDs, overlap hợp lệ, segment sai bounds, timezone sai, auth. |
| 2. TranscriptContextBuilder | Tạo segment map, participant/speaker map đã xác nhận, compact context và token estimate; giữ nguyên source IDs/text. | Typed request → extraction context + source index. | Request schemas, tokenizer/provider capability nếu có. | Không âm thầm cắt text; vượt budget chuyển TranscriptTooLong hoặc trả window plan. | Giữ nguyên text/IDs, mapping speaker, duration, token boundary và segment order. |
| 3. ExtractionService + PromptRegistry | Chọn prompt theo version/ngôn ngữ/modules; gọi một lần extraction có structured schema. | Context + module set → candidate JSON. | LLMProvider, prompt templates. | Timeout/rate-limit/provider failure được chuẩn hóa; raw response không ghi log. | Fake provider cho từng module set, prompt version, vi/en, timeout và invalid JSON. |
| 4. TemporalResolver | Parse raw temporal expressions và tính exact date/range/unresolved từ anchor/timezone. | Candidate raw phrases + anchor_date, timezone → TemporalResolution. | Python date/calendar/timezone standard library. | Phrase không đủ rõ giữ unresolved; ngày không hợp lệ không tự sửa. | Weekdays, tuần, cuối tháng, leap year, qua tháng/năm, timezone, mơ hồ. |
| 5. EvidenceVerifier | Kiểm tra source IDs, cùng request/revision, timestamp projection và semantic support của claim. | Candidate claims + source index → verified/review/drop decision. | Source index và verifier prompt/provider đã cấu hình. | Unsupported claim bị bỏ/đánh review; module không còn nội dung dùng được trả UNVERIFIED_EVIDENCE. | ID hợp lệ/sai, segment sai meeting/revision, quote không support, mâu thuẫn, empty evidence. |
| 6. OutputValidator | Validate Pydantic schema, module semantics, null/empty rules, temporal invariants, IDs, needs_review và source subsets. | Candidate đã resolve/verify → validated response modules. | Request/response schemas. | Sau tối đa một structured repair, output còn invalid trả INVALID_STRUCTURED_OUTPUT; không trả partial success. | JSON invalid, field thiếu, enum sai, date state không nhất quán, requested module null. |
| 7. ResponseBuilder | Copy metadata đã biết, gán response-local IDs, tính source_timestamp, điền null cho module chưa yêu cầu, thêm processing metadata. | Validated modules + request + provider metadata → response JSON. | Schemas, source index, request context. | Lỗi nội bộ trả INTERNAL_ERROR, không serialize stack trace. | Echo request/revision, thứ tự IDs, timestamp từ segment start, token usage optional. |

### 3.1 Chi tiết luồng dữ liệu

1. Web gửi immutable transcript.revision_id; request validator từ chối revision thiếu segments dùng được trước khi tiêu tốn provider call.
2. Context builder lập index segment_id → {start, end, speaker_id, text}. Speaker ID chỉ được đổi sang tên participant nếu request đã có mapping.
3. Prompt nhận context và transcript dưới dạng data block JSON đã serialize, tách khỏi system instructions. Model trả candidate modules, raw temporal phrases và source IDs; model không được tự tạo source timestamps hoặc persistent IDs.
4. Temporal resolver dùng anchor/timezone tính date state cho Action Items, Follow-ups và Timeline Events. Cùng một expression dùng cùng hàm resolve, không tính riêng trong từng prompt.
5. Evidence verifier kiểm tra source reference và mức hỗ trợ ngữ nghĩa. Kết quả uncertain được đánh review hoặc loại bỏ; bằng chứng cấu trúc hợp lệ không tự chứng minh claim đúng.
6. Output validator kiểm tra invariants cuối. Requested module không thể null trong response thành công; list rỗng sau extraction hợp lệ là [].
7. Response builder echo meeting/revision/request IDs, sắp xếp artifact theo quy tắc module trong contract, gán ID hiển thị theo thứ tự trả về và tính source_timestamp từ segment gốc. Web persist response, không phải LLM Service.

## 4. LLM extraction design

### 4.1 Prompt templates và versioning

- Lưu prompt templates như file versioned trong app/prompts/v1/; không nhúng prompt dài trong route handler.
- System instructions xác định role, output language, sáu module, business boundaries, cấm bịa, schema và source citation requirements.
- User prompt chứa meeting metadata cần cho extraction và transcript segments dưới dạng data block JSON. Không nối transcript thành phần system/developer instruction.
- Transcript là untrusted data: câu nói như “bỏ qua hướng dẫn trước” chỉ là nội dung cuộc họp. Prompt phải nói rõ không nhận chỉ thị trong transcript để đổi role, schema, policy hoặc tool use.
- prompt_version được trả trong response; mọi sửa đổi làm thay đổi cách trích xuất tăng version để evaluation có thể so sánh.
- Chỉ đưa vào prompt dữ liệu cần thiết. Không gửi meeting IDs có ý nghĩa cá nhân, credentials hay nội dung không thuộc transcript.
- Yêu cầu structured output theo schema Pydantic/JSON Schema khi provider hỗ trợ. Nếu provider chỉ trả text, parse JSON nghiêm ngặt rồi validate; chỉ cho một lần repair có giới hạn.
- Repair prompt nhận lỗi schema đã rút gọn và candidate output dưới dạng untrusted data; không đưa stack trace hoặc secrets vào prompt.
- Không yêu cầu hoặc lưu chain-of-thought. Chỉ nhận artifact, source IDs và các field cần thiết.

### 4.2 Provider abstraction

Một interface nhỏ LLMProvider tách ExtractionService khỏi SDK cụ thể. Interface tối thiểu cần:

- generate_structured(messages, schema, model_config, timeout): trả payload đã decode, model_id, token usage nếu provider cung cấp.
- count_tokens(text, model_config) hoặc khả năng ước lượng token/context để preflight và lập window.
- Chuẩn hóa lỗi thành nhóm timeout, rate-limit, authentication/configuration, transient provider failure, permanent provider failure và malformed output.
- Không làm lộ provider-specific request/response trong HTTP contract.

MVP chỉ cần một adapter thật sau khi nhóm chọn provider/model và một fake adapter cho tests. Không tạo registry/plugin framework hoặc nhiều adapter chưa có use case. provider và model_id thật được ghi trong processing metadata; fixtures dùng tên giả lập.

### 4.3 Lựa chọn extraction pass

| Phương án | Latency/cost | Accuracy/maintainability | Đánh giá |
|---|---|---|---|
| Single-pass: một structured generation cho tất cả requested modules | Thấp nhất; ít round trip. | Tốt cho schema thống nhất nhưng prompt dài, nhầm ranh giới module và source checking yếu hơn. | Phù hợp P03 Summary/Actions và transcript ngắn; cần validation/evidence stage trước khi coi full result đã kiểm chứng. |
| Multi-stage theo chủ đề rồi hợp nhất | Cao hơn; nhiều lần gọi và nhiều bước state cần debug. | Có thể dùng ngữ cảnh/verification riêng nhưng merge có thể tạo duplicate hoặc làm mất source. | Chưa cần framework riêng cho MVP; dùng sau benchmark nếu single-pass hụt chất lượng. |
| Một lần gọi riêng cho từng module | Latency/cost cao nhất, lỗi một module dễ cô lập hơn. | Prompt đơn giản hơn nhưng các module có thể mâu thuẫn về owner/date và lặp claim. | Không khuyến nghị làm mặc định. |

**Đề xuất MVP:** một generation pass cho các module được yêu cầu trong mỗi transcript window; sau đó deterministic temporal resolution, structural/reference validation và một evidence-verification pass theo batch cho claims cần kiểm tra. Nếu output schema sai, tối đa một repair attempt. Đây không phải multi-agent architecture; verifier chỉ trả trạng thái support/uncertain/unsupported, không tự tạo artifact mới. Đo chi phí và latency trên gold dataset trước khi bỏ verifier hoặc chuyển sang pipeline nhiều lượt.

Trong P03, có thể bắt đầu với Summary + Actions và fake provider/fixtures, sau đó tích hợp provider thật theo M1. P07 thêm bốn module còn lại, kiểm tra phân loại nghiệp vụ và evidence trước M2.

### 4.4 Sáu module, tiếng Việt/Anh và mâu thuẫn

- Một schema response giữ sáu key cố định; requested_modules quyết định module nào chạy, giúp P03 chỉ dùng Summary/Actions và P07 mở rộng mà không đổi root response shape.
- output_language là vi hoặc en; transcript vẫn giữ transcript.language gốc. Không dịch raw statement/source text.
- Tên riêng, display name và speaker labels giữ nguyên theo request/transcript. Không tự chuẩn hóa hai tên thành một người.
- Action Item yêu cầu task/deliverable cụ thể. Owner có thể null nếu có candidate nhưng chưa xác nhận; đánh needs_review, không trình bày như đã giao việc.
- Decision chỉ được tạo khi có câu chốt/consensus; proposal và opinion không đủ. Rationale/alternatives null nếu không được nêu.
- Open Issue là câu hỏi/bất đồng chưa giải; Follow-up là bước cụ thể để quay lại/kiểm tra. Một cuộc trao đổi có thể tạo cả hai nếu source chứng minh hai nội dung riêng.
- Khi transcript mâu thuẫn, giữ claim và evidence riêng, không tự chọn người “đúng”. Nếu mâu thuẫn chưa được giải, không phát hành decision đã chốt; tạo issue/review item phù hợp.
- Summary tổng hợp nội dung nhưng mỗi topic và overview vẫn phải có source IDs; không phát biểu kết luận không có trong cuộc họp.
- Priority/severity chỉ được điền khi được nói rõ hoặc có rubric đã được nhóm chốt; nếu không, null.

## 5. Temporal resolution engine

### 5.1 Hybrid approach

LLM nhận diện temporal phrase, target event/task và segment evidence. Python TemporalResolver parse phrase, áp quy tắc lịch trên meeting.anchor_date và meeting.timezone, rồi trả exact_date, date_range hoặc unresolved theo contract. LLM không thực hiện phép tính calendar cuối.

### 5.2 Quy trình resolve

1. Thu thập phrase nguyên văn từ các candidate Action Items, Follow-ups và Timeline Events.
2. Chuẩn hóa khoảng trắng để phân tích nhưng giữ nguyên raw phrase.
3. Xác định loại expression: ngày ISO/cụ thể, weekday tương đối, tuần, cuối tháng, khoảng ngày hoặc thiếu ngữ cảnh.
4. Chuyển anchor date sang local civil date theo timezone của meeting; không gọi system clock để chọn ngày.
5. Tính kết quả bằng datetime.date, calendar.monthrange và quy tắc ISO week; không cộng trừ 24-hour duration để thay thế calendar arithmetic.
6. Nếu expression chỉ cho biết range, giữ hai đầu inclusive; không chọn một ngày đại diện.
7. Nếu nhiều cách diễn giải hợp lý, trả unresolved và cần review.
8. Ghi cùng resolution vào các module có cùng temporal expression để deadline và event không lệch nhau.

### 5.3 Chính sách lịch v1 đề xuất

| Trường hợp | Xử lý |
|---|---|
| “Thứ Sáu này” | Ngày thứ Sáu đầu tiên từ anchor date trở đi; anchor vào thứ Sáu thì dùng chính ngày đó. 2026-10-05 → 2026-10-09. |
| “Tuần sau” | ISO week kế tiếp, thứ Hai–Chủ nhật inclusive. 2026-10-05 → 2026-10-12 đến 2026-10-18; exact day chưa biết nên không suy ra thứ Hai. |
| “Cuối tháng” | Ngày cuối tháng chứa anchor date; với 2026-10-05 là 2026-10-31. Đây là policy đề xuất khớp ví dụ gốc, cần P08-01 xác nhận. |
| “Cuối tháng sau” | Ngày cuối tháng kế tiếp anchor month; kiểm tra chuyển năm và số ngày tháng bằng thư viện lịch. |
| “Ngày 12” không rõ tháng/năm | Resolve khi transcript cho một tháng/năm duy nhất; nếu không, unresolved. |
| Ngày qua tháng/năm hoặc năm nhuận | Dùng phép tính calendar; không dựa vào số ngày cố định trong tháng. |
| Timezone | Dùng IANA timezone của meeting để xác định ngày dân sự. Timestamp transcript vẫn là elapsed seconds trên audio gốc. |
| Mơ hồ/mâu thuẫn | Giữ raw phrase, các source IDs và status unresolved; needs_review là true. |

Các ví dụ này sửa cách diễn giải temporal sai trong Product Description/Feature Overview; xem Open Questions. UI phải hiển thị date range/unresolved riêng, không sắp xếp chúng thành một due date giả.

## 6. Chiến lược transcript dài

### 6.1 Token budgeting

- Byte limit HTTP được kiểm tra trước khi parse toàn bộ request vào model; giới hạn deployment phải được công bố.
- Adapter ước lượng token theo model/provider đang cấu hình. Budget dành riêng chỗ cho system prompt, meeting context, output schema, completion và safety margin.
- Dùng model context window từ cấu hình adapter; không assume một con số chung cho mọi provider.
- Nếu request vượt token budget một pass nhưng còn trong hard limit, chia cửa sổ theo ranh giới segment. Không cắt giữa segment hoặc bỏ segment có timestamp nếu nó là evidence cho overlap/turn-taking.
- Nếu không thể xử lý hết cửa sổ trong total request budget hoặc hard limit, trả TRANSCRIPT_TOO_LONG; không trả partial success.

### 6.2 MVP windowing

1. Ưu tiên single-pass cho transcript vừa context.
2. Với transcript dài, tạo windows theo thứ tự thời gian và dừng trước token limit; overlap chỉ thêm trọn segment boundary cần thiết, có giới hạn cấu hình.
3. Giữ global segment_id, start/end và speaker ID trong từng window; không đổi ID/offset.
4. Trích candidate artifacts theo cửa sổ; mỗi item giữ source IDs.
5. Gộp candidate trùng dựa trên source ID overlap, semantic content và evidence verifier; không chỉ so sánh string giống nhau.
6. Gộp source IDs theo thời gian và gán response IDs sau khi deduplicate.
7. Tạo global summary từ các topic/window summaries có evidence, không nối máy móc các summary riêng.
8. Resolve temporal sau khi merge để mọi candidate dùng cùng anchor date/timezone.
9. Với candidate cùng chủ đề nhưng statement mâu thuẫn giữa windows, giữ cả evidence và yêu cầu review; không loại một phía theo thứ tự xử lý.

### 6.3 Phạm vi MVP và cải tiến

**Tối thiểu cho MVP:** token preflight, single-pass trong context, segment-aligned windows khi cần, overlap giới hạn, deterministic merge, dedup có source refs, global summary có evidence và lỗi có cấu trúc nếu vượt hard limit. Kiểm tra transcript được stitch từ Audio Processing Service bằng fixtures trước khi tích hợp.

**Sau benchmark/Post-MVP:** adaptive window size theo topic, map-reduce nhiều tầng, semantic clustering chuyên biệt, incremental re-extraction theo transcript delta, retrieval index và distributed workers. Không thêm vector database, queue hoặc orchestration framework để xử lý MVP.

## 7. Reliability và security

### 7.1 Reliability

- Tất cả bước có request-level deadline; provider call bị cắt theo remaining request budget.
- Provider adapter chuẩn hóa lỗi và không tự retry không giới hạn. Web Backend quản lý retry policy cho extraction job; đây là tầng duy nhất quyết định retry toàn HTTP request.
- Structured-output repair tối đa một lần, chỉ cho lỗi format/schema có thể sửa; không dùng repair để biến thiếu evidence thành claim.
- Failure ở bất kỳ module được yêu cầu nào làm request non-2xx; không ghi một response completed thiếu module.
- LLM Service stateless; không tạo job, queue, DB hoặc deduplication store. Web dùng meeting/revision/module/config làm logical job key.
- Giới hạn concurrency theo instance, trả 429 CAPACITY_LIMIT/Retry-After khi quá tải thay vì nhận request không giới hạn.
- Provider/model/config có kiểm soát; lỗi credentials không được retry tự động.
- Web Backend chỉ lưu artifact sau khi validate đúng meeting_id, transcript_revision_id, request_id và response contract.

### 7.2 Security và privacy

- Transcript là untrusted user data, không phải instruction. JSON serialization và prompt boundary phải ngăn transcript ghi đè system instructions.
- Không nhận audio/raw ASR payload; không ghi transcript, participant names, API keys, bearer tokens, full prompt hay raw provider response vào logs.
- Logs chỉ lưu request/correlation ID, meeting ID nếu policy cho phép, revision ID, số segments/characters, duration, module set, provider/model/prompt version, token counts, latency và error code.
- Không log evidence snippets; nếu debug cần text, chỉ bật trong môi trường synthetic có thời hạn và quyền truy cập hạn chế.
- Không persist transcript tại LLM Service; dữ liệu trong memory chỉ tồn tại trong thời gian xử lý, cần được giải phóng sau response/failure.
- Chỉ Web Backend được gọi endpoint extraction bằng token riêng; token từ secret manager, rotate được và không commit vào repo.
- Không gắn role/user claims vào transcript; authentication nội bộ xác thực caller service, còn Web chịu trách nhiệm authorization meeting.
- Production egress chỉ tới provider được phê duyệt; đánh giá retention, data region, encryption và provider logging trước khi gửi transcript thật.
- Error envelope không trả stack trace, SQL, đường dẫn filesystem, quota details nhạy cảm hoặc nội dung transcript.
- Logs và metrics tránh cardinality cao; không dùng raw request ID/meeting ID làm metric label.

## 8. Observability và evaluation

### 8.1 Structured logging và metrics

Log JSON có request_id, transcript_revision_id, module set, provider/model, prompt_version, timestamp bắt đầu/kết thúc, latency từng stage, token usage khi provider có, số segments, số windows, số artifact, số artifact review, retry/error code và timeout budget còn lại. Không log transcript body hay prompt.

Metrics đề xuất:

- Request count theo status/error code/provider/model.
- End-to-end latency và latency từng stage.
- Provider timeout, rate-limit, malformed output, repair count, evidence rejection/review.
- Input/output token usage và cost estimate theo bảng giá do nhóm cấu hình; không ghi giá/benchmark giả định trong tài liệu này.
- Window count, transcript characters/segments và tỷ lệ vượt token budget.
- Tỷ lệ item có needs_review, thiếu owner/deadline, temporal exact/range/unresolved.

Correlation dùng request_id từ Web qua log của hai service; nếu truyền distributed trace trong tương lai thì dùng trace context chuẩn, không nhúng transcript trong span attributes.

### 8.2 Đánh giá extraction

Chuẩn bị gold dataset từ transcript có quyền sử dụng, đã loại thông tin nhận diện không cần thiết. Mỗi sample có:

- Transcript segments với speaker, timestamps và transcript revision.
- Meeting context/anchor date/timezone.
- Đáp án do người gán nhãn cho sáu modules, source segment IDs, owner/deadline, temporal state và mâu thuẫn.
- Ghi chú trường hợp không có action/decision, owner không rõ, lời nói mơ hồ, nội dung Việt/Anh trộn và speaker chưa map.
- Quy trình hai người gán nhãn cho subset và phân xử bất đồng; giữ provenance/consent của fixture.

Tách dữ liệu tune prompt và regression; không dùng cùng một sample để vừa điều chỉnh prompt vừa tuyên bố kết quả holdout. Chạy evaluation cố định theo provider, model, prompt version, schema version và cấu hình temporal.

| Metric | Cách tính |
|---|---|
| Precision/Recall/F1 theo artifact | Match item theo business definition và evidence; báo riêng từng module, không chỉ micro-average. |
| Owner accuracy | So sánh owner đã xác nhận; tính riêng null/unassigned và role-based owner. |
| Deadline accuracy | So sánh exact date, date range và unresolved state; sai status cũng tính là lỗi. |
| Evidence grounding accuracy | Tỷ lệ claim có source segment đúng và ngữ nghĩa hỗ trợ; đo referential validity riêng với entailment. |
| Hallucination rate | Claim không được source hỗ trợ trên tổng claim đã phát hành; phân loại bị drop, needs_review và lọt qua verifier. |
| Temporal resolution accuracy | Exact date/range boundaries và needs_review so với gold; báo riêng ngày rõ và phrase mơ hồ. |
| Empty-result behavior | Đo precision khi không có action/decision/follow-up/event; danh sách rỗng phải đúng khi transcript không chứa module đó. |
| Contradiction handling | Đo decision sai do bỏ qua bất đồng và tỷ lệ issue/review được giữ lại khi hội thoại chưa chốt. |

Không đặt benchmark results, target score hoặc quality threshold được phê duyệt khi nhóm chưa có baseline. P11-01/P11-05 ghi số liệu thực, model/config, dataset split, latency, số retry và giới hạn.

## 9. Cấu trúc project đề xuất

Đây là cấu trúc mục tiêu để review trước khi code, không phải các file đã tạo. Task hiện tại chỉ tạo hai Markdown design docs.

~~~text
apps/llm-service/
├── app/
│   ├── main.py                         # Khởi tạo FastAPI và middleware
│   ├── api/
│   │   ├── routes.py                   # GET /health, POST /v1/extractions
│   │   └── dependencies.py             # Auth, config và provider dependencies
│   ├── core/
│   │   ├── config.py                   # Settings, limits và timeout budget
│   │   ├── errors.py                   # Error codes và HTTP mapping
│   │   └── observability.py            # Structured logging và metrics hooks
│   ├── schemas/
│   │   ├── request.py                  # Request Pydantic v2 models
│   │   ├── response.py                 # Sáu module và response/error models
│   │   └── temporal.py                 # TemporalResolution invariants
│   ├── services/
│   │   ├── extraction.py               # Pipeline orchestration trong một request
│   │   ├── context_builder.py          # Transcript/participant context và token budget
│   │   ├── temporal_resolver.py        # Calendar rules thuần Python
│   │   ├── evidence_verifier.py        # Source và semantic evidence checks
│   │   ├── output_validator.py         # Module invariants và repair boundary
│   │   └── transcript_windows.py       # Segment-aligned windowing/merge
│   ├── providers/
│   │   ├── protocol.py                 # Interface nhỏ cho provider
│   │   └── factory.py                  # Tạo adapter đã cấu hình
│   └── prompts/
│       └── v1/
│           ├── system_vi.txt           # System rules tiếng Việt
│           ├── system_en.txt           # System rules tiếng Anh
│           ├── extract.json            # Extraction prompt/version
│           └── verify_evidence.json    # Verifier prompt/version
├── tests/
│   ├── unit/                           # Resolver, validator, builder, merger
│   ├── integration/                    # FastAPI + fake provider
│   ├── contract/                       # Request/response/OpenAPI fixtures
│   └── fixtures/                       # Transcript/gold cases đã được phép dùng
├── pyproject.toml                       # Python 3.12+, dependencies, pytest config
└── Dockerfile                           # Image chạy service độc lập
~~~

Thư mục/file chỉ được tạo khi task tương ứng bắt đầu. Tên provider adapter cụ thể được quyết định sau P00; không tạo placeholder cho provider chưa chọn.

## 10. Implementation roadmap cho LLM Service

Các task dưới đây là breakdown đề xuất nối với roadmap hiện tại, không đánh dấu trạng thái hoàn thành và không sửa implementation-roadmap.md. P00 là prerequisite quyết định provider, schema và data policy. Ưu tiên/cost là ước lượng thiết kế: P0 cần để bắt đầu integration, P1 cần cho M2/MVP, P2 là cải tiến benchmark-driven; complexity S/M/L tương ứng nhỏ/vừa/lớn.

### LLM-01 — Contract models và fixtures

- **Objective:** Chuyển contract v1 thành Pydantic request/response/error models và fixtures dùng chung.
- **Deliverables:** Request/response schemas cho sáu modules, error model, OpenAPI snapshots/fixtures, validation invariants và examples parse được.
- **Dependencies:** P00-04; nhóm duyệt open questions làm thay đổi schema. Có thể bắt đầu trước khi Audio Processing Service/Web Backend hoàn tất.
- **Affected components:** app/schemas/, tests/contract/, tests/fixtures/.
- **Implementation approach:** extra='forbid', date/timezone parsing tường minh, module keys cố định, null/empty semantics đúng contract; không tạo DB model.
- **Acceptance Criteria:** Full request/response, Summary+Actions subset, empty list, temporal states và error envelope pass schema; unknown field/version sai bị từ chối.
- **Testing strategy:** Unit validation và contract tests offline; kiểm tra OpenAPI sinh từ FastAPI ở task runtime.
- **Priority / complexity:** P0 / M.
- **Roadmap mapping:** P00-04, P01-01, P07-01.

### LLM-02 — FastAPI runtime, health, auth và config

- **Objective:** Tạo HTTP runtime riêng có thể chạy/deploy độc lập.
- **Deliverables:** FastAPI app, GET /health, POST /v1/extractions skeleton, /openapi.json, bearer dependency, settings, Dockerfile và pyproject.toml.
- **Dependencies:** LLM-01 cho response shape; không phụ thuộc API backend đã implement.
- **Affected components:** app/main.py, app/api/, app/core/, Dockerfile, pyproject.toml.
- **Implementation approach:** Dependency injection cho fake/real provider; route chỉ gọi service layer; health không gọi provider; không kết nối DB/queue.
- **Acceptance Criteria:** Service khởi động Python 3.12+, auth đúng, OpenAPI phản ánh contract, health không lộ secrets và process dừng graceful.
- **Testing strategy:** FastAPI TestClient với auth hợp lệ/sai, health/OpenAPI và error serialization.
- **Priority / complexity:** P0 / M.
- **Roadmap mapping:** Mở rộng P01-01 cho service mới; tích hợp setup tại P11-04.

### LLM-03 — Provider adapter và P03 Summary/Actions

- **Objective:** Tạo structured extraction ban đầu cho Summary và Action Items.
- **Deliverables:** LLMProvider protocol, adapter đầu tiên sau khi nhóm chọn provider, versioned prompt, Summary/Actions output và fake provider.
- **Dependencies:** LLM-01/02; transcript fixtures đủ để làm trước ASR thật.
- **Affected components:** app/providers/, app/prompts/v1/, app/services/extraction.py, schemas và integration tests.
- **Implementation approach:** Một generation pass cho requested modules; metadata summary copy/tính từ request; owner/deadline không rõ giữ null/review; không chọn provider trong tài liệu này.
- **Acceptance Criteria:** Summary + Actions response khớp schema/source IDs; lỗi provider map đúng envelope; P03-04 fixture pass trước khi provider thật được nghiệm thu.
- **Testing strategy:** Fake provider cho deterministic tests; integration provider thật chỉ chạy bằng credential/dataset đã được nhóm duyệt, tách khỏi CI mặc định.
- **Priority / complexity:** P0 / M.
- **Roadmap mapping:** P03-04, refine tại P07-02, tích hợp end-to-end P03-06.

### LLM-04 — TemporalResolver

- **Objective:** Resolve relative date trong Actions, Follow-ups và Timeline bằng quy tắc deterministic.
- **Deliverables:** TemporalResolver, ba trạng thái date, raw phrase/evidence preservation và shared resolution output.
- **Dependencies:** LLM-01 schema; có thể phát triển song song LLM-03 bằng calendar fixtures.
- **Affected components:** app/schemas/temporal.py, app/services/temporal_resolver.py, tests/unit/.
- **Implementation approach:** LLM chỉ nhận diện raw phrase; Python calendar rules nhận anchor_date và IANA timezone; không gọi system clock.
- **Acceptance Criteria:** Ví dụ 2026-10-05 → Friday 2026-10-09, next week range 2026-10-12..2026-10-18, cuối tháng 2026-10-31; ambiguous giữ unresolved.
- **Testing strategy:** Table-driven unit tests weekday boundaries, leap years, month/year rollover, invalid timezone và câu thiếu ngữ cảnh.
- **Priority / complexity:** P1 / M.
- **Roadmap mapping:** P08-01, P08-02, P08-04, đồng bộ persistence với P08-03.

### LLM-05 — Decision, Open Issues, Follow-ups và Timeline

- **Objective:** Mở rộng extraction từ hai module đầu sang đủ sáu business modules.
- **Deliverables:** Prompt/schema bốn module còn lại, ranh giới decision/proposal, issue/follow-up và timeline fields.
- **Dependencies:** LLM-01/02/03; có thể làm song song LLM-04 trên fixtures nhưng integration dùng chung temporal model.
- **Affected components:** app/prompts/, app/schemas/response.py, app/services/extraction.py, unit/integration fixtures.
- **Implementation approach:** Giữ sáu response keys cố định; chỉ chạy modules yêu cầu; dùng IDs gán server-side; raw statements/source evidence luôn giữ.
- **Acceptance Criteria:** Decision chỉ là lựa chọn đã chốt; open issue unresolved; follow-up khác task; timeline chỉ có event nói trong transcript; empty module trả [].
- **Testing strategy:** Vietnamese/English fixtures có proposal, disagreement, no-item và overlapping module cases.
- **Priority / complexity:** P1 / M.
- **Roadmap mapping:** P07-01, P07-03, P07-04.

### LLM-06 — Evidence verifier và output validation

- **Objective:** Không phát hành claim chỉ vì model trả segment ID tồn tại.
- **Deliverables:** Source index validator, semantic verifier batch, needs_review/drop policy, timestamp derivation và bounded schema repair.
- **Dependencies:** LLM-01/03/05; verifier có thể làm bằng fake fixture trước khi Web/Audio integration xong.
- **Affected components:** app/services/evidence_verifier.py, output_validator.py, response.py, tests/contract.
- **Implementation approach:** Deterministic kiểm tra IDs/same request/revision/subset/order/timestamp; verifier kiểm tra semantic support; một repair tối đa cho schema, không repair facts thiếu evidence.
- **Acceptance Criteria:** Source ID sai bị từ chối; claim không được support bị review/drop; module không có output dùng được trả UNVERIFIED_EVIDENCE; không trả 200 partial.
- **Testing strategy:** Positive/negative entailment fixtures, cross-revision ID, forged timestamp, missing owner/evidence và invalid review invariants.
- **Priority / complexity:** P1 / L.
- **Roadmap mapping:** P07-05 và P07-06.

### LLM-07 — Token budget và long-transcript windows

- **Objective:** Xử lý transcript dài mà không làm mất segment/source alignment.
- **Deliverables:** Token preflight, segment-aligned window builder, bounded overlap, artifact aggregation/dedup và global summary synthesis.
- **Dependencies:** LLM-01/03/05; fixture transcript tự tạo đủ trước khi P05 audio chunking hoàn tất.
- **Affected components:** app/services/context_builder.py, transcript_windows.py, extraction.py, tests/fixtures.
- **Implementation approach:** Single pass khi vừa context; trên budget chia windows, giữ global segment IDs, merge rồi resolve temporal; vượt hard cap trả TRANSCRIPT_TOO_LONG.
- **Acceptance Criteria:** Mọi segment được xử lý hoặc request fail rõ ràng; không mất source ID, không tạo item trùng tại overlap, giữ contradiction giữa windows.
- **Testing strategy:** Synthetic windows ở ranh giới segment, duplicate overlap, dài hơn context và mâu thuẫn xuyên cửa sổ; không cần model thật cho merge mechanics.
- **Priority / complexity:** P1 / L.
- **Roadmap mapping:** Liên quan P05-01/P05-02/P05-06 về transcript gốc và P07-06 về extraction; đây là windowing văn bản phía LLM, không thay audio chunking.

### LLM-08 — Reliability, privacy và observability

- **Objective:** Giới hạn lỗi, chi phí và dữ liệu nhạy cảm trong vận hành.
- **Deliverables:** Request/provider deadlines, concurrency limit, error mapping, structured logs, latency/token metrics, secret handling và documented run config.
- **Dependencies:** LLM-02/03; làm song song với extraction features.
- **Affected components:** app/core/config.py, errors, provider adapter, API dependencies và deployment config.
- **Implementation approach:** Retry toàn job do Web quyết định; không lưu transcript/log body; chỉ một structured repair; health tách khỏi provider.
- **Acceptance Criteria:** Lỗi transient/permanent map đúng; capacity trả 429; không lộ secrets/transcript; per-request budget được enforce.
- **Testing strategy:** Fake provider timeout/rate-limit/malformed response; log capture assertions; concurrency-limit tests.
- **Priority / complexity:** P1 / M.
- **Roadmap mapping:** P03-02 error handling, P05-04 retry boundaries, P11-04 reproducible setup.

### LLM-09 — Gold evaluation và acceptance

- **Objective:** Đo chất lượng extraction thật mà không bịa benchmark hoặc dùng một demo để kết luận.
- **Deliverables:** Consent/anonymization notes, gold dataset split, scoring script, regression report theo module/model/prompt và end-to-end evidence.
- **Dependencies:** LLM-03 đến LLM-08; cần provider thật, normalized transcript và Web persistence cho full live path.
- **Affected components:** tests/fixtures/, evaluation tooling, docs/report generated sau khi chạy.
- **Implementation approach:** Đo precision/recall/F1 từng module, owner/deadline, evidence entailment, hallucination, temporal state và empty/contradictory cases; nhóm chốt threshold sau baseline.
- **Acceptance Criteria:** Kết quả lưu config, dataset version, số lần retry/latency; tách fixture/mock khỏi provider thật; không ghi threshold chưa duyệt.
- **Testing strategy:** Offline regression trên holdout fixtures; P11-05 live provider acceptance trên audio/transcript có quyền sử dụng.
- **Priority / complexity:** P1 / M.
- **Roadmap mapping:** P07-06, P11-01 và P11-05.

### 10.1 Parallel work và checkpoints

- LLM-01/02 có thể làm khi Web và Audio Processing mới ở P00/P01; JSON fixtures thay thế service còn thiếu.
- LLM-03 Summary/Actions và LLM-04 TemporalResolver có thể làm song song khi contract đã ổn định.
- LLM-05 module bổ sung có thể dùng normalized transcript fixtures trước khi diarization hoàn thành; speaker ID null phải được test.
- Web Backend có thể implement request client, job state và response persistence song song từ LLM-01; Audio Processing có thể đảm bảo segment IDs/timestamps tương thích mà không chờ LLM provider.
- LLM-06 verifier và LLM-07 windowing có thể triển khai trên fixtures; integration chỉ cần khi API contracts của ba service đã được chốt.
- P03-06 là checkpoint đầu tiên gọi ASR/LLM provider thật; P07-05/06 là checkpoint sáu modules và evidence; P08-04 temporal; P11-01/05 evaluation/end-to-end.
- Task có thể hoàn tất độc lập nếu đạt acceptance fixtures; không đánh dấu tích hợp thật hoàn tất khi chỉ dùng fake provider.

## 11. Architecture Decisions và trade-offs

| Quyết định | Trạng thái | Lựa chọn/Trade-off |
|---|---|---|
| Python/FastAPI hay TypeScript/NestJS | **Proposed decision** | Dùng Python 3.12+, FastAPI, Pydantic v2 theo baseline: schema validation/AI adapter dễ cô lập; đổi lại repo thêm runtime/toolchain ngoài Next/Nest/pnpm. Không xem đây là stack đã có trong repo. |
| REST hay message queue giữa Web và LLM | **Confirmed requirement** | REST/JSON đồng bộ tại boundary; Web job chạy background. Đơn giản, dễ contract-test; request dài cần timeout budget phù hợp. Queue riêng ở LLM không cần trong MVP. |
| Stateless hay stateful LLM Service | **Confirmed requirement** | Stateless, không DB/job store; Web sở hữu dedupe, job state và persistence. Điều này scale đơn giản nhưng retry sau timeout có thể gọi provider lần nữa. |
| Single-pass hay multi-stage extraction | **Proposed decision** | Một generation cho tất cả module được yêu cầu trong một window, deterministic temporal, batched evidence verifier và tối đa một schema repair. Cân bằng cost/latency với correctness; benchmark mới quyết định tách stage/module. |
| LLM-only hay hybrid temporal resolution | **Proposed decision theo yêu cầu thiết kế** | LLM phát hiện phrase/context; Python calendar rules tính ngày/range. Tính deterministic và test được; phrase tự nhiên mơ hồ vẫn phải needs_review. |
| Synchronous request hay asynchronous worker API | **Confirmed requirement** | POST /v1/extractions giữ HTTP đến khi xong; Web quản lý background job. Không tạo 202, polling hoặc queue ở LLM Service. |
| Provider-specific hay provider-agnostic | **Confirmed requirement** | Contract provider-neutral và có adapter/configurable provider; MVP chỉ triển khai một adapter thật sau P00. Trade-off là interface nhỏ cần map capability/token/error khác nhau. |
| Bearer token và private networking | **Proposed decision** | Token service-to-service + private network là baseline nhẹ; cần nhóm chốt secret distribution, TLS termination, rotation và môi trường local. |
| Evidence verifier pass | **Proposed decision** | Một batch verification riêng cho semantic entailment; tăng token/latency nhưng đáp ứng yêu cầu source grounding. Có thể thay đổi sau evaluation, không được coi ID hợp lệ là đủ. |
| Windowing transcript dài | **Proposed MVP decision** | Segment-aligned window + bounded overlap/dedup; giữ evidence mà không thêm queue/vector store. Map-reduce phức tạp chỉ sau benchmark. |

## 12. Open questions và phụ thuộc tích hợp

| Câu hỏi/phụ thuộc | Ảnh hưởng | Người/phase cần quyết định |
|---|---|---|
| Provider/model LLM nào được phép dùng? | Adapter capability, token budget, structured-output support, cost, latency, region và retention. | Nhóm/P00-03; trước provider integration P03-04. |
| Provider có được nhận transcript chứa dữ liệu meeting thật không; retention/region ra sao? | Privacy, consent, secrets và data policy. | Nhóm trước P03 live provider/P11-05. |
| meeting.timezone lấy từ đâu? | Prisma hiện chưa có timezone; không được fallback theo timezone process. | Web Backend/P00-02/P00-04; bổ sung metadata ngoài task docs này. |
| Participants, speaker mapping, duration và transcript revision lưu ở đâu? | Request yêu cầu các field này nhưng Prisma hiện chỉ có title/anchorDate. | Web Backend/P02/P03/P07-01. |
| Action candidate không có owner có được trả ở dạng needs_review? | Product criteria nói owner identifiable; Roadmap cho phép field chưa rõ/null. | Product/BE/AI trước P03-04/P07-02. |
| “Cuối tháng” là đúng ngày cuối tháng hay khoảng cuối tháng? | Temporal exactness và deadline UX. | Nhóm/P08-01; thiết kế hiện đề xuất ngày cuối tháng theo ví dụ gốc. |
| Có hiển thị Meeting Anchor như Timeline Event không? | Product sample có event synthetic không có transcript evidence. | Product/UI/BE trước P07-01; thiết kế hiện để Web render từ metadata. |
| Error envelope có dùng chung với Nest API không? | Client error parsing và public conventions. API hiện chỉ có health route. | BE/P00-04; không có contract file trong refs local. |
| Timeout, byte limit, token limit và concurrency cap cụ thể? | Capacity, reverse proxy, job timeout và cost. | Nhóm sau benchmark P03/P11; con số đề xuất không phải SLA. |
| Evidence verifier cần threshold nào để tự đánh dấu verified? | Rủi ro claim sai và tỷ lệ review. | AI/Product sau khi có gold set P07-06/P11-01; hiện không đặt threshold. |
| Root AGENTS.md có cần đồng bộ mô tả repo? | Guidance hiện nói chưa có source trong khi code skeleton đã có. | Repository maintainers trong task docs riêng; phạm vi này không sửa file đó. |

### 12.1 Mâu thuẫn temporal cần lưu ý

Product Description/Feature Overview có ví dụ không nhất quán về “Thứ 6” từ anchor 2026-10-05: có chỗ ghi 2026-10-08, có chỗ 2026-10-09; ngày 08/10/2026 là thứ Năm. Implementation Roadmap xác định ngày đúng là 2026-10-09 và yêu cầu “Tuần sau” là khoảng 2026-10-12–2026-10-18, không tự gán ngày 12. Hai tài liệu mới dùng quy tắc của Roadmap, nhưng việc sửa tài liệu gốc nằm ngoài phạm vi hiện tại.

Product Description còn đưa “Meeting (Anchor)” vào ví dụ Timeline với timestamp 00:00:00, trong khi định nghĩa Timeline là mốc dự án được nói và contract yêu cầu mọi artifact có source evidence. Thiết kế hiện không tạo timeline artifact tổng hợp từ metadata; Web có thể hiển thị meeting date riêng. Nhóm cần chốt trước khi persistence/UI dựa vào semantics này.
