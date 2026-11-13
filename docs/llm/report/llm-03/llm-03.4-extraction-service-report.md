# LLM-03.4 — Summary/Actions Extraction Service

## 1. Tổng quan milestone

LLM-03.4 xây dựng pipeline trích xuất Summary và Action Items từ một `ExtractionRequest` đã được xác thực. Milestone này nối các thành phần provider-neutral đã có với các bước chuẩn bị và điều phối; việc tạo public response chỉ được thực hiện sau các kiểm tra cần thiết.

LLM-03.4 phụ thuộc vào LLM-03.2 (provider protocol, adapter và `ProviderUsage`) và LLM-03.3 (candidate schema, prompt registry, renderer và parser). Đã chọn **Phương án A — Tách biệt Orchestration và Verification**: LLM-03.4 phụ trách orchestration và chuẩn bị dữ liệu; LLM-03.5 xác minh source references, semantic evidence và các điều kiện để tạo response đã xác minh.

Trạng thái hiện tại: **Groups A, B, C và D hoàn thành trong phạm vi pipeline nội bộ đã được duyệt và kiểm chứng**. Các tiêu chí verified public extraction trong acceptance ban đầu được hoãn có chủ đích sang LLM-03.5; vì vậy không tuyên bố mọi tiêu chí public của milestone gốc đã đạt.

## 2. Kiến trúc và luồng dữ liệu

Luồng mục tiêu:

```text
ExtractionRequest
    → ExtractionPreflight
    → PreparedRequest
    → LLMProvider.generate()                 [Group B — đã triển khai]
    → parse_candidate()                      [Group B — đã triển khai]
    → PreparedExtraction                    [Group B — đã triển khai]
    → ExtractionProjector.project()          [Group C — đã triển khai]
    → ProjectedExtraction                    [Group C — đã triển khai]
    → kiểm tra ranh giới, lỗi và cách ly request [Group D — đã kiểm thử]
    → validation/evidence safeguards         [LLM-03.5]
    → verified ExtractionResponse            [sau các validation bắt buộc]
```

Trong Group A, `ExtractionPreflight.prepare()` kiểm tra capability, tải prompt đã duyệt bằng `PromptRegistry`, gọi `PromptRenderer` và trả `PreparedRequest`. Group B dùng kết quả này để gọi provider đúng một lần, parse candidate và tạo `PreparedExtraction` chưa xác minh. Group C chỉ ánh xạ metadata request và candidate sang `ProjectedExtraction`; projection cũng chưa xác minh nội dung. Không nhóm nào ở trạng thái hiện tại tạo `ExtractionResponse`.

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

Các lệnh kiểm thử Group C, chạy từ `apps/llm-service/`:

```bash
uv run --locked --extra test pytest -q tests/unit/services/test_projection.py
```

Kết quả: **15 passed, 0 failed, 0 skipped**.

```bash
uv run --locked --extra test pytest -q tests/integration/test_candidate_projection.py
```

Kết quả: **7 passed, 0 failed, 0 skipped**.

```bash
uv run --locked --extra test pytest -q
```

Kết quả regression sau Group C: **409 passed, 0 failed, 0 skipped** (`2.37s`), tăng từ mốc lịch sử **387 passed** sau Group B. Không gọi OpenRouter hoặc dùng API credentials.

## 6. Bảo mật và độ tin cậy

