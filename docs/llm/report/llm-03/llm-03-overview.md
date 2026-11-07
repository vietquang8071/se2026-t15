# LLM-03 — Provider Adapter & Summary/Actions Extraction

**Project:** SE2026-T15 — Meeting Minutes Assistant  
**Component:** LLM Service  
**Task ID:** LLM-03  
**Priority:** P0  
**Complexity:** M  
**Status:** Proposed — Pending Implementation  
**Roadmap Mapping:** P00-03, P03-04, P03-06, P07-02

---

## 1. Overview

### 1.1. Background

LLM Service là một trong các thành phần xử lý AI của Meeting Minutes Assistant, chịu trách nhiệm chuyển normalized transcript thành các structured meeting artifacts.

Trước LLM-03, hệ thống đã có hai nền tảng:

**LLM-01 — Contract Models & Fixtures**

- Pydantic v2 request/response schemas.
- Schemas cho sáu business modules.
- Temporal resolution models.
- Error envelope.
- Contract validation và synthetic fixtures.

**LLM-02 — FastAPI Runtime**

- FastAPI application.
- `GET /health`.
- `POST /v1/extractions`.
- Bearer authentication.
- Application configuration.
- Dependency injection.
- HTTP error handling.
- OpenAPI và Docker runtime.

Ở LLM-02, extraction endpoint mới là skeleton. `UnconfiguredExtractionService` trả lỗi có cấu trúc vì chưa có extraction implementation thật.

**LLM-03 là bước đầu tiên tích hợp một LLM provider thật vào service để thực hiện structured extraction.**

### 1.2. Objective

Xây dựng extraction pipeline ban đầu để chuyển normalized transcript thành:

1. **Meeting Summary:** Tóm tắt cuộc họp, các chủ đề chính và nội dung thảo luận.
2. **Action Items:** Các công việc được giao hoặc cam kết, kèm owner, deadline và source references khi có đủ bằng chứng.

Kết quả phải tuân thủ API Contract v1, được validate bằng Pydantic models và không được tạo thông tin không xuất hiện trong transcript.

### 1.3. Expected Outcome

Sau khi LLM-03 hoàn thành, một request hợp lệ chỉ yêu cầu `meeting_summary` và `action_items` có thể:

1. Đi qua FastAPI authentication và request validation.
2. Được chuyển đến ExtractionService.
3. Gọi một LLM provider thật.
4. Nhận structured extraction output.
5. Kiểm tra schema và source references.
6. Tạo response đúng Contract v1 hoặc trả structured error.

LLM-03 phải hoạt động được với synthetic transcript mà không cần chờ Audio Processing Service hoặc Web Backend hoàn tất.

---

## 2. Scope

### 2.1. In Scope

- Lựa chọn và cấu hình một LLM provider.
- Thiết kế `LLMProvider` abstraction.
- Implement một provider adapter thật.
- Implement fake provider cho automated tests.
- Thiết kế versioned prompts cho Summary và Action Items.
- Xây dựng extraction orchestration.
- Sinh structured outputs đúng Pydantic schemas.
- Bảo toàn metadata từ request.
- Validate source IDs và dẫn xuất timestamps.
- Kiểm soát thông tin chưa chắc chắn và hallucination.
- Chuẩn hóa provider errors.
- Bổ sung processing metadata.
- Kiểm thử offline và kiểm thử với provider thật.
- Kiểm soát chi phí inference và tránh lộ dữ liệu nhạy cảm.

### 2.2. Out of Scope

Các chức năng sau không thuộc LLM-03:

- Audio transcription.
- Speaker diarization.
- Web Backend job orchestration.
- Database persistence.
- Decision Log extraction.
- Open Issues extraction.
- Follow-up Items extraction.
- Timeline Events extraction.
- TemporalResolver hoàn chỉnh cho relative dates.
- Long-transcript windowing và aggregation.
- EvidenceVerifier tổng quát cho cả sáu modules.
- Gold dataset benchmark quy mô lớn.
- Multi-provider routing hoặc multi-agent orchestration.

Các phần này thuộc LLM-04 đến LLM-09 hoặc các task của service khác.

### 2.3. Supported Modules

Trong phạm vi LLM-03:

| Module | Trạng thái mục tiêu |
|---|---|
| `meeting_summary` | Supported |
| `action_items` | Supported |
| `decision_log` | Deferred — LLM-05 |
| `open_issues` | Deferred — LLM-05 |
| `follow_up_items` | Deferred — LLM-05 |
| `timeline_events` | Deferred — LLM-05 |

