# LLM-03.4 — Summary/Actions Extraction Service

## 1. Tổng quan milestone

LLM-03.4 xây dựng pipeline trích xuất Summary và Action Items từ một `ExtractionRequest` đã được xác thực. Milestone này nối các thành phần provider-neutral đã có với các bước chuẩn bị và điều phối; việc tạo public response chỉ được thực hiện sau các kiểm tra cần thiết.

LLM-03.4 phụ thuộc vào LLM-03.2 (provider protocol, adapter và `ProviderUsage`) và LLM-03.3 (candidate schema, prompt registry, renderer và parser). Đã chọn **Phương án A — Tách biệt Orchestration và Verification**: LLM-03.4 phụ trách orchestration và chuẩn bị dữ liệu; LLM-03.5 xác minh source references, semantic evidence và các điều kiện để tạo response đã xác minh.

Trạng thái hiện tại: **Group A hoàn thành và được kiểm chứng**. Toàn bộ milestone LLM-03.4 chưa hoàn thành; Groups B, C và D vẫn chưa triển khai.

## 2. Kiến trúc và luồng dữ liệu

Luồng mục tiêu:

```text
ExtractionRequest
    → ExtractionPreflight
    → PreparedRequest
    → LLMProvider.generate()                 [Group B]
    → parse_candidate()                      [Group B]
    → PreparedExtraction                    [Group B]
    → validation/evidence safeguards         [LLM-03.5]
    → verified ExtractionResponse            [sau các validation bắt buộc]
```

Trong Group A, `ExtractionPreflight.prepare()` kiểm tra capability, tải prompt đã duyệt bằng `PromptRegistry`, gọi `PromptRenderer` và trả `PreparedRequest`. Group A không gọi provider, không parse candidate và không tạo `ExtractionResponse`.

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

## 5. Testing & Validation

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

Kết quả regression mới nhất: **359 passed, 0 failed, 0 skipped** (`2.36s`). Baseline lịch sử trước Group A là **346 passed** ngày 2026-11-13; đây không phải kết quả mới. Lượt chạy đầu trong sandbox bị chặn trước khi pytest khởi chạy vì `uv` không tạo được file tạm trong cache; các lệnh kiểm thử sau đó chạy thành công với quyền truy cập cache.

## 6. Security & Reliability

- Preflight không khởi tạo provider, gọi mạng, đọc API key hoặc chạy inference.
- Transcript không bị cắt, dịch, sắp xếp lại hay biến đổi; dữ liệu được truyền qua Renderer hiện có.
- Lỗi capability và prompt preparation có thông báo tổng quát, không chứa transcript, template, filesystem path hoặc secrets.
- Request-specific state không nằm trên instance preflight; kiểm thử xác nhận hai request độc lập không lẫn dữ liệu.
- Dataclass representation ẩn request, rendered prompt và candidate. Các model Pydantic lồng bên trong không được tuyên bố là bất biến sâu.
- Byte limit HTTP hiện có không thay thế token/context limit theo model. Group A không ước lượng, chunk hoặc truncate transcript.
- Candidate chưa được xác minh không thể tạo public success trong phạm vi Group A; endpoint runtime vẫn dùng placeholder fail-closed.

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
- Gọi `provider.generate()` bằng `PreparedRequest`, sau đó parse JSON bằng `parse_candidate()`.
- Tạo `PreparedExtraction` với metadata thực tế từ provider và runtime.
- Tích hợp dependency injection vào FastAPI nhưng giữ hành vi fail-closed.
- Kiểm thử offline với `FakeProvider`, bao gồm request isolation.

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
| B | LLM-03.4.2 + LLM-03.4.4 | Chưa triển khai |
| C | LLM-03.4.5 + LLM-03.4.6 | Chưa triển khai |
| D | LLM-03.4.7 + LLM-03.4.8 | Chưa triển khai |

Hoàn thành Group A không đồng nghĩa toàn bộ LLM-03.4 hoặc LLM-03.5 đã hoàn thành.

## 8. Handoff sang Group B

Group B nên tái sử dụng `ExtractionPreflight.prepare(request) -> PreparedRequest`; provider request nằm tại `prepared.rendered_prompt.provider_request`, còn prompt/schema version nằm trong `prepared.rendered_prompt`. `PreparedExtraction` đã định nghĩa các field cho request, parsed `SummaryActionsCandidate`, prompt/schema versions, model ID thực tế, provider tùy chọn, `ProviderUsage` và timestamp tùy chọn.

Group B cần inject `LLMProvider` cùng các dependencies, gọi `generate()` với provider request đã chuẩn bị, parse kết quả bằng `parse_candidate()` và chỉ tạo `PreparedExtraction` từ metadata thực tế. `FakeProvider` hiện có trong `tests/fakes/provider.py` là boundary dùng cho kiểm thử offline; không cần network hoặc credentials.

Provider invocation, parser orchestration, FastAPI dependency wiring, metadata capture sau generation và service-level tests chưa được Group A triển khai. FastAPI hiện tiếp tục fail-closed qua `UnconfiguredExtractionService`. Group B không được trả success trước khi validation bắt buộc ở LLM-03.5 sẵn sàng.

## 9. Ranh giới với LLM-03.5

Group A **chưa** triển khai:

- Kiểm tra source ID tồn tại trong transcript revision.
- Semantic evidence checking hoặc xác minh claim.
- Dẫn xuất `source_timestamp`.
- Gán artifact IDs.
- Temporal resolution hoặc temporal safeguards cho output.
- Gán review state/flags.
- Full public error mapping.
- Dựng verified `ExtractionResponse`.

Các phần này thuộc LLM-03.5 hoặc milestone sau theo phân công. Không có production extraction thành công được khẳng định từ kết quả Group A, và không điền `evidence_prompt_version` nếu verifier chưa chạy.