- Preflight không khởi tạo provider, gọi mạng, đọc API key hoặc chạy inference.
- Transcript không bị cắt, dịch, sắp xếp lại hay biến đổi; dữ liệu được truyền qua Renderer hiện có.
- Lỗi capability và prompt preparation có thông báo tổng quát, không chứa transcript, template, filesystem path hoặc secrets.
- Request-specific state không nằm trên instance preflight; kiểm thử xác nhận hai request độc lập không lẫn dữ liệu.
- Dataclass representation ẩn request, rendered prompt và candidate. Các model Pydantic lồng bên trong không được tuyên bố là bất biến sâu.
- Byte limit HTTP hiện có không thay thế token/context limit theo model. Group A không ước lượng, chunk hoặc truncate transcript.
- Default runtime vẫn fail-closed sau Group D: endpoint mặc định dùng `UnconfiguredExtractionService`, không gọi provider hoặc candidate pipeline. `create_app()` vẫn cho phép inject một `ExtractionService` tùy biến; schema validation của response không chứng minh service đó đã xác minh evidence.
- Group B không ghi log transcript, prompt hoặc raw provider output; `ProviderResult.content` chỉ được giữ cục bộ đến khi parse xong.
- Factory production tạo `OpenRouterAdapter` mà không gọi mạng hoặc đọc API key; đọc cấu hình bí mật chỉ xảy ra bên trong adapter khi `generate()` được gọi.
- Mỗi lần chạy giữ request, candidate, timestamps và provider result ở biến cục bộ. Kiểm thử hai request chồng lấp xác nhận candidate, model ID và token usage không bị trộn.
- Provider hoặc parser lỗi được truyền nguyên trạng; cancellation không bị nuốt. Không có retry, JSON repair hoặc fallback.
- `PreparedExtraction` vẫn là candidate chưa xác minh; parse thành công không xác nhận source IDs, evidence, owner, deadline hay temporal consistency.
- `ExtractionProjector` không gọi provider, mạng hoặc đọc credentials; kiểm thử tích hợp đi qua `FakeProvider` và các component prompt/parser thật.
- Projector không sửa request, transcript hay candidate. Danh sách Action Items được copy nông; các Pydantic candidate bên trong vẫn được tham chiếu và có thể mutable, vì vậy downstream phải xem chúng là dữ liệu chỉ đọc.
- Source IDs không tồn tại vẫn được giữ nguyên để LLM-03.5 xác minh; projection không tuyên bố chúng là evidence hợp lệ.
- Thời lượng dương rất ngắn có thể được làm tròn thành `0.0` phút. Public `MeetingSummary.duration_minutes` hiện yêu cầu giá trị dương; projection không bịa mức tối thiểu và chưa thay đổi schema.

## 7. Trạng thái các nhóm LLM-03.4

### Phân chia nhóm triển khai LLM-03.4

Đã chọn **Phương án A — Tách biệt Orchestration và Verification**. LLM-03.4 chịu trách nhiệm orchestration, preflight, provider invocation và chuẩn bị dữ liệu đầu ra. LLM-03.5 chịu trách nhiệm xác minh source references, semantic evidence, temporal safeguards, review flags và hoàn thiện verified `ExtractionResponse`.

Default production endpoint phải **fail closed** khi các bước validation bắt buộc chưa sẵn sàng; candidate của pipeline nội bộ chưa xác minh không được nối thành HTTP `200 completed`. Không điền giả `evidence_prompt_version` hoặc metadata verification.

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
- Xác nhận default FastAPI runtime không tạo HTTP `200 completed` từ candidate nội bộ chưa xác minh; response sai cấu trúc từ service được inject bị từ chối.
- Bổ sung service-level và HTTP integration tests.
- Kiểm thử failure propagation và concurrent-request isolation.
- Chạy full offline regression suite.
- Hoàn thiện báo cáo chung LLM-03.4.

| Nhóm | Tasks | Trạng thái |
|---|---|---|
| A | LLM-03.4.1 + LLM-03.4.3 | Hoàn thành |
| B | LLM-03.4.2 + LLM-03.4.4 | Hoàn thành |
| C | LLM-03.4.5 + LLM-03.4.6 | Hoàn thành |
| D | LLM-03.4.7 + LLM-03.4.8 | Hoàn thành |

Phạm vi pipeline nội bộ của LLM-03.4 đã hoàn thành theo Phương án A. Đây là điều chỉnh ranh giới acceptance có chủ đích: tiêu chí HTTP success từ tài liệu milestone gốc vẫn được ghi nhận nhưng hoãn sang LLM-03.5, vì không thể bật an toàn trước khi có validation bắt buộc và đường dựng verified response.

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