Success response vẫn phải chứa đầy đủ sáu module keys. Các module không được yêu cầu có giá trị `null`.

Request chứa module chưa hỗ trợ không được trả `200 completed` giả. Cần thống nhất error behavior tương thích với Contract v1 trước khi triển khai.

---

## 3. Proposed Architecture

### 3.1. Extraction Pipeline

```text
POST /v1/extractions
        |
        v
FastAPI HTTP Layer
- Bearer Authentication
- Request Validation
- Request Timeout
        |
        v
ExtractionService
        |
        +--> Check Supported Modules
        |
        +--> Prepare Meeting Context
        |
        +--> Prepare Transcript Segments
        |
        +--> Build Versioned Prompts
        |
        v
LLMProvider Interface
        |
        v
OpenRouter Adapter
        |
        v
Selected LLM Model
        |
        v
Structured Candidate Output
        |
        +--> Parse / Validate Schema
        |
        +--> Copy Meeting Metadata
        |
        +--> Normalize Action Items
        |
        +--> Validate Source References
        |
        +--> Derive Source Timestamps
        |
        +--> Check Evidence & Review Flags
        |
        v
ExtractionResponse (Contract v1)
        |
        v
HTTP 200 or Structured Error
```

### 3.2. Design Principles

**Provider Independence**

ExtractionService không được phụ thuộc trực tiếp vào OpenRouter SDK hoặc model-specific response format.

**Contract First**

Pydantic schemas từ LLM-01 là nguồn xác thực output cuối cùng.

**Separation of Concerns**

- API layer xử lý HTTP.
- ExtractionService điều phối extraction.
- Provider adapter xử lý giao tiếp với LLM.
- Prompt layer quản lý extraction instructions.
- Validation layer kiểm tra output và source references.

**Traceability**

Mỗi claim được phát hành phải có source IDs hợp lệ, có thể truy ngược tới transcript segments.

**No Fabrication**

Không tự tạo owner, deadline, priority hoặc meeting decisions.

**Cost Awareness**

Automated tests mặc định phải chạy offline và không phát sinh chi phí API.

---

## 4. Provider Strategy

### 4.1. Initial Provider

**Proposed Gateway:** OpenRouter

Lý do:

- Đã có OpenRouter API key để phát triển.
- API tương thích với OpenAI Chat Completions.
- Có thể thay đổi model bằng configuration.
- Hỗ trợ thử nghiệm các model miễn phí và trả phí.
- Không cần viết adapter riêng cho từng model trong giai đoạn đầu.

OpenRouter là gateway, không đồng nghĩa với việc một model cụ thể đã được lựa chọn chính thức.

### 4.2. Model Selection Strategy

Sử dụng ba chế độ kiểm thử:

| Mode | Model | Purpose |
|---|---|---|
| Offline | Fake Provider | Unit, contract và integration tests |
| Development | Free model trên OpenRouter | API smoke tests, prompt experiments |
| Integration | Low-cost paid model có structured output | Schema và extraction quality tests |

Model IDs, giá/token, free-tier limits và khả năng hỗ trợ JSON Schema phải được xác nhận tại thời điểm lựa chọn.

Không hardcode model ID vào ExtractionService.

### 4.3. Provider Configuration

Các cấu hình dự kiến:

```text
OPENROUTER_API_KEY
OPENROUTER_BASE_URL
OPENROUTER_MODEL
OPENROUTER_MAX_OUTPUT_TOKENS
OPENROUTER_TEMPERATURE
```

Tận dụng các timeout settings đã có trong LLM-02.

Không hardcode API keys. Không commit `.env` chứa credentials.

Phân biệt:

- `LLM_SERVICE_TOKEN`: Xác thực giữa Web Backend và LLM Service.
- `OPENROUTER_API_KEY`: Xác thực với OpenRouter.

### 4.4. Data Privacy

Trước khi gửi transcript thật tới provider, cần xác nhận:

- Quyền sử dụng transcript và sự đồng ý của những người liên quan.
- Chính sách lưu trữ dữ liệu của OpenRouter và underlying model provider.
- Data retention và training/data collection settings.
- Các giới hạn lưu log và dữ liệu nhạy cảm.

Trong giai đoạn phát triển ban đầu, chỉ sử dụng synthetic transcripts hoặc dữ liệu đã được phép sử dụng.

