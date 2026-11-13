# LLM-03.4 — Summary/Actions Extraction Service

## 1. Tổng quan milestone

LLM-03.4 xây dựng pipeline trích xuất Summary và Action Items từ một `ExtractionRequest` đã được xác thực. Milestone này nối các thành phần provider-neutral đã có với các bước chuẩn bị và điều phối; việc tạo public response chỉ được thực hiện sau các kiểm tra cần thiết.

LLM-03.4 phụ thuộc vào LLM-03.2 (provider protocol, adapter và `ProviderUsage`) và LLM-03.3 (candidate schema, prompt registry, renderer và parser). Đã chọn **Phương án A — Tách biệt Orchestration và Verification**: LLM-03.4 phụ trách orchestration và chuẩn bị dữ liệu; LLM-03.5 xác minh source references, semantic evidence và các điều kiện để tạo response đã xác minh.

Trạng thái hiện tại: **Groups A và B hoàn thành, đã được kiểm chứng**. Toàn bộ milestone LLM-03.4 chưa hoàn thành; Groups C và D vẫn chưa triển khai.

## 2. Kiến trúc và luồng dữ liệu

Luồng mục tiêu:

```text
ExtractionRequest
    → ExtractionPreflight
    → PreparedRequest
    → LLMProvider.generate()                 [Group B — đã triển khai]
    → parse_candidate()                      [Group B — đã triển khai]
    → PreparedExtraction                    [Group B — đã triển khai]
    → validation/evidence safeguards         [LLM-03.5]
    → verified ExtractionResponse            [sau các validation bắt buộc]
```

Trong Group A, `ExtractionPreflight.prepare()` kiểm tra capability, tải prompt đã duyệt bằng `PromptRegistry`, gọi `PromptRenderer` và trả `PreparedRequest`. Group B dùng kết quả này để gọi provider đúng một lần, parse candidate và tạo `PreparedExtraction` chưa xác minh. Không nhóm nào ở trạng thái hiện tại tạo `ExtractionResponse`.

`PreparedRequest` giữ `ExtractionRequest` gốc và `RenderedPrompt`; không sao chép provider request hoặc các phiên bản prompt/schema đã có trong `RenderedPrompt`. `PreparedExtraction` là hợp đồng nội bộ cho candidate đã parse nhưng chưa xác minh. Public `ExtractionService.extract(request) -> ExtractionResponse` và `UnconfiguredExtractionService` được giữ nguyên; runtime tiếp tục fail-closed.

## 3. LLM-03.4.1 — Extraction Pipeline Architecture & Internal Models

### Tệp triển khai

| Tệp | Trách nhiệm |
|---|---|
| `apps/llm-service/app/services/models.py` | Định nghĩa `PreparedRequest` và `PreparedExtraction`. |
| `apps/llm-service/tests/unit/services/test_models.py` | Kiểm tra representation an toàn và hợp đồng model. |

Hai model dùng `dataclass(frozen=True, slots=True)`. `PreparedRequest` chứa `request` và `rendered_prompt`; cả hai field không xuất hiện trong dataclass representation. `PreparedExtraction` chứa `request`, `candidate`, `prompt_version`, `candidate_schema_version`, `model_id`, provider tùy chọn, `ProviderUsage` tùy chọn và timestamp bắt đầu/kết thúc tùy chọn. Request và candidate cũng được ẩn khỏi representation.

`frozen=True` chỉ ngăn gán lại thuộc tính dataclass; nó không làm các Pydantic model lồng bên trong bất biến sâu. `model_id` phải đến từ kết quả provider thực tế khi Group B tạo model; provider identity và thời gian chỉ được điền nếu runtime có dữ liệu thực. Model không có raw provider JSON, verification flag, `evidence_prompt_version`, artifact IDs, source timestamps hoặc review flags.

Request-specific data nằm trong từng model trả về và không được lưu vào state dùng chung của preflight. Kiểm thử tạo hai request độc lập trên cùng một preflight để xác nhận prompt và request không trộn lẫn. LLM-03.5 vẫn phải kiểm tra source IDs và ý nghĩa evidence trước khi dựng public response.