Groups A, B và C không triển khai; Group D xác nhận các trách nhiệm sau vẫn nằm ngoài phạm vi LLM-03.4:

- Kiểm tra source ID tồn tại trong transcript revision.
- Semantic evidence checking hoặc xác minh claim.
- Dẫn xuất `source_timestamp`.
- Gán artifact IDs.
- Temporal resolution hoặc temporal safeguards cho output.
- Gán review state/flags.
- Full public error mapping.
- Dựng verified `ExtractionResponse`.

Các phần này thuộc LLM-03.5 hoặc milestone sau theo phân công. Không khẳng định đã có production extraction được xác minh từ kết quả Groups A/B/C, và không điền `evidence_prompt_version` nếu verifier chưa chạy.

## 13. LLM-03.4 Group C — Summary & Action Items Projection

Group C triển khai projection nội bộ giữa `PreparedExtraction` và bước xác minh. Projection chỉ chuẩn bị dữ liệu; nó không biến candidate chưa xác minh thành artifacts đáng tin cậy hoặc public response.

### LLM-03.4.5 — Meeting Summary Projection

| Tệp | Trách nhiệm |
|---|---|
| `apps/llm-service/app/services/projection.py` | Định nghĩa `ProjectedMeetingSummary`, `ProjectedExtraction` và `ExtractionProjector`. |
| `apps/llm-service/tests/unit/services/test_projection.py` | Kiểm tra mapping metadata/content, giữ null state, không mutate và tính xác định. |
| `apps/llm-service/tests/integration/test_candidate_projection.py` | Kiểm tra luồng offline từ request qua provider giả, parser và projector; xác nhận FastAPI vẫn fail-closed. |

`ProjectedMeetingSummary` chứa metadata lấy từ `PreparedExtraction.request.meeting`: `title`, `anchor_date` thành `date`, `duration_seconds` thành `duration_minutes`, và danh sách `participants[].display_name` theo thứ tự request. Nội dung được giữ trong tham chiếu `MeetingSummaryCandidate`, nhờ đó `overview`, thứ tự `key_topics` và tất cả source IDs không bị sao chép, viết lại hoặc sắp xếp lại.

Duration dùng đúng quy tắc `round(duration_seconds / 60, 2)`. Với thời lượng dương quá ngắn, kết quả có thể là `0.0`; public `MeetingSummary.duration_minutes` lại yêu cầu số dương. Đây là giới hạn tương thích được ghi nhận cho downstream. Group C không thay giá trị, không đặt mức tối thiểu và không sửa public schema; nếu cần thay contract, phải có quyết định/phê duyệt riêng.

### LLM-03.4.6 — Action Items Projection

`ProjectedExtraction.action_items` giữ `None` khi module không được yêu cầu và giữ list rỗng `[]` khi Actions đã được yêu cầu nhưng không có item. Với list có nội dung, projector tạo shallow copy để giữ thứ tự mà không làm thay đổi list gốc; các `ActionItemCandidate` vẫn được tham chiếu và không bị sửa.

Các trường `task`, `owner`, `raw_due_expression`, `priority`, `context` và `source_segment_ids` được giữ nguyên. Owner/priority nullable vẫn là `None`; biểu thức thời gian tương đối vẫn ở dạng raw; source IDs không tồn tại vẫn được chuyển tiếp mà không bị loại hoặc thay thế. Candidate/topic Pydantic models mutable không được xem là immutable sâu, nên caller downstream cần coi dữ liệu là chỉ đọc.

Không tạo `id`, `source_timestamp`, `due_date`, `due_date_resolution`, `needs_review`, `review_reasons` hay `evidence_prompt_version`. Không có `ExtractionResponse` hoặc public `MeetingSummary`/`ActionItem` nào được tạo.

### Hợp đồng và luồng dữ liệu