---

## 5. Milestone Breakdown

LLM-03 được chia thành bảy mốc triển khai tuần tự. Một số phần có thể phát triển song song sau khi các interface đã ổn định.

### LLM-03.1 — Provider Selection & Configuration

**Objective:** Chọn gateway/model thử nghiệm và chuẩn hóa cấu hình provider.

**Tasks:**

1. Xác nhận OpenRouter làm provider gateway cho MVP.
2. Kiểm tra API key bằng một request đơn giản.
3. Chọn một model phục vụ development smoke tests.
4. Chọn một model giá thấp có structured output phù hợp.
5. Xác nhận JSON mode và JSON Schema compatibility.
6. Xác định timeout, token limits và chi phí thử nghiệm.
7. Thiết kế environment settings.
8. Xác nhận chính sách sử dụng dữ liệu trong giai đoạn test.

**Deliverables:**

- Provider/model decision.
- Configuration specification.
- Cost-control policy.
- Successful manual API smoke test.
- Ghi nhận giới hạn của các model được chọn.

**Acceptance Criteria:**

- Có thể gọi OpenRouter thành công.
- Model được xác định bằng configuration.
- API key không xuất hiện trong repository hoặc logs.
- Không bắt buộc sử dụng paid model để chạy automated tests.
- Chi phí test có thể được giới hạn.

**Dependencies:** LLM-02.

**Complexity:** S.

---

### LLM-03.2 — Provider Interface & Adapter

**Objective:** Tạo abstraction tách application logic khỏi provider API.

**Tasks:**

1. Định nghĩa `LLMProvider` protocol.
2. Định nghĩa provider request/result types tối thiểu.
3. Implement OpenRouter adapter.
4. Hỗ trợ structured generation.
5. Xử lý model configuration và request timeout.
6. Chuẩn hóa provider errors.
7. Thu thập token usage và model metadata.
8. Implement fake provider có deterministic responses.
9. Viết unit tests cho adapter và error mapping.

**Proposed Components:**

```text
app/providers/
    protocol.py
    openrouter.py
    fake.py
```

Tên file chỉ là đề xuất; cấu trúc cuối cùng phải phù hợp code hiện có.

**Deliverables:**

- `LLMProvider` interface.
- OpenRouter adapter.
- Fake provider.
- Provider result model.
- Typed provider errors.
- Adapter tests.

**Acceptance Criteria:**

- ExtractionService không import OpenRouter SDK trực tiếp.
- Có thể thay fake/real provider bằng dependency injection.
- Có thể đổi model qua configuration.
- Timeout, rate limit và provider failures được phân loại.
- Không log secrets hoặc raw transcript.
- Automated tests không cần kết nối mạng.

**Dependencies:** LLM-03.1.

**Complexity:** M.

---

### LLM-03.3 — Versioned Prompts & Extraction Schema

**Objective:** Thiết kế prompt để model trích xuất Summary và Action Items có cấu trúc.

**Tasks:**

1. Xây dựng system prompt.
2. Xây dựng extraction prompt template.
3. Định nghĩa candidate output schema.
4. Chuẩn hóa cách đưa transcript segments vào prompt.
5. Xác định quy tắc multilingual output (`vi`/`en`).
6. Quy định source citation và no-fabrication rules.
7. Chống prompt injection từ transcript.
8. Bổ sung versioning cho prompt.
9. Viết tests cho prompt rendering.

**Suggested Structure:**

```text
app/prompts/
    v1/
        system.txt
        summary_actions.txt
```

**Prompt Requirements:**

- Transcript được truyền như dữ liệu, không phải instruction.
- Không tự suy luận speaker identity.
- Không tự gán owner nếu chưa xác định.
- Không tự đặt deadline hoặc priority.
- Chỉ tạo Action Item khi có commitment rõ ràng.
- Summary phải phản ánh đúng nội dung đã được nói.
- Mỗi claim phải liên kết với source segments.
- Không yêu cầu chain-of-thought.

**Deliverables:**

- Versioned prompt templates.
- Candidate structured output schema.
- Prompt rendering helpers.
- Prompt tests.

**Acceptance Criteria:**

- Prompt được lưu độc lập với route handler.
- Source segment IDs được giữ nguyên.
- Thay prompt version có thể truy vết trong processing metadata.
- Prompt không chứa credentials.
- Candidate schema không bắt LLM phải tự sinh metadata có thể dẫn xuất bằng Python.