**Unit tests:** 2 tests trong `tests/unit/services/test_models.py`, đã pass.

## 4. LLM-03.4.3 — Request Preflight & Context Preparation

### Tệp triển khai

| Tệp | Trách nhiệm |
|---|---|
| `apps/llm-service/app/services/preflight.py` | Kiểm tra module, chọn prompt cố định, gọi Registry/Renderer và phân loại lỗi. |
| `apps/llm-service/tests/unit/services/test_preflight.py` | Kiểm tra module selection, rendering, lỗi và request isolation. |

`SUPPORTED_MODULES` gồm `meeting_summary` và `action_items`. Từng module đơn lẻ hoặc cả hai đều được chấp nhận theo đúng thứ tự trong request. Nếu request có module ngoài phạm vi, toàn request bị từ chối trước khi Registry hoặc Renderer chạy; không lọc bỏ module không hỗ trợ.

Preflight dùng constant nội bộ `APPROVED_PROMPT_VERSION = "extract-v1.0"`; không có lựa chọn động, fallback hay cấu hình môi trường mới. Registry hiện có chịu trách nhiệm ánh xạ version sang `system.md` và `summary_actions.md`; candidate schema version `candidate-v1` được lấy từ `RenderedPrompt`, không ánh xạ lại trong preflight.

Lỗi được phân loại thành `UnsupportedExtractionCapabilityError` và `PromptPreparationError`. Lỗi Registry/Renderer được chuyển thành thông báo prompt-preparation tổng quát, không làm lộ đường dẫn, nội dung template, transcript hoặc exception details. Không có HTTP `ErrorEnvelope` mapping trong Group A.

Renderer hiện có bảo toàn Unicode tiếng Việt, segment IDs, thứ tự segment và speaker mappings đầu vào; preflight không sửa transcript, dịch nội dung hoặc suy đoán speaker. Nó không thêm Summary vào request chỉ yêu cầu Actions.

HTTP runtime hiện đã áp dụng body byte limit theo cấu hình. Chưa có giới hạn token/context theo model mà preflight có thể dùng một cách đáng tin cậy; vì vậy preflight không đảm bảo transcript vừa context window. Không thêm tokenizer, truncation hay chunking. Đây là giới hạn cần xử lý trong hardening tương lai.

**Unit tests:** 11 tests trong `tests/unit/services/test_preflight.py`, đã pass.

## 5. Kiểm thử và xác minh

Các lệnh chạy từ `apps/llm-service/`; tests dùng fixture tổng hợp và các component nội bộ thật. Không gọi OpenRouter, không đọc API credentials và không dùng transcript thật.

```bash
uv run --locked --extra test pytest -q tests/unit/services/test_preflight.py
```

Kết quả: **11 passed, 0 failed, 0 skipped**.

```bash
uv run --locked --extra test pytest -q tests/unit/services
```

Kết quả: **13 passed, 0 failed, 0 skipped**.

```bash
uv run --locked --extra test pytest -q
```

Kết quả kiểm thử Group A trước Group B: **359 passed, 0 failed, 0 skipped**; đây là mốc lịch sử sau Group A. Baseline trước Group A là **346 passed** ngày 2026-11-13.

Các lệnh kiểm thử Group B, chạy từ `apps/llm-service/`:

```bash
uv run --locked --extra test pytest -q tests/unit/services/test_orchestration.py
```

Kết quả: **19 passed, 0 failed, 0 skipped**.

```bash
uv run --locked --extra test pytest -q tests/integration/test_candidate_orchestration.py
```

Kết quả: **9 passed, 0 failed, 0 skipped**.

```bash
uv run --locked --extra test pytest -q
```

Kết quả regression sau Group B: **387 passed, 0 failed, 0 skipped** (`2.70s`). Không gọi OpenRouter hoặc dùng API credentials. Các lượt chạy cần quyền truy cập cache của `uv` để tạo file tạm; sau khi được cấp quyền chạy, các lệnh đều hoàn tất thành công.