`ExtractionProjector.project(extraction: PreparedExtraction) -> ProjectedExtraction` là phép ánh xạ đồng bộ, xác định và không có state theo request. `ProjectedExtraction.prepared_extraction` giữ tham chiếu tới nguồn gốc để LLM-03.5 tiếp tục truy cập request, transcript, candidate và provider metadata mà không nhân bản các metadata đó. `ProjectedMeetingSummary.candidate` tái sử dụng `MeetingSummaryCandidate`; `action_items` giữ collection module theo semantics `None`/list.

Projector dựa trên invariant module đã được `parse_candidate()` kiểm tra. Nó không lặp lại Candidate Schema validation và không sửa dữ liệu nếu đầu vào không nhất quán; hợp đồng đầu vào là `PreparedExtraction` đã được tạo từ luồng Group B thành công.

### Kiểm thử và xác minh Group C

- `uv run --locked --extra test pytest -q tests/unit/services/test_projection.py`: **15 passed, 0 failed, 0 skipped**.
- `uv run --locked --extra test pytest -q tests/integration/test_candidate_projection.py`: **7 passed, 0 failed, 0 skipped**.
- `uv run --locked --extra test pytest -q`: **409 passed, 0 failed, 0 skipped**. Mốc trước Group C là **387 passed** sau Group B.

Integration tests dùng `FakeProvider`, PromptRegistry, PromptRenderer, `CandidateExtractionOrchestrator` và parser thật. Chúng xác nhận Summary-only, Actions-only, combined, empty Actions, metadata và source preservation; kiểm tra `/health` cùng extraction endpoint mặc định fail-closed. Không dùng API key hoặc gọi mạng provider.

### Bảo mật, độ tin cậy và handoff sang Group D/LLM-03.5

Projector không gọi LLM/provider, không log hoặc sinh nội dung mới, không mutate request/transcript/candidate và không gán trạng thái xác minh. Request-derived meeting metadata và candidate-derived claims vẫn phân biệt được; source references chưa được kiểm tra tiếp tục mang provenance tới LLM-03.5.

Group D đã kiểm thử luồng `PreparedExtraction` → `ProjectedExtraction` và xác nhận có thể tiếp tục lấy request, transcript, candidate cùng provider metadata qua `prepared_extraction`. Các nội dung, owners, deadlines và source IDs vẫn chưa được xác minh. LLM-03.5 phải xử lý source ID existence, semantic evidence, temporal safeguards, review states, artifact IDs, source timestamps, error mapping và verified response construction. Vì vậy public `ExtractionResponse` chưa thể được tạo an toàn từ candidate chưa xác minh; endpoint mặc định tiếp tục fail-closed.

## 14. LLM-03.4.7 — Validation Gate & Fail-Closed Boundary

Group D đã rà soát đường đi nội bộ và public API mà không thêm production component. `CandidateExtractionOrchestrator` chỉ trả `PreparedExtraction`; `ExtractionProjector` chỉ trả `ProjectedExtraction`. Không có đường đăng ký hai thành phần này làm public `ExtractionService`, và `app/main.py` mặc định tiếp tục khởi tạo `UnconfiguredExtractionService`.

`GET /health` không phụ thuộc provider. Request trích xuất đã xác thực trong default runtime trả HTTP 503 với `ErrorEnvelope` `PROVIDER_CONFIGURATION_ERROR`; public service contract vẫn là `extract(request) -> ExtractionResponse`. Test Group D xác nhận response sai cấu trúc từ service được inject trả HTTP 502 `INVALID_STRUCTURED_OUTPUT`, không trả HTTP 200.

Ranh giới này có giới hạn rõ ràng: caller có thể inject một `ExtractionService` tùy biến. Nếu service đó chủ động trả một `ExtractionResponse` hợp lệ về schema, route có thể trả HTTP 200. Runtime không xác minh ngữ nghĩa/evidence của mọi implementation được inject, và Pydantic response validation không thay thế semantic verification. Group D không thay đổi DI public hoặc tự nhận có bảo đảm này; production composition mặc định vẫn fail-closed.