**Dependencies:** LLM-01 và provider interface.

**Complexity:** M.

---

### LLM-03.4 — Summary/Actions Extraction Service

**Objective:** Kết nối provider adapter, prompts và FastAPI runtime thành extraction pipeline.

**Tasks:**

1. Implement concrete ExtractionService.
2. Tích hợp provider qua dependency injection.
3. Kiểm tra requested modules thuộc phạm vi hỗ trợ.
4. Chuẩn bị normalized transcript context.
5. Gọi provider bằng versioned prompt.
6. Parse structured output.
7. Tạo Meeting Summary.
8. Tạo Action Items.
9. Gắn processing metadata.
10. Trả response qua existing FastAPI route.

**Summary Rules:**

- `title` lấy từ meeting metadata.
- `date` lấy từ `anchor_date`.
- `duration_minutes` tính từ `duration_seconds`.
- `participants` lấy từ danh sách participant metadata.
- `overview` và `key_topics` dựa trên transcript.

**Action Item Rules:**

- `task` phải có bằng chứng.
- `owner` có thể là `null`.
- Deadline không rõ không được tự suy ra.
- `priority` mặc định `null` nếu không có căn cứ.
- Source IDs phải tồn tại trong transcript.

**Deliverables:**

- Concrete ExtractionService.
- Summary extraction.
- Action Items extraction.
- Dependency injection integration.
- Response construction.

**Acceptance Criteria:**

- Có thể gọi service qua `POST /v1/extractions`.
- `meeting_summary` và `action_items` trả đúng schema.
- Các module chưa yêu cầu là `null`.
- Không trả fake extraction success.
- Không có provider logic trong FastAPI route.
- Request IDs và transcript revision ID được bảo toàn.

**Dependencies:** LLM-03.2 và LLM-03.3.

**Complexity:** M.

---

### LLM-03.5 — Output Validation, Evidence & Error Mapping

**Objective:** Bảo đảm dữ liệu provider trả về an toàn và đúng contract trước khi phát hành.

**Tasks:**

1. Validate structured candidate bằng Pydantic.
2. Kiểm tra source segment IDs tồn tại trong transcript.
3. Tính `source_timestamp` từ segment bắt đầu sớm nhất.
4. Gán artifact IDs theo thứ tự response.
5. Kiểm tra owner, priority và nullable fields.
6. Kiểm tra consistency của review flags.
7. Xử lý explicit dates và unresolved deadlines.
8. Bảo đảm metadata Summary khớp request.
9. Chuẩn hóa invalid output/provider failures thành `ErrorEnvelope`.
10. Giới hạn số lần structured-output repair.
11. Xác định và triển khai mức semantic evidence checking tối thiểu cần thiết cho hai module.

**Temporal Boundary:**

LLM-04 mới xử lý relative dates đầy đủ. Ở LLM-03:

- Ngày tuyệt đối rõ ràng có thể được parse và validate bằng logic deterministic.
- Biểu thức tương đối chưa được hỗ trợ phải giữ nguyên raw expression và được đánh dấu unresolved/review.
- Không để model tự diễn giải relative date thành exact date thiếu kiểm chứng.

**Evidence Boundary:**

LLM-06 xây dựng EvidenceVerifier đầy đủ. Tuy nhiên, Contract v1 đã yêu cầu source grounding và evidence checks trước khi trả `200 completed`.

Do đó, LLM-03 phải có một bước kiểm tra evidence tối thiểu có ý nghĩa thực tế cho Summary/Actions, hoặc nhóm phải điều chỉnh mốc nghiệm thu contract-compliant success cho phù hợp.

Không được sử dụng source ID hợp lệ như bằng chứng duy nhất rằng claim được transcript hỗ trợ.

Không điền `evidence_prompt_version` giả nếu thực tế chưa chạy bước verification tương ứng.

**Deliverables:**

- Output validation pipeline.
- Source reference validation.
- Deterministic timestamp derivation.
- Artifact ID assignment.
- Review-state safeguards.
- Error mapping.
- Validation tests.

**Acceptance Criteria:**

- Invalid source IDs bị từ chối.
- Invalid structured output không được trả HTTP 200.
- Owner chưa xác định không bị trình bày như đã xác nhận.
- Temporal uncertainty được phản ánh đúng trong artifact.
- Response không chứa fabricated metadata.
- Provider failures được ánh xạ đúng HTTP error contract.