## 6. Bảo mật và độ tin cậy

- Preflight không khởi tạo provider, gọi mạng, đọc API key hoặc chạy inference.
- Transcript không bị cắt, dịch, sắp xếp lại hay biến đổi; dữ liệu được truyền qua Renderer hiện có.
- Lỗi capability và prompt preparation có thông báo tổng quát, không chứa transcript, template, filesystem path hoặc secrets.
- Request-specific state không nằm trên instance preflight; kiểm thử xác nhận hai request độc lập không lẫn dữ liệu.
- Dataclass representation ẩn request, rendered prompt và candidate. Các model Pydantic lồng bên trong không được tuyên bố là bất biến sâu.
- Byte limit HTTP hiện có không thay thế token/context limit theo model. Group A không ước lượng, chunk hoặc truncate transcript.
- Candidate chưa được xác minh không thể tạo public success trong phạm vi Group A; endpoint runtime vẫn dùng placeholder fail-closed.
- Group B không ghi log transcript, prompt hoặc raw provider output; `ProviderResult.content` chỉ được giữ cục bộ đến khi parse xong.
- Factory production tạo `OpenRouterAdapter` mà không gọi mạng hoặc đọc API key; đọc cấu hình bí mật chỉ xảy ra bên trong adapter khi `generate()` được gọi.
- Mỗi lần chạy giữ request, candidate, timestamps và provider result ở biến cục bộ. Kiểm thử hai request chồng lấp xác nhận candidate, model ID và token usage không bị trộn.
- Provider hoặc parser lỗi được truyền nguyên trạng; cancellation không bị nuốt. Không có retry, JSON repair hoặc fallback.
- `PreparedExtraction` vẫn là candidate chưa xác minh; parse thành công không xác nhận source IDs, evidence, owner, deadline hay temporal consistency.

## 7. Trạng thái các nhóm LLM-03.4

### Phân chia nhóm triển khai LLM-03.4

Đã chọn **Phương án A — Tách biệt Orchestration và Verification**. LLM-03.4 chịu trách nhiệm orchestration, preflight, provider invocation và chuẩn bị dữ liệu đầu ra. LLM-03.5 chịu trách nhiệm xác minh source references, semantic evidence, temporal safeguards, review flags và hoàn thiện verified `ExtractionResponse`.

Production endpoint phải **fail closed** khi các bước validation bắt buộc chưa sẵn sàng. Candidate chưa xác minh không được tạo HTTP `200 completed`; không điền giả `evidence_prompt_version` hoặc metadata verification.

#### Group A — LLM-03.4.1 + LLM-03.4.3: Kiến trúc pipeline và chuẩn bị request

- Thiết kế internal models `PreparedRequest` và `PreparedExtraction`.
- Xây dựng `ExtractionPreflight` và kiểm tra các module được hỗ trợ.
- Dùng `PromptRegistry` và `PromptRenderer` với prompt version `extract-v1.0`.
- Viết unit tests cho preflight và internal models.
- Đầu ra là `PreparedRequest` sẵn sàng cho provider invocation; Group A không gọi provider.

#### Group B — LLM-03.4.2 + LLM-03.4.4: Dependency Injection và điều phối trích xuất

- Xây dựng concrete extraction orchestrator và inject `LLMProvider` cùng các dependencies cần thiết.
- Gọi `provider.generate()` với `prepared.rendered_prompt.provider_request`, sau đó parse JSON bằng `parse_candidate()`.
- Tạo `PreparedExtraction` với metadata thực tế từ provider và runtime.
- Tạo composition factory nội bộ dùng `Settings` và `OpenRouterAdapter`; không nối candidate orchestrator vào FastAPI.
- Giữ public endpoint fail-closed và kiểm thử offline với `FakeProvider`, bao gồm request isolation.

#### Group C — LLM-03.4.5 + LLM-03.4.6: Chuẩn bị Meeting Summary và Action Items

- Mapping metadata Summary từ `ExtractionRequest`.
- Mapping nội dung Summary và Actions từ candidate.
- Bảo toàn source IDs, raw deadlines, owner và priority nullable.
- Chuẩn bị dữ liệu để LLM-03.5 xác minh.
- Không tự tạo artifact IDs, source timestamps, resolved dates hoặc review flags.