Ở pipeline nội bộ, lỗi prompt preparation được kiểm tra qua orchestrator và không gọi provider. Các test A/B hiện có tiếp tục xác nhận typed provider errors, candidate format/schema/module mismatch được truyền nguyên trạng, không retry hoặc sửa JSON. Test cancellation hiện có được bổ sung timeout hữu hạn khi chờ provider bắt đầu và khi chờ task bị hủy; cleanup hủy và thu hồi task nếu đồng bộ hóa lỗi. Group D không bổ sung HTTP mapping cho provider/parser errors; phần này thuộc LLM-03.5.

Không có transcript, prompt, raw provider output, API key hoặc chi tiết exception nhạy cảm mới được ghi log hay đưa vào public error. Không tạo verification metadata, không xác minh source IDs, semantic evidence, owner hoặc deadline.

## 15. LLM-03.4.8 — Integration Tests & Milestone Documentation

### Coverage audit và test bổ sung

| Hành vi | Coverage trước Group D | Kết quả Group D |
|---|---|---|
| Module không hỗ trợ bị chặn trước provider | `test_preflight.py::test_unsupported_modules_are_rejected_before_prompt_components`; `test_orchestration.py::test_unsupported_modules_fail_before_provider_call`; `test_prompt_candidate_flow.py::test_it08_unsupported_module_is_rejected_before_fake_provider_call` | Đã đủ; không tạo test trùng. |
| Lỗi prompt không gọi provider qua orchestrator | Preflight unit tests kiểm tra lỗi template/render; chưa kiểm tra qua orchestrator | Bổ sung `test_prompt_preparation_failure_propagates_without_provider_invocation`. |
| Provider/parser errors, module mismatch và không retry | Orchestration unit tests, `test_prompt_candidate_flow.py::test_it05`–`test_it09`, parser và provider tests | Đã đủ; không nhân đôi. |
| Cancellation và cleanup | `test_orchestration.py::test_cancellation_propagates_without_retry_or_completed_result` | Đã thêm timeout hữu hạn và cleanup cho task blocking. |
| Pipeline thành công A → B → C | `test_candidate_projection.py::test_full_offline_pipeline_projects_requested_module_variants` và các test Group B | Đã đủ cho các biến thể module; không thêm luồng tuần tự trùng lặp. |
| Cách ly request đồng thời qua projection | Group B kiểm tra concurrency đến `PreparedExtraction`; Group C kiểm tra projection tuần tự | Bổ sung `test_concurrent_requests_remain_isolated_through_projection` để bao phủ A → B → C trong hai request chồng lấp. |
| Default HTTP fail-closed, health, auth và request validation | `test_runtime.py`, `test_candidate_orchestration.py::test_it04_fastapi_health_and_extraction_remain_fail_closed`, `test_candidate_projection.py::test_fastapi_remains_fail_closed_without_projection_wiring` | Đã đủ; giữ nguyên test hiện có. |
| Response sai cấu trúc từ service được inject | Có test response hợp lệ và schema contract, nhưng chưa kiểm tra handler response-validation qua HTTP | Bổ sung `test_invalid_injected_extraction_response_maps_to_error_envelope`. |
| Unknown source IDs và thiếu verification fields | Projection unit/integration tests | Đã đủ; source IDs được giữ nguyên và chưa được xem là evidence đã xác minh. |

Test mới nằm trong `apps/llm-service/tests/integration/test_extraction_pipeline_boundary.py`. Fake provider đồng bộ hai request bằng `asyncio.Event`; test xác nhận candidate, source references, request/transcript, model, usage, provider identity và prompt/schema metadata vẫn gắn với đúng request sau projection. Các test dùng fixture tổng hợp và không cần credentials hoặc network.

### Kiểm thử và regression

Các lệnh chạy từ `apps/llm-service/`:

```bash
uv run --locked --extra test pytest -q tests/integration/test_extraction_pipeline_boundary.py
```

