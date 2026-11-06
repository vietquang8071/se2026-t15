# Task: Implement LLM-01 — Contract Models & Fixtures

Bạn là **Senior Python Backend Engineer, AI Engineer và Software Architect**, đang phát triển dự án **SE2026-T15 — Meeting Minutes Assistant**.

Repository: vietquang8071/se2026-t15

Nhiệm vụ: triển khai LLM-01 — Contract Models & Fixtures theo LLM Service Architecture và API Contract đã được thiết kế.

**Yêu cầu quan trọng:** Trước khi triển khai, bắt buộc chuyển về branch develop, cập nhật từ remote và tạo feature branch mới. Không thực hiện task trực tiếp trên main hoặc develop.

---

## 1. Git Workflow — Bắt buộc thực hiện đầu tiên

### Step 1. Kiểm tra trạng thái repository

Trước khi thực hiện bất kỳ thay đổi nào, chạy các lệnh read-only để xác định:

- Current branch.
- Working tree status.
- Local/remote branches.
- Các thay đổi chưa commit.
- Các file hiện có trong apps/llm-service/.

Nếu working tree có thay đổi chưa commit hoặc untracked files có nguy cơ bị ảnh hưởng, **dừng và báo cáo**, không tự ý discard, reset, clean, stash hoặc overwrite.

### Step 2. Switch to develop

Sau khi xác nhận working tree an toàn:

~~~bash
git switch develop
~~~

Nếu local develop chưa tồn tại nhưng origin/develop tồn tại, có thể tạo local tracking branch.

Cập nhật develop bằng:

~~~bash
git pull --ff-only origin develop
~~~

Nếu có conflict, divergent history hoặc không thể fast-forward, dừng và báo cáo. Không tự rebase hay force reset.

### Step 3. Create feature branch

Tạo branch:

~~~bash
git switch -c feature/llm-contract-models
~~~

Nếu branch đã tồn tại, không xóa hoặc ghi đè. Báo cáo tình trạng và không tự tạo tên branch thay thế.

Nếu task có GitHub Issue được xác định rõ, tuân thủ quy tắc đặt tên branch theo Issue ID trong CONTRIBUTING.md. Không tự bịa Issue ID.

**Mọi thay đổi của task phải nằm trên feature branch.**

Không commit, push, tạo Pull Request hoặc merge nếu chưa được yêu cầu riêng.

---

## 2. Repository Analysis

Trước khi viết code, đọc đầy đủ:

### Primary specifications

- apps/llm-service/docs/llm-service-contract.md
- apps/llm-service/docs/llm-service-architecture.md

Trong Architecture Document, tập trung vào:

- Section 3 — Internal Processing Pipeline.
- Section 9 — Proposed Project Structure.
- Section 10 — Implementation Roadmap.
- LLM-01 — Contract Models & Fixtures.
- Section 12 — Open Questions.

Trong Contract Document, tập trung vào:

- Section 2 — HTTP API.
- Section 3 — Request Schema.
- Section 4 — Response Schema.
- Section 5 — Six Business Modules.
- Section 6 — Temporal Resolution.
- Section 7 — Source Grounding.
- Section 8 — Error Contract.
- Section 9 — Contract Examples.
- Section 10 — Contract Tests.

### Repository conventions

- docs/product-description.md
- docs/feature-overview.md
- docs/implementation-roadmap.md
- CONTRIBUTING.md
- AGENTS.md, nếu có.
- Các Python files/configurations đã tồn tại trong apps/llm-service/, nếu có.

**Source of Truth:**

1. llm-service-contract.md là nguồn chuẩn cho request/response schema và validation semantics.
2. llm-service-architecture.md là nguồn chuẩn cho component boundaries và task scope.
3. Product Description và Feature Overview cung cấp business requirements.
4. CONTRIBUTING.md quy định Git workflow và coding conventions liên quan.

Không suy đoán tên field, kiểu dữ liệu hoặc enum khi contract đã quy định.