#### Group D — LLM-03.4.7 + LLM-03.4.8: Validation Gate, kiểm thử tích hợp và hoàn thiện báo cáo

- Hoàn thiện ranh giới fail-closed.
- Bảo đảm candidate chưa được xác minh không thể tạo HTTP `200 completed`.
- Bổ sung service-level và HTTP integration tests.
- Kiểm thử failure propagation và concurrent-request isolation.
- Chạy full offline regression suite.
- Hoàn thiện báo cáo chung LLM-03.4.

| Nhóm | Tasks | Trạng thái |
|---|---|---|
| A | LLM-03.4.1 + LLM-03.4.3 | Hoàn thành |
| B | LLM-03.4.2 + LLM-03.4.4 | Hoàn thành |
| C | LLM-03.4.5 + LLM-03.4.6 | Chưa triển khai |
| D | LLM-03.4.7 + LLM-03.4.8 | Chưa triển khai |

Việc hoàn thành Groups A và B không đồng nghĩa toàn bộ LLM-03.4 hoặc LLM-03.5 đã hoàn thành. Tiêu chí public HTTP success trong tài liệu milestone gốc được điều chỉnh có chủ đích theo Phương án A: không thể bật an toàn trước khi LLM-03.5 cung cấp validation bắt buộc và đường dựng verified response.

## 8. Handoff sang Group B

Group B đã tái sử dụng `ExtractionPreflight.prepare(request) -> PreparedRequest`; provider request nằm tại `prepared.rendered_prompt.provider_request`, còn prompt/schema version nằm trong `prepared.rendered_prompt`. `PreparedExtraction` định nghĩa các field cho request, parsed `SummaryActionsCandidate`, prompt/schema versions, model ID thực tế, provider, `ProviderUsage` và timestamps.

`CandidateExtractionOrchestrator` inject `LLMProvider` và `ExtractionPreflight`, gọi `generate()` một lần, parse kết quả bằng `parse_candidate()` và chỉ tạo `PreparedExtraction` từ metadata thực tế. `FakeProvider` trong `tests/fakes/provider.py` là lựa chọn cho kiểm thử offline; không cần network hoặc credentials.

Composition factory chỉ dựng pipeline nội bộ. FastAPI tiếp tục dùng `UnconfiguredExtractionService`; không có dependency wiring hoặc public success mới. `PreparedExtraction` là điểm bàn giao candidate chưa xác minh, không phải `ExtractionResponse`.

## 9. LLM-03.4.2 — Provider Dependency Injection

### Tệp triển khai

| Tệp | Trách nhiệm |
|---|---|
| `apps/llm-service/app/services/factory.py` | Composition factory `create_candidate_orchestrator(settings, *, provider=None, provider_name=None, preflight=None)`. |
| `apps/llm-service/app/services/orchestration.py` | Constructor injection của provider, preflight và provider identity. |
| `apps/llm-service/tests/integration/test_candidate_orchestration.py` | Kiểm tra factory, cách ly HTTP và pipeline offline. |

`CandidateExtractionOrchestrator` nhận `LLMProvider`, `ExtractionPreflight` và `provider_name` qua constructor. Nó không import hay tạo adapter cụ thể và không lưu request-specific state trên instance.

Factory mặc định tạo `OpenRouterAdapter(settings)` với identity `openrouter`. Việc khởi tạo không gọi mạng, không kiểm tra API key qua request và không truy cập credentials trong orchestrator. Khi inject provider tùy chỉnh, caller phải truyền identity tường minh, không rỗng và đã trim; provider tùy chỉnh không thể tự nhận identity dành riêng `openrouter`, còn `OpenRouterAdapter` phải dùng identity đó. Factory dùng `Settings` hiện có, không thêm biến môi trường hoặc dependency.