Kết quả: **3 passed, 0 failed, 0 skipped**.

```bash
uv run --locked --extra test pytest -q tests/unit/services/test_orchestration.py::test_cancellation_propagates_without_retry_or_completed_result
```

Kết quả: **1 passed, 0 failed, 0 skipped**.

```bash
uv run --locked --extra test pytest -q tests/unit/services
```

Kết quả: **47 passed, 0 failed, 0 skipped**.

```bash
uv run --locked --extra test pytest -q tests/integration
```

Kết quả: **60 passed, 0 failed, 0 skipped**.

```bash
uv run --locked --extra test pytest -q
```

Regression sau Group D: **412 passed, 0 failed, 0 skipped**. Mốc lịch sử trước Group D là **409 passed** sau Group C; ba test integration mới làm tăng tổng số test. Không gọi OpenRouter, không dùng API key và không dùng transcript thật.

Runner ban đầu chặn `uv` tạo file tạm trong cache chỉ đọc nên pytest chưa được khởi chạy; các lần chạy sau được cấp quyền truy cập cache cần thiết và hoàn tất offline. Trong lần chạy ban đầu của test concurrency, test cũng bị timeout do chưa mở sự kiện giải phóng provider sau khi xác nhận hai request đã vào. Test harness đã được sửa để giải phóng event và cleanup task trong `finally`; các lần chạy focused và full regression cuối cùng đều hoàn tất như kết quả trên.

## 16. Kiểm toán acceptance và trạng thái milestone

Đây là đối chiếu giữa acceptance ban đầu và phạm vi được điều chỉnh theo Phương án A. `Đạt` nghĩa là đã triển khai và có bằng chứng kiểm thử; `Hoãn có chủ đích sang LLM-03.5` không được tính là đã đạt public extraction; `Chưa đạt` dành cho yêu cầu còn thiếu trong phạm vi đã duyệt. Audit hiện không phát hiện tiêu chí Group D nào thuộc phạm vi được duyệt ở trạng thái `Chưa đạt`.

| Tiêu chí | Trạng thái | Bằng chứng hoặc giới hạn | Theo dõi |
|---|---|---|---|
| Preflight, prompt version cố định và các module Summary/Actions được hỗ trợ | Đạt | `test_preflight.py`, integration Group A/B/C và regression Group D | — |
| Provider invocation, parse Candidate Schema v1 và metadata thực tế | Đạt | `test_orchestration.py`, `test_candidate_orchestration.py`, `test_prompt_candidate_flow.py` | — |
| Projection giữ metadata request, candidate content, nullable states và source IDs | Đạt | `test_projection.py`, `test_candidate_projection.py` | — |
| Lỗi preflight/provider/parser không tạo kết quả pipeline giả; cancellation truyền lên caller | Đạt | Unit orchestration, flow tests, test prompt failure Group D và test cancellation có timeout | — |
| Isolation giữa request đồng thời đến hết projection | Đạt | `test_concurrent_requests_remain_isolated_through_projection` và test concurrency Group B | — |
| Default API health, auth, validation, 503 fail-closed và response sai cấu trúc không thành 200 | Đạt | `test_runtime.py`, test fail-closed Group B/C và `test_invalid_injected_extraction_response_maps_to_error_envelope` | — |
| Source ID existence, semantic evidence, owner attribution và temporal safeguards | Hoãn có chủ đích sang LLM-03.5 | Candidate/projected data vẫn chưa xác minh; Group D không xây verifier | LLM-03.5 |
| `source_timestamp`, artifact IDs, review flags/reasons và verified `ExtractionResponse` | Hoãn có chủ đích sang LLM-03.5 | Không được dựng giả từ candidate; không có public response builder | LLM-03.5 |
| HTTP mapping đầy đủ cho provider/candidate errors và kích hoạt public extraction an toàn | Hoãn có chủ đích sang LLM-03.5 | Default service vẫn trả 503; response schema validation không xác minh evidence | LLM-03.5 |
| Public HTTP `200 completed` cho kết quả đã xác minh theo tiêu chí milestone gốc | Hoãn có chủ đích sang LLM-03.5 | Đây là điều chỉnh acceptance có chủ đích theo Option A, không phải tiêu chí đã hoàn thành trong LLM-03.4 nội bộ | LLM-03.5 |
| Tương thích duration dương rất ngắn với schema public | Hoãn có chủ đích sang LLM-03.5/contract decision | `round(duration_seconds / 60, 2)` có thể cho `0.0`, trong khi `duration_minutes` công khai yêu cầu dương; Group C không tự đặt giá trị tối thiểu | Giải quyết trước khi dựng public response |
| Các tiêu chí Group D thuộc phạm vi được duyệt đã qua kiểm thử | Đạt | Không phát hiện tiêu chí Group D nào còn thiếu sau kiểm tra; public extraction được phân loại riêng là hoãn có chủ đích | — |