Nếu phát hiện mâu thuẫn nghiêm trọng khiến implementation không thể đúng contract, ghi nhận và báo cáo trước khi thực hiện phần bị ảnh hưởng. Không tự sửa tài liệu thiết kế.

---

## 3. Task Definition

**Task ID:** LLM-01
**Title:** Contract Models & Fixtures
**Priority:** P0
**Complexity:** Medium

**Objective:** Chuyển LLM Service Contract v1 thành Python/Pydantic v2 models có thể validate dữ liệu thực tế, đồng thời xây dựng JSON fixtures và automated contract tests.

Task phải hoàn thành độc lập, không phụ thuộc Audio Processing Service, Web Backend hoặc LLM provider.

### Deliverables

- Pydantic request models.
- Pydantic response models.
- Error response models.
- Temporal resolution models.
- Validation invariants.
- Synthetic JSON fixtures.
- Automated contract tests.
- Pydantic JSON Schema snapshots/fixtures, khi có giá trị kiểm thử.

**Không triển khai HTTP runtime, FastAPI routes hoặc LLM processing.**

---

## 4. Implementation Scope

Triển khai trong apps/llm-service/:

~~~text
apps/llm-service/
├── app/
│   ├── schemas/
│   │   ├── request.py
│   │   ├── response.py
│   │   ├── temporal.py
│   │   └── errors.py
│   └── ...
├── tests/
│   ├── contract/
│   └── fixtures/
└── pyproject.toml
~~~

Cấu trúc chỉ mang tính định hướng. Chỉ tạo file thực sự cần. Có thể tạo __init__.py khi cần.

Nếu chưa có Python project configuration, được phép tạo pyproject.toml tối thiểu để khai báo Python 3.12+, Pydantic v2, pytest và cấu hình chạy tests.

Không thêm FastAPI, OpenAI SDK hoặc dependency của task tương lai nếu chưa cần. Nếu quản lý dependency versions, dùng phiên bản tương thích Python 3.12 và bảo đảm test environment có thể tái lập. Không tạo module rỗng chỉ để hoàn thành folder structure.

---

## 5. Request Models

Implement request models đúng Section 3 của contract.

### Request metadata

- contract_version
- request_id

contract_version chỉ chấp nhận "1.0".

### Meeting context

- id
- title
- anchor_date
- timezone
- duration_seconds
- participants

Participant hỗ trợ id, display_name, speaker_ids. Không suy luận participant identity từ speaker labels.

### Transcript

- revision_id
- language
- segments

Mỗi segment có id, start, end, speaker_id, text.

### Extraction configuration

- output_language
- requested_modules

Chỉ chấp nhận module enum:

~~~text
meeting_summary
action_items
decision_log
open_issues
follow_up_items
timeline_events
~~~

### Request Validation Requirements

Sử dụng Pydantic v2: BaseModel, ConfigDict(extra="forbid"), field_validator, model_validator và strict typing phù hợp contract.

Bắt buộc validate:

1. Unknown fields bị từ chối ở mọi nested model.
2. Contract version khác "1.0" bị từ chối.
3. anchor_date là ngày lịch hợp lệ, đúng định dạng YYYY-MM-DD.
4. Không tự động chuyển datetime thành date-only.
5. timezone là IANA timezone hợp lệ.
6. duration_seconds là số hữu hạn lớn hơn 0.
7. segment.start >= 0.
8. segment.end > segment.start.
9. segment.end <= duration_seconds.
10. Segment IDs không trùng.
11. Segments sắp xếp theo start time không giảm dần.
12. Overlapping segments hợp lệ được chấp nhận.
13. speaker_id = null được chấp nhận.
14. Text rỗng/whitespace không phải speech hợp lệ.
15. Participant IDs không trùng.
16. Một speaker không map vào hai participants.
17. requested_modules không rỗng, không trùng, chỉ chứa enum hợp lệ.
18. Không coercion giữa string, number, boolean và null nếu contract không cho phép.