**Dependencies:** LLM-03.4.

**Complexity:** M–L.

---

### LLM-03.6 — Offline Tests & Contract Integration

**Objective:** Kiểm thử toàn bộ pipeline mà không phụ thuộc provider thật.

**Tasks:**

1. Viết unit tests cho prompt rendering.
2. Viết provider adapter tests.
3. Viết ExtractionService tests.
4. Viết FastAPI integration tests với fake provider.
5. Kiểm thử valid Summary + Actions response.
6. Kiểm thử response có Action Items rỗng.
7. Kiểm thử owner chưa rõ.
8. Kiểm thử invalid JSON và invalid schema.
9. Kiểm thử source references không tồn tại.
10. Kiểm thử provider timeout, rate limit và errors.
11. Chạy regression suite LLM-01/02.

**Example Test Cases:**

| Scenario | Expected |
|---|---|
| Transcript có quyết định giao việc rõ | Action Item hợp lệ |
| Transcript không có công việc được giao | `action_items: []` |
| Task rõ nhưng owner chưa xác nhận | `owner: null`, `needs_review: true` |
| Transcript có deadline mơ hồ | Giữ raw phrase, không tạo exact date giả |
| Provider trả malformed JSON | Structured error |
| Provider trả source ID không tồn tại | Output bị từ chối |
| Provider timeout | `504 PROVIDER_TIMEOUT` |
| Provider rate limit | `503 PROVIDER_RATE_LIMIT` |
| Chỉ yêu cầu Summary | Action Items và bốn module còn lại `null` |
| Request yêu cầu module chưa hỗ trợ | Không trả `200 completed` giả |

**Deliverables:**

- Unit tests.
- Offline integration tests.
- Synthetic fixtures.
- Regression test results.

**Acceptance Criteria:**

- Fake provider tests chạy offline.
- Không yêu cầu API key khi chạy pytest mặc định.
- LLM-01 và LLM-02 tests tiếp tục pass.
- Error scenarios được kiểm thử.
- Test results deterministic và có thể chạy lại.

**Dependencies:** LLM-03.2–03.5.

**Complexity:** M.

---

### LLM-03.7 — Real Provider Integration & Cost Evaluation

**Objective:** Xác minh extraction pipeline hoạt động thực tế với OpenRouter.

**Tasks:**

1. Chuẩn bị synthetic Vietnamese meeting transcripts.
2. Chạy thử model miễn phí trên transcript ngắn.
3. Chạy thử model hỗ trợ structured output đáng tin cậy.
4. Kiểm tra schema compliance.
5. Đánh giá chất lượng Summary.
6. Đánh giá precision của Action Items.
7. Kiểm tra hallucinated owner/deadline.
8. Thu thập input/output token usage.
9. Ước tính chi phí mỗi meeting.
10. Ghi nhận latency, failure modes và model configuration.

**Cost Optimization Strategy:**

- Không gọi provider trong CI mặc định.
- Cố định model trong mỗi lần benchmark.
- Giới hạn transcript length và output tokens khi thử nghiệm.
- Dùng fake provider cho phần lớn tests.
- Giới hạn số lượng real API requests.
- Không retry vô hạn.
- Không chạy mọi prompt variation trên toàn bộ test suite.
- Ghi token usage và estimated cost theo model.
- Ưu tiên free-tier smoke test, chỉ dùng paid model cho validation có giá trị.

**Deliverables:**

- Real-provider smoke test.
- Test dataset có quyền sử dụng.
- Model/configuration record.
- Latency và token usage report.
- Cost estimate.
- Known limitations.

**Acceptance Criteria:**

- Ít nhất một real-provider extraction thành công, được validate bằng Contract v1.
- Kết quả có source references kiểm tra được.
- Không phát sinh fabricated owner/deadline trong các test cases bắt buộc.
- Chi phí test được ghi nhận.
- Provider credentials được bảo vệ.
- Real-provider tests có thể chạy riêng và không bắt buộc trong CI.

**Dependencies:** LLM-03.1–03.6.

**Complexity:** M.

---

## 6. Milestone Dependencies

```text
LLM-03.1 — Provider Selection
           |
           v
LLM-03.2 — Provider Adapter
           |
           +---------------------+
           |                     |
           v                     v
LLM-03.3 — Prompts       Fake Provider Setup
           |                     |
           +----------+----------+
                      |
                      v
LLM-03.4 — ExtractionService
                      |
                      v
LLM-03.5 — Validation & Evidence
                      |
                      v
LLM-03.6 — Offline Integration Tests
                      |
                      v
LLM-03.7 — Real Provider Evaluation
```