Factory không được nối vào `app/main.py`, `app/api/dependencies.py` hoặc route. Kiểm thử xác nhận `/health` hoạt động độc lập và request đã xác thực tới `POST /v1/extractions` vẫn trả HTTP 503 qua `UnconfiguredExtractionService`, không tạo HTTP 200 từ candidate.

## 10. LLM-03.4.4 — Candidate Extraction Orchestration

Luồng được triển khai trong `CandidateExtractionOrchestrator.run(request) -> PreparedExtraction`:

1. Gọi `ExtractionPreflight.prepare()` đúng một lần.
2. Ghi nhận `started_at` theo UTC có timezone, ngay trước provider generation.
3. Gọi `LLMProvider.generate(prepared.rendered_prompt.provider_request)` đúng một lần.
4. Parse `ProviderResult.content` bằng `parse_candidate(content, prepared.request)`.
5. Sau khi parse thành công, ghi nhận `completed_at` theo UTC và dựng `PreparedExtraction`.

`PreparedExtraction` nhận request gốc; candidate đã parse; `prompt_version` và `candidate_schema_version` từ `RenderedPrompt`; `model_id` và `token_usage` từ `ProviderResult`; provider identity từ composition; cùng hai timestamp xử lý. Nếu provider không báo usage, giá trị vẫn là `None`. Timestamp có timezone UTC và bảo đảm `started_at <= completed_at`; `completed_at` chỉ biểu thị parse hoàn tất, không phải evidence verification hoặc hoàn tất public extraction.

Preflight errors (`UnsupportedExtractionCapabilityError`, `PromptPreparationError`), typed provider errors và parser errors (`CandidateFormatError`, `CandidateRequestMismatchError`) được truyền nguyên trạng. Provider không được gọi nếu preflight lỗi. Không có retry, fallback, sửa JSON hoặc kết quả giả. `asyncio.CancelledError` được phép truyền lên caller; không trả kết quả một phần.

`parse_candidate()` chỉ kiểm tra cấu trúc Candidate Schema v1 và sự tương ứng giữa module được yêu cầu với candidate. Candidate thành công vẫn chưa xác minh source ID, evidence, owner, deadline hoặc thời gian. Không tạo raw output bản sao, `evidence_prompt_version`, public response hay verification flags.

**Kiểm thử Group B:** 19 unit tests trong `tests/unit/services/test_orchestration.py` và 9 integration tests trong `tests/integration/test_candidate_orchestration.py`; tất cả pass. Bao gồm summary-only, actions-only, combined modules, action list rỗng, module không hỗ trợ, lỗi provider/parser, cancellation, metadata, factory không credentials/network, FastAPI fail-closed và hai request chạy chồng lấp.

## 11. Handoff sang Group C — Summary & Action Items Projection

Group C nhận `PreparedExtraction` từ `CandidateExtractionOrchestrator.run(request)`. Model này cung cấp `request`, `candidate`, các phiên bản prompt/schema, provider, model ID, token usage tùy chọn và timestamps xử lý. Nội dung để projection nằm trong `candidate.meeting_summary` và `candidate.action_items`; metadata Summary có thể lấy từ `request` theo contract hiện hành.

Group C cần giữ nguyên source IDs, `raw_due_expression`, owner và priority nullable khi chuẩn bị Summary/Action Items cho LLM-03.5. Không tự sinh artifact IDs, source timestamps, resolved dates hoặc review flags. `PreparedExtraction` không mang trạng thái đã xác minh và không được coi là public response.

## 12. Ranh giới với LLM-03.5

Groups A và B **chưa** triển khai:

- Kiểm tra source ID tồn tại trong transcript revision.
- Semantic evidence checking hoặc xác minh claim.
- Dẫn xuất `source_timestamp`.
- Gán artifact IDs.
- Temporal resolution hoặc temporal safeguards cho output.
- Gán review state/flags.
- Full public error mapping.
- Dựng verified `ExtractionResponse`.

Các phần này thuộc LLM-03.5 hoặc milestone sau theo phân công. Không khẳng định đã có production extraction được xác minh từ kết quả Groups A/B, và không điền `evidence_prompt_version` nếu verifier chưa chạy.