Phân biệt validation error thông thường với EMPTY_TRANSCRIPT theo Error Contract.

LLM-01 implement validation semantics và error models. Chưa viết FastAPI exception handlers ánh xạ HTTP status; phần đó thuộc LLM-02.

---

## 6. Response Models — Six Business Modules

Implement đủ:

1. Meeting Summary.
2. Action Items.
3. Decision Log.
4. Open Issues.
5. Follow-up Items.
6. Timeline Events.

Tuân thủ chính xác field ở Sections 4 và 5 của Contract Document. Không dùng dict[str, Any] chung thay cho typed models.

Ưu tiên Pydantic nested models, Literal/Enum cho controlled values, nullable fields đúng contract, explicit cross-field validators, và reusable models chỉ khi có cùng business meaning.

### Module Semantics

Response root luôn có đủ sáu module keys.

- Module không được yêu cầu → null.
- Module được yêu cầu nhưng không có items → [] nếu là list module.
- Module được yêu cầu thành công → validated artifact.
- Requested module không có kết quả sử dụng được → không được coi là success.

Bảo đảm:

- status = "completed" cho success response.
- request_id, meeting_id, transcript_revision_id được giữ theo contract.
- requested_modules chỉ chứa module hợp lệ.
- processing có đúng metadata theo contract.
- source_segment_ids, source_timestamp, needs_review, review_reasons có schema chính xác.

Không thực hiện extraction, gán artifact IDs thực tế hoặc tính source timestamp. Có thể implement pure validation helpers nhưng không xây dựng ResponseBuilder hoặc EvidenceVerifier hoàn chỉnh.

---

## 7. Temporal Resolution Models

Implement TemporalResolution và invariants tương ứng.

**Exact Date**

~~~text
status = exact_date
resolved_date = valid ISO date
start_date = null
end_date = null
~~~

**Date Range**

~~~text
status = date_range
resolved_date = null
start_date = valid ISO date
end_date = valid ISO date
start_date <= end_date
~~~

**Unresolved**

~~~text
status = unresolved
resolved_date = null
start_date = null
end_date = null
needs_review = true
~~~

Không cho phép trộn sai trạng thái. Áp dụng needs_review, source reference constraints và quy tắc contract.

**Không viết TemporalResolver** xử lý câu như “thứ Sáu này” hoặc “tuần sau”; calendar arithmetic thuộc LLM-04. LLM-01 chỉ validate cấu trúc kết quả temporal.

---

## 8. Error Models

Implement typed error envelope theo Section 8 của API Contract, gồm:

- statusCode
- code
- message
- request_id
- retryable
- retry_after_seconds
- errors

Implement error codes theo tài liệu, tối thiểu:

- VALIDATION_ERROR
- UNSUPPORTED_CONTRACT_VERSION
- AUTHENTICATION_REQUIRED
- PAYLOAD_TOO_LARGE
- TRANSCRIPT_TOO_LONG
- EMPTY_TRANSCRIPT
- PROVIDER_FAILURE
- INVALID_STRUCTURED_OUTPUT
- UNVERIFIED_EVIDENCE
- PROVIDER_RATE_LIMIT
- PROVIDER_TIMEOUT
- INTERNAL_ERROR

Đọc contract để bổ sung đủ mã lỗi còn lại. Bảo đảm code và retry semantics phù hợp tài liệu. Chỉ implement models/validation, chưa xử lý HTTP exceptions hoặc lỗi provider thực tế.

---

## 9. JSON Fixtures

Tạo synthetic JSON fixtures tại apps/llm-service/tests/fixtures/.

Tối thiểu:

| Fixture | Purpose |
|---|---|
| Full valid request | Meeting context + transcript + sáu modules |
| Full valid response | Response đủ sáu modules |
| Summary + Actions request | Chỉ yêu cầu hai modules |
| Summary + Actions response | Bốn module còn lại null |
| Empty results response | Các list modules là [] |
| Exact date response | Temporal exact_date hợp lệ |
| Date range response | Temporal date_range hợp lệ |
| Unresolved temporal response | Temporal unresolved hợp lệ |
| Invalid request fixtures | Missing field, wrong version, invalid segment |
| Valid error response | Error envelope hợp lệ |

Ưu tiên tái sử dụng JSON examples trong Contract Document sau khi kiểm tra tính nhất quán. Dùng dữ liệu giả lập, không dùng transcript riêng tư hoặc API credentials. Mọi fixture phải parse bằng Python standard library và validate đúng bằng Pydantic. Không giả định LLM hoặc Audio Processing Service đã triển khai.

---

## 10. Automated Contract Tests

Dùng pytest tại apps/llm-service/tests/contract/.

### Request validation

Test valid request, invalid contract version, missing required fields, unknown fields, invalid ISO date/timezone, negative timestamp, end trước start, segment vượt duration, duplicate IDs, out-of-order segments, overlap hợp lệ, unknown speaker, duplicate participant IDs, conflicting speaker mapping và invalid requested modules.

### Response validation

Test full six-module response, Summary + Actions, unrequested modules null, requested list module [], requested module null bị từ chối, missing artifact fields, invalid enum, invalid processing metadata và invalid needs_review/review_reasons combinations.

### Temporal validation

Test exact/range/unresolved hợp lệ; range start sau end; exact có range fields; unresolved có resolved date; invalid calendar date; qua tháng/năm và năm nhuận ở mức parsing.

### Error validation

Test valid envelopes, invalid HTTP status type/code/retry metadata và missing required fields.

### Source reference validation

Test source_segment_ids đúng kiểu, không trùng, source fields bắt buộc, temporal source IDs là subset. Nếu có pure cross-document validator, kiểm tra references tồn tại trong transcript request.

Không làm semantic entailment verification hoặc gọi model; phần đó thuộc LLM-06. Dùng parameterized tests để hạn chế trùng lặp.

---

## 11. JSON Schema & OpenAPI Preparation

Dùng Pydantic v2 model_json_schema() và bảo đảm public request/response/error models sinh JSON Schema hợp lệ.

Có thể lưu deterministic schema snapshots tại tests/fixtures/schemas/ khi hữu ích cho regression.

**Không tạo OpenAPI giả hoặc giả định FastAPI routes đã có.** Kiểm tra /openapi.json được thực hiện ở LLM-02. Nếu deliverable nào cần FastAPI thì ghi rõ defer sang LLM-02.

---

## 12. Engineering Standards

- Python 3.12+.
- Pydantic v2.
- Type hints.
- SOLID, DRY, KISS.
- Separation of concerns.
- No unnecessary abstractions.
- Readable validators.
- Clear module boundaries.
- Deterministic tests.

Không duplicate validation khi có thể dùng helper hợp lý. Không dùng Any tràn lan. Không hardcode ngày hiện tại hoặc timezone máy. Không triển khai tính năng ngoài task.

---

## 13. Strict Scope Restrictions

**Chỉ thay đổi phục vụ LLM-01 bên trong apps/llm-service/.**

Allowed:

- Tạo/cập nhật Pydantic schemas.
- Tạo contract tests và JSON fixtures.
- Tạo Python/pytest config tối thiểu.
- Tạo package initialization files cần thiết.

Not allowed:

- Sửa apps/web/, apps/api/, packages/database/.
- Sửa Prisma schema/migrations.
- Sửa Audio Processing Service.
- Sửa tài liệu thiết kế hiện có.
- Tạo FastAPI routes hoặc runtime.
- Tích hợp OpenAI/provider khác.
- Viết prompt templates.
- Triển khai extraction pipeline, TemporalResolver, semantic EvidenceVerifier.
- Tạo Docker infrastructure.
- Commit, push hoặc merge branch.