Một số công việc có thể chạy song song:

- Versioned prompts và fake provider fixtures.
- Adapter unit tests và prompt rendering tests.
- Chuẩn bị synthetic dataset và xây dựng extraction service.
- LLM-04 TemporalResolver có thể phát triển độc lập sau khi temporal interfaces được thống nhất.

Không yêu cầu Audio Processing Service hoặc Web Backend hoàn tất mới bắt đầu LLM-03.

---

## 7. Proposed File Changes

Các thành phần dự kiến ảnh hưởng:

```text
apps/llm-service/
├── app/
│   ├── providers/
│   │   ├── protocol.py
│   │   ├── openrouter.py
│   │   └── fake.py
│   ├── prompts/
│   │   └── v1/
│   │       ├── system.txt
│   │       └── summary_actions.txt
│   ├── services/
│   │   └── extraction.py
│   ├── api/
│   │   └── dependencies.py
│   ├── core/
│   │   └── config.py
│   └── schemas/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── pyproject.toml
└── uv.lock
```

Đây là cấu trúc đề xuất, không phải yêu cầu tạo toàn bộ file trước khi cần.

Ưu tiên tái sử dụng schemas và runtime từ LLM-01/02. Không tạo provider framework phức tạp hoặc các adapter chưa sử dụng.

---

## 8. Acceptance Criteria — LLM-03 Overall

LLM-03 chỉ được xem là hoàn thành khi:

- [ ] Có một LLM provider adapter thật hoạt động.
- [ ] Có fake provider để chạy offline tests.
- [ ] Provider/model được cấu hình qua environment.
- [ ] Không hardcode hoặc log API credentials.
- [ ] Có versioned extraction prompts.
- [ ] Hỗ trợ `meeting_summary` và `action_items`.
- [ ] Có real extraction response đúng Contract v1.
- [ ] Không fabricate metadata, owner, date hoặc priority.
- [ ] Source IDs hợp lệ và source timestamps được dẫn xuất từ transcript.
- [ ] Review flags phản ánh uncertainty.
- [ ] Structured output errors được phát hiện.
- [ ] Provider errors được ánh xạ đúng ErrorEnvelope.
- [ ] Unsupported modules không được trả success giả.
- [ ] Không trả success khi evidence checks bắt buộc chưa đạt.
- [ ] Offline integration tests pass.
- [ ] LLM-01/02 regression tests pass.
- [ ] Real-provider smoke test hoàn thành.
- [ ] Token usage và chi phí thử nghiệm được ghi nhận.
- [ ] Không yêu cầu database, audio service hoặc backend đang chạy.

---

## 9. Known Risks & Technical Debt

### 9.1. Existing LLM-01 Validation Debt

Các vấn đề đã được ghi nhận:

| ID | Issue | Required Before |
|---|---|---|
| F1 | Owner null chưa bắt buộc review | Real extraction acceptance |
| F2 | Temporal uncertainty chưa truyền đầy đủ lên artifact | Real extraction acceptance |
| F3 | Source timestamp chưa được cross-validated với transcript | Contract-compliant extraction |
| F4 | Numeric overflow có thể gây exception | Production-facing request handling |

Các vấn đề trên cần được khắc phục hoặc kiểm soát bằng invariant checks tương đương trước khi nghiệm thu luồng extraction thật.

Không được coi số lượng passing tests là bằng chứng thay thế cho việc kiểm tra các invariant này.

### 9.2. Provider Output Quality

Structured JSON đúng schema không bảo đảm nội dung đúng transcript.

Cần phân biệt:

- Syntactic validity.
- Schema validity.
- Source reference validity.
- Semantic evidence correctness.

LLM-03 kiểm tra các điều kiện tối thiểu cần thiết để trả response an toàn. LLM-06 mở rộng thành evidence verification tổng quát.

### 9.3. Temporal Ambiguity

LLM-03 không được tự tính các relative dates chưa được hỗ trợ bằng deterministic logic.

Các trường hợp ambiguous cần được giữ nguyên và đánh dấu review.

LLM-04 sẽ xây dựng TemporalResolver hoàn chỉnh.

### 9.4. Unsupported Modules

Contract v1 mô tả sáu modules, trong khi LLM-03 mới triển khai hai modules.