Trạng thái nhóm sau khi kiểm chứng:

| Nhóm | Tasks | Trạng thái |
|---|---|---|
| A | LLM-03.4.1 + LLM-03.4.3 | Hoàn thành |
| B | LLM-03.4.2 + LLM-03.4.4 | Hoàn thành |
| C | LLM-03.4.5 + LLM-03.4.6 | Hoàn thành |
| D | LLM-03.4.7 + LLM-03.4.8 | Hoàn thành |

**Hoàn thành phạm vi pipeline nội bộ của LLM-03.4 theo Phương án A; các tiêu chí verified public extraction được chuyển sang LLM-03.5.** Không tuyên bố toàn bộ acceptance ban đầu của public extraction đã đạt.

## 17. Handoff sang LLM-03.5

LLM-03.5 có thể nhận `ProjectedExtraction`; dùng `meeting_summary` và `action_items` làm nội dung candidate chưa xác minh, đồng thời truy cập nguồn gốc, transcript, request và provider metadata qua `projected.prepared_extraction`. Meeting title/date/duration/participants là dữ liệu từ request; overview, topics, actions và source references là nội dung candidate từ model.

Checklist tiếp theo:

1. Xác minh mọi source segment ID tồn tại trong đúng transcript revision.
2. Kiểm tra semantic evidence cho từng claim; không coi ID hợp lệ là bằng chứng nội dung được hỗ trợ.
3. Kiểm tra owner attribution và thể hiện uncertainty an toàn khi không đủ căn cứ.
4. Xử lý temporal safeguards, deadline mơ hồ và các biểu thức raw chưa resolve; không suy diễn ngày còn thiếu.
5. Dẫn xuất `source_timestamp` từ các segment đã xác minh.
6. Gán artifact IDs sau validation theo thứ tự xác định.
7. Gán `needs_review` và `review_reasons` theo kết quả validation thực tế.
8. Ánh xạ lỗi provider/candidate sang HTTP `ErrorEnvelope` theo contract mà không làm lộ dữ liệu nhạy cảm.
9. Chỉ dựng `ExtractionResponse` từ dữ liệu đã qua các kiểm tra bắt buộc; không điền giả `evidence_prompt_version`.
10. Kích hoạt public extraction service bằng composition đã nối đầy đủ verification path, giữ default fail-closed khi path chưa sẵn sàng.
11. Chứng minh response HTTP thành công tuân thủ contract và chứa đúng state của module được yêu cầu.
12. Kiểm thử rằng candidate hoặc projection chưa xác minh không thể được publish thành HTTP `200 completed`.

Trước khi dựng public Summary, cần quyết định cách xử lý duration dương rất ngắn: quy tắc hiện tại `round(duration_seconds / 60, 2)` có thể tạo `0.0`, nhưng `MeetingSummary.duration_minutes` yêu cầu giá trị dương. Không được âm thầm áp dụng mức tối thiểu hoặc thay đổi contract khi chưa có quyết định riêng.