Nếu task đòi thay đổi ngoài phạm vi, báo cáo và đề xuất thay đổi thay vì thực hiện.

---

## 14. Execution Workflow

### Phase A — Git Preparation

1. Kiểm tra working tree.
2. Switch về develop.
3. Pull bằng fast-forward only.
4. Tạo feature branch.
5. Xác nhận branch hiện tại.

### Phase B — Repository Understanding

1. Đọc hai tài liệu LLM Service.
2. Đọc CONTRIBUTING và yêu cầu liên quan.
3. Liệt kê models/validators.
4. Đối chiếu open questions.
5. Lập implementation plan ngắn trước khi code.

### Phase C — Implementation

1. Request models.
2. Temporal models.
3. Response models.
4. Error models.
5. Synthetic fixtures.
6. Contract tests.
7. Sinh/kiểm tra JSON Schema nếu phù hợp.

### Phase D — Validation

Chạy Python syntax/import checks, pytest contract tests, JSON fixture parsing, Pydantic validation, JSON Schema generation và lint/type checks đã cấu hình nếu có.

Nếu test fail, chỉ sửa lỗi trong scope. Không sửa project khác để làm test LLM Service chạy.

### Phase E — Final Review

Kiểm tra file thay đổi, không sửa ngoài apps/llm-service/, không có secrets/dữ liệu nhạy cảm, không có generated artifact thừa, không có FastAPI/provider integration ngoài scope, và đối chiếu mọi acceptance criteria.

---

## 15. Acceptance Criteria

- [ ] Working branch được tạo từ develop đúng convention.
- [ ] Có Pydantic v2 request models đầy đủ.
- [ ] Có response models cho sáu modules.
- [ ] Có TemporalResolution models/validators.
- [ ] Có structured error models.
- [ ] Nested models từ chối unknown fields bằng extra="forbid".
- [ ] Contract version sai bị từ chối.
- [ ] Date/timezone validation đúng.
- [ ] Segment timestamps và IDs được kiểm tra.
- [ ] Overlapping segments và unknown speaker được hỗ trợ.
- [ ] Null/empty module semantics đúng.
- [ ] Temporal states không mâu thuẫn.
- [ ] JSON fixtures parse và validate.
- [ ] Automated contract tests chạy thành công.
- [ ] Pydantic JSON Schema generation chạy được.
- [ ] Không gọi LLM provider hoặc Audio Processing Service.
- [ ] Không sửa code/config/docs ngoài scope.

Nếu không đạt tiêu chí, báo cáo rõ lý do và trạng thái.

---

## 16. Final Response Format

Báo cáo bằng tiếng Việt theo cấu trúc:

### 1. Git Status

- Branch ban đầu.
- Branch hiện tại.
- Base branch và kết quả cập nhật.
- Xác nhận không commit/push.

### 2. Implementation Summary

- Models triển khai.
- Validation rules quan trọng.
- Fixtures và tests đã tạo.

### 3. Files Changed

Liệt kê file cùng mục đích.

### 4. Test Results

Nêu lệnh, số tests passed/failed/skipped, phần chưa kiểm thử và JSON Schema generation status. Không bịa kết quả.

### 5. Contract Compliance

Đối chiếu implementation với Acceptance Criteria và chỉ rõ phần chưa hoàn thành.

### 6. Open Questions / Risks

Nêu điểm chưa thống nhất ảnh hưởng tích hợp ba service.

### 7. Next Steps

Đề xuất LLM-02 — FastAPI Runtime sau review/chấp thuận.

**Không tự thực hiện LLM-02.**

---

## Final Instruction

Thực hiện LLM-01 — Contract Models & Fixtures trên feature branch mới từ develop.

Ưu tiên:

**Contract correctness → Type safety → Validation → Automated tests → Maintainability.**

Không overengineer. Không triển khai task tiếp theo. Không commit, push hoặc merge.