Nhóm cần thống nhất hành vi lỗi cho requested modules chưa được hỗ trợ mà không làm sai contract. Trong giai đoạn triển khai, có thể sử dụng trạng thái capability-unavailable có cấu trúc theo quy tắc đã duyệt.

### 9.5. Provider Cost and Limits

Free-tier model có thể có rate limits, availability thấp hoặc structured output không ổn định.

Không phụ thuộc vào free model để nghiệm thu toàn bộ chất lượng extraction.

### 9.6. Data Privacy

LLM provider có thể tiếp nhận transcript chứa thông tin nhạy cảm.

Không gửi dữ liệu cuộc họp thật trước khi chính sách provider, retention và consent được phê duyệt.

---

## 10. Validation & Evaluation

### 10.1. Automated Validation

Bắt buộc duy trì các nhóm kiểm thử:

- LLM-01 contract tests.
- LLM-02 HTTP runtime tests.
- LLM-03 provider adapter tests.
- LLM-03 extraction service tests.
- LLM-03 offline integration tests.

### 10.2. Manual Evaluation

Đánh giá các tiêu chí sau trên một tập transcript mẫu:

| Metric | Evaluation |
|---|---|
| Schema Compliance | Output parse và validate đúng |
| Summary Faithfulness | Summary phản ánh đúng transcript |
| Action Precision | Tránh tạo Action Item không có commitment |
| Owner Correctness | Không tự gán người phụ trách |
| Deadline Correctness | Không tự tạo ngày chính xác |
| Source Traceability | Mỗi artifact có source IDs hợp lệ |
| Latency | Ghi thời gian xử lý |
| Token Usage | Ghi input/output tokens |
| Cost | Ước tính chi phí cho mỗi request |

Ngưỡng chất lượng chính thức sẽ được xác định trong LLM-09 sau khi có baseline và gold evaluation set.

---

## 11. Definition of Done

LLM-03 đạt Definition of Done khi:

1. Provider thật hoạt động với cấu hình đã duyệt.
2. FastAPI gọi được ExtractionService thật qua dependency injection.
3. Meeting Summary và Action Items được sinh từ transcript.
4. Không có fabricated facts trong các acceptance test cases.
5. Response tuân thủ Contract v1, bao gồm evidence requirements.
6. Các lỗi provider/validation được xử lý có cấu trúc.
7. Test suite offline pass.
8. Real-provider test được thực hiện và ghi nhận.
9. Không có credentials trong code hoặc logs.
10. Implementation được review và merge vào `develop` theo `CONTRIBUTING.md`.

---

## 12. Recommended Execution Order

Thứ tự triển khai đề xuất:

| Order | Milestone | Output |
|---|---|---|
| 1 | LLM-03.1 | Provider/model và cost policy |
| 2 | LLM-03.2 | OpenRouter adapter + fake provider |
| 3 | LLM-03.3 | Versioned prompts |
| 4 | LLM-03.4 | ExtractionService |
| 5 | LLM-03.5 | Output validation + evidence safeguards |
| 6 | LLM-03.6 | Offline tests |
| 7 | LLM-03.7 | Real-provider evaluation |

**Recommended First Step:** LLM-03.1 — Provider Selection & Configuration.

Trước khi bắt đầu LLM-03.2, cần xác nhận model hỗ trợ structured output, chi phí thử nghiệm và chính sách dữ liệu.

---

## 13. Next Tasks After LLM-03

| Task | Description |
|---|---|
| LLM-04 | Deterministic TemporalResolver |
| LLM-05 | Remaining Four Business Modules |
| LLM-06 | Comprehensive EvidenceVerifier |
| LLM-07 | Long Transcript Processing |
| LLM-08 | Reliability, Privacy & Observability |
| LLM-09 | Gold Evaluation & Acceptance |

LLM-03 cung cấp nền tảng provider và extraction để các task tiếp theo mở rộng mà không phải viết lại FastAPI runtime.

---

## 14. References

- [LLM Service Architecture](./llm-service-architecture.md)
- [LLM Service Contract](./llm-service-contract.md)
- [Implementation Roadmap](../implementation-roadmap.md)
- [Feature Overview](../feature-overview.md)
- [Contributing Guidelines](../../CONTRIBUTING.md)

**Document status:** Proposed. Nội dung này là kế hoạch triển khai, không xác nhận các chức năng LLM-03 đã được implement.