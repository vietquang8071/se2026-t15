# LLM-03.5 — Output Validation, Evidence & Error Mapping

> **Dự án:** SE2026-T15 — Meeting Minutes Assistant  
> **Thành phần:** `apps/llm-service`  
> **Nhánh tham chiếu:** `feature/llm-03-provider-integration`  
> **Tài liệu:** Thiết kế kỹ thuật kiêm báo cáo triển khai LLM-03.5  
> **Ngày khởi tạo bản thiết kế:** 14/11/2026  
> **Trạng thái:** **Đã chốt phương án thiết kế; chưa triển khai LLM-03.5**  
> **Phụ thuộc:** LLM-01, LLM-02, LLM-03.2, LLM-03.3 và LLM-03.4 (Phương án A)

## 1. Mục tiêu và phạm vi

### 1.1. Mục tiêu

LLM-03.5 chuyển kết quả `ProjectedExtraction` **chưa xác minh** của LLM-03.4 thành `ExtractionResponse` theo **API Contract v1**, chỉ khi các điều kiện kiểm tra cấu trúc, nguồn dẫn, bằng chứng ngữ nghĩa, thời gian, trạng thái review và metadata đều đạt.

**Nguyên tắc bắt buộc:** Không công bố một candidate/projection chưa được xác minh như kết quả trích xuất thành công. Nếu không thể tạo kết quả hợp lệ và an toàn, trả `ErrorEnvelope` với HTTP non-2xx; không tạo dữ liệu giả hoặc trả thành công một phần.

### 1.2. Phạm vi thực hiện

- Xác minh `source_segment_ids` với transcript của đúng request/revision.
- Xác minh ngữ nghĩa tối thiểu, thực chất cho **Meeting Summary** và **Action Items**.
- Kiểm soát owner, priority, nullable fields, biểu thức hạn và trạng thái cần review.
- Dẫn xuất timestamp, sắp xếp và gán artifact IDs theo quy tắc deterministic.
- Dựng response theo Contract v1 với metadata có nguồn gốc thực tế.
- Ánh xạ lỗi của provider, parser, verification và response sang `ErrorEnvelope`.
- Nối pipeline đã xác minh vào runtime FastAPI, kèm kiểm thử offline và regression.

### 1.3. Ngoài phạm vi

- Bốn module còn lại: `decision_log`, `open_issues`, `follow_up_items`, `timeline_events`.
- TemporalResolver đầy đủ cho ngày tương đối (LLM-04).
- EvidenceVerifier tổng quát cho cả sáu module (LLM-06).
- Chia cửa sổ và tổng hợp transcript dài; benchmark chất lượng quy mô lớn.
- Nhận audio, diarization, database persistence hoặc tích hợp NestJS Backend.
- Multi-provider routing, retry tự động và structured-output repair trong milestone này.
- Thay đổi API Contract v1 hoặc bổ sung cơ chế bypass verification.

## 2. Trạng thái repository trước khi triển khai

Các nội dung trong bảng này đã được đối chiếu với source trên nhánh tham chiếu. Chúng **không** đại diện cho các thành phần LLM-03.5 đã được triển khai.

| Thành phần hiện hữu | File | Trạng thái thực tế |
|---|---|---|
| FastAPI runtime | `app/main.py`, `app/api/routes.py` | Có `/health`, `/v1/extractions`, auth, timeout, DI; mặc định extraction trả 503 |
| Candidate parsing | `app/parsing/candidates.py` | Kiểm tra JSON/Pydantic và module presence; **chưa** kiểm tra evidence |
| Candidate models | `app/schemas/candidates.py` | `SummaryActionsCandidate`, `MeetingSummaryCandidate`, `ActionItemCandidate` |
| Internal orchestration | `app/services/orchestration.py` | Gọi provider một lần, parse candidate, giữ processing metadata |
| Projection | `app/services/projection.py` | `ProjectedExtraction` với Summary/Actions chưa xác minh |
| Provider adapter | `app/providers/openrouter.py`, `app/providers/protocol.py` | OpenRouter qua abstraction; typed provider errors |
| Public extraction boundary | `app/services/extraction.py` | `ExtractionService` protocol và `UnconfiguredExtractionService` |
| Public schema | `app/schemas/response.py` | `ExtractionResponse`, `ProcessingMetadata`, `validate_response_for_request()` |
| Temporal schema | `app/schemas/temporal.py` | `TemporalResolution`: `exact_date`, `date_range`, `unresolved` |
| Error contract | `app/schemas/errors.py`, `app/core/errors.py` | Bảng mã và một số handler; chưa mapping đủ lỗi LLM-03.5 |

**Ranh giới quan trọng:** `validate_response_for_request()` đã kiểm tra identity, source ID tồn tại/thứ tự và metadata Summary, nhưng **không thay thế semantic evidence verification**. `ExtractionProjector` hiện tính `duration_minutes` bằng `round(duration_seconds / 60, 2)`; với duration dương cực ngắn có thể nhận `0.0` trong khi public schema yêu cầu số dương.

Báo cáo LLM-03.4 Group D ghi nhận **412 tests passed**, là mốc regression lịch sử trong tài liệu; chưa có test nào của LLM-03.5 được thực hiện tại thời điểm viết bản thiết kế.

## 3. Quyết định kỹ thuật đã chốt

| ID | Chủ đề | Quyết định áp dụng cho LLM-03.5 |
|---|---|---|
| D-01 | Chiến lược xác minh | **Hybrid:** deterministic validation + một bước LLM evidence verifier có schema/prompt version riêng |
| D-02 | Provider calls | Thông thường 1 extraction call + 1 verification call/request; không gọi verifier riêng cho từng item |
| D-03 | Trạng thái verdict | Nội bộ dùng `supported`, `uncertain`, `unsupported`; đây **không** phải enum công khai của Contract v1 |
| D-04 | Claim handling | Không phát hành `unsupported`; `uncertain` chỉ được giữ có điều kiện và phải được đánh dấu review; không hợp thức hóa claim bịa đặt bằng review flag |
| D-05 | Source validation | Deterministic; không tự sửa ID, không bịa thêm nguồn; nguồn hợp lệ về ID **chưa đủ** chứng minh ngữ nghĩa |
| D-06 | Owner/priority | Chỉ giữ khi có căn cứ cụ thể; thiếu căn cứ dùng `null`, không suy diễn |
| D-07 | Thời gian | Chỉ parse ngày tuyệt đối đủ rõ; còn lại giữ `raw_due_expression`, `unresolved` và review; chưa resolve relative date |
| D-08 | Response | Timestamp, ID, module states và meeting metadata được dựng deterministic từ dữ liệu đã qua verification |
| D-09 | Verification metadata | `evidence_prompt_version` phải là phiên bản prompt **thật sự được thực thi**; không đặt giả |
| D-10 | Model và usage | Dùng cùng provider/model cho extraction và verification trong MVP; usage chỉ lấy từ kết quả thật |
| D-11 | Repair/retry | **0** lần structured-output repair; không tự retry provider trong LLM Service |
| D-12 | Public success gate | HTTP 200 chỉ qua pipeline được kiểm tra đầy đủ; runtime vẫn fail-closed khi chưa sẵn sàng |
| D-13 | Test | Automated tests offline với fake provider; HTTP integration và regression bắt buộc trước nghiệm thu |
| D-14 | Contract | Giữ nguyên public Contract v1; không tự thêm feature flag cho phép bỏ qua verification |

**Quy tắc cụ thể hóa cho duration rất ngắn (D-15):** Không sửa schema/không tự ép `duration_minutes=0.01`. Nếu request yêu cầu `meeting_summary` và `round(duration_seconds / 60, 2) <= 0`, từ chối sớm với `400 VALIDATION_ERROR` trước khi gọi provider. Quy tắc này là một ràng buộc nghiệp vụ **đề xuất trong bản thiết kế** cần được kiểm thử và đối chiếu với API contract khi triển khai. Request chỉ yêu cầu Actions không bị từ chối vì quy tắc projection của Summary. Nếu việc áp dụng đòi hỏi thay đổi contract, phải đưa ra review riêng.

## 4. Kiến trúc và ranh giới dữ liệu

### 4.1. Pipeline

```text
POST /v1/extractions
    |
    v
FastAPI: auth + request validation + request timeout    [LLM-02: đã có]
    |
    v
ExtractionPreflight + CandidateExtractionOrchestrator   [LLM-03.4: đã có]
    |
    v
PreparedExtraction -> ExtractionProjector
    |
    v
ProjectedExtraction                                 [UNVERIFIED]
    |
    v
[A] SourceValidator -> SourceValidatedExtraction
    |
    v
[B] EvidenceVerifier -> EvidenceVerifiedExtraction
    |           (1 provider verification call, versioned prompt)
    v
[C] TemporalReviewProcessor -> ValidatedExtraction
    |
    v
[D] ResponseBuilder -> ExtractionResponse
    |           (Pydantic + validate_response_for_request)
    v
[E] Concrete ExtractionService + HTTP error mapping
    |
    +-- Verified output ----------------------> HTTP 200 completed
    |
    +-- Bất kỳ gate bắt buộc thất bại --------> ErrorEnvelope non-2xx
```

Các tên `SourceValidatedExtraction`, `EvidenceVerifiedExtraction`, `ValidatedExtraction`, `SourceValidator`, `EvidenceVerifier`, `TemporalReviewProcessor`, `ResponseBuilder` là **đề xuất interface**, chưa tồn tại trong source tại thời điểm viết tài liệu.

### 4.2. Nguyên tắc kiến trúc

1. **Fail-closed:** Không có shortcut từ `ProjectedExtraction` sang public response.
2. **Tách trách nhiệm:** A kiểm tra nguồn; B kiểm chứng ý nghĩa; C áp dụng safeguards; D chỉ dựng output; E chỉ tích hợp và mapping lỗi.
3. **Immutable-by-convention:** Không sửa Pydantic candidate gốc bằng side effect; dữ liệu đã xác minh cần được biểu diễn thành đối tượng khác hoặc bản sao có kiểm soát.
4. **Provider-neutral:** Service/verifier chỉ phụ thuộc `LLMProvider` protocol; không gọi HTTPX/OpenRouter trực tiếp trong business logic.
5. **Request isolation:** Không lưu transcript/candidate/verdict của request vào mutable singleton dùng chung.
6. **Traceability:** Giữ `request_id`, `transcript.revision_id`, source IDs, provider/model và prompt versions qua các bước.
7. **Không làm lộ dữ liệu:** Exception, logs và public errors không chứa transcript, prompt, token hoặc raw provider output.

## 5. Giao diện nội bộ giữa các nhóm

### 5.1. Các hợp đồng dữ liệu đề xuất

| Input → Output | Dữ liệu bắt buộc | Bảo đảm và giới hạn |
|---|---|---|
| `ProjectedExtraction` → `SourceValidatedExtraction` | `ProjectedExtraction` gốc; source index từ transcript; claim IDs và source IDs đã kiểm tra | **Chỉ** bảo đảm IDs tồn tại, duy nhất, đúng revision/đúng request và thứ tự; chưa xác minh ý nghĩa |
| `SourceValidatedExtraction` → `EvidenceVerifiedExtraction` | Verdict trên từng claim; nội dung được phép giữ/loại; prompt/model/usage của verification thực | Có kiểm chứng ngữ nghĩa tối thiểu, nhưng còn cần temporal/review safeguards |
| `EvidenceVerifiedExtraction` → `ValidatedExtraction` | Summary/Actions an toàn; nullable fields; temporal resolution; review reasons; source IDs cuối cùng | Đủ điều kiện để xây dựng Contract v1 hoặc nêu rõ failure |
| `ValidatedExtraction` → `ExtractionResponse` | Meeting metadata, artifact IDs, timestamp, module states, processing metadata | Chỉ tạo response hợp lệ và kiểm tra lại với request |
| `ExtractionResponse` → HTTP | `ExtractionResponse` hoặc typed failure | HTTP 200 khi đạt tất cả gate; lỗi dùng `ErrorEnvelope` |

Không cho `ResponseBuilder` nhận trực tiếp `ProjectedExtraction` hoặc verdict chưa được nhóm C chấp nhận.

### 5.2. Định danh claim

Mỗi claim được cấp định danh deterministic theo vị trí trong candidate, ví dụ:

- `summary.overview`
- `summary.key_topics[0]`
- `actions[0].task`
- `actions[0].owner`
- `actions[0].raw_due_expression`
- `actions[0].priority`
- `actions[0].context`

Verifier phải trả verdict cho **đúng** các claim IDs yêu cầu; thiếu, trùng hoặc phát sinh ID không biết phải bị từ chối. Các claim rỗng/null không cần verdict cho giá trị không tồn tại; riêng yêu cầu `action_items: []` vẫn phải được verifier đánh giá về **việc không tìm thấy cam kết** trong transcript để tránh biến extraction thiếu sót thành thành công rỗng.

Với `overview` có nhiều nhận định, verifier phải xác nhận **tất cả nhận định thực chất** trong đoạn; nếu không thể xác minh một phần thì không xem cả đoạn là `supported`. Trong MVP, không để verifier tự viết lại summary/task hoặc thay thế bằng nguồn mới. Những trường hợp cần tái viết phải fail-closed hoặc được xử lý bằng milestone riêng.

### 5.3. Hợp đồng verdict tối thiểu

Mô hình minh họa để thống nhất giao diện, **không phải API Contract v1**:

```json
{
  "checks": [
    {
      "claim_id": "actions[0].task",
      "status": "supported",
      "reason": "explicit_commitment"
    },
    {
      "claim_id": "actions[0].owner",
      "status": "uncertain",
      "reason": "owner_not_confirmed"
    }
  ]
}
```

- `status` chỉ nhận một trong ba giá trị đã chốt.
- `claim_id` do application kiểm soát, không phải artifact ID do model sinh.
- `reason` là thông tin nội bộ cần giới hạn/chuẩn hóa; **không** đưa lý do tự do của LLM vào `review_reasons` công khai.
- Verdict phải được parse bằng schema strict; không coi lời giải thích tự do là chứng cứ để bypass gate.
- Với provider timeout, output thiếu/truncated hoặc verdict bất hợp lệ, trả lỗi theo policy; không tự cho phép `supported`.
- Có thể tách verdict theo từng thuộc tính để `owner` hoặc `priority` trở về `null` mà không làm mất task đã được xác minh.

## 6. Nhóm A — Source Reference Validation

**Mục tiêu:** Bảo đảm toàn bộ source references trỏ tới transcript segments thuộc đúng request.

**Quy tắc:**

1. Tạo index duy nhất từ `request.transcript.segments`; dùng dữ liệu `revision_id` đã gắn với request đó, không tra transcript khác.
2. Kiểm tra danh sách source không rỗng và không trùng cho Summary overview, từng Key Topic và từng Action Item.
3. Mọi ID phải tồn tại trong index; không tự sinh ID mới, sửa typo hoặc thay thế bằng segment gần nhất.
4. Chuẩn hóa thứ tự ID theo `segment.start` tăng dần; nếu trùng start, dùng thứ tự xuất hiện trong transcript làm khóa phụ ổn định.
5. Không dùng ID hợp lệ để mặc nhiên xác nhận claim; đó là trách nhiệm nhóm B.
6. Khi một claim có ID không tồn tại, claim **không đạt**; chỉ được loại khỏi kết quả nếu module vẫn còn output dùng được và policy B cho phép. Nếu mất toàn bộ output dùng được thì trả `502 UNVERIFIED_EVIDENCE`. Không biến mọi item lỗi thành `[]` giả như không có việc.

**File dự kiến:** `app/services/source_validation.py` (mới), các bài test `tests/unit/services/` và `tests/integration/` tương ứng.

**Tiêu chí nghiệm thu:** Unknown IDs, duplicate IDs, cross-request leakage và thứ tự source sai đều được xử lý deterministic; không phát sinh provider calls ở nhóm A.

## 7. Nhóm B — Semantic Evidence Verification

**Mục tiêu:** Xác minh transcript thực sự hỗ trợ từng nhận định hoặc cam kết được trích xuất.

### 7.1. Chiến lược Hybrid

- **Deterministic:** Source IDs, speaker mapping, metadata, kiểu dữ liệu, nullability, thời gian rõ ràng.
- **LLM verification:** Ngữ nghĩa của Summary/Key Topics và Action Items, phân biệt câu hỏi, đề nghị, dự kiến, phủ định, tranh luận và cam kết đã xác nhận.
- Một verification request có cấu trúc kiểm tra toàn bộ claim của extraction; không tạo một call cho mỗi item.
- Prompt verifier có **phiên bản thực** được lưu trong prompt registry và được trả về như metadata từ application.
- Verifier chỉ nhận những đoạn transcript cần thiết, ngữ cảnh được phép dùng và claim IDs; transcript là **dữ liệu không đáng tin cậy**, không phải instruction.
- Có thể dùng cùng `LLMProvider` abstraction và cùng model/provider như bước extraction trong MVP; không hardcode OpenRouter vào lớp verifier.

### 7.2. Ý nghĩa verdict và chính sách công bố

| Verdict | Ý nghĩa | Hành vi |
|---|---|---|
| `supported` | Tất cả thông tin thực chất của claim được source hỗ trợ rõ | Giữ claim; tiếp tục các guard còn lại |
| `uncertain` | Transcript có căn cứ liên quan, nhưng tình trạng chưa chắc chắn **được thể hiện đúng trong nội dung** | Chỉ giữ khi không biến đề nghị thành cam kết/sự thật; gắn review reason phù hợp |
| `unsupported` | Không có evidence đủ, nguồn không liên quan hoặc nội dung bị phủ định/mâu thuẫn theo cách không thể công bố an toàn | Loại claim hoặc reject module/request; **không** giữ dưới dạng “sự thật cần review” |

**Ràng buộc quan trọng:** `uncertain` không phải lối thoát cho nội dung sai. Một task chưa được nhận làm không trở thành Action Item chỉ vì được đánh dấu `needs_review=true`. Nếu task/overview không thể được giữ mà không thay đổi nội dung thì phải loại hoặc từ chối output, không tự viết lại bằng verifier.

### 7.3. Các claim phải kiểm tra

| Module | Các nội dung phải xác minh |
|---|---|
| Meeting Summary | `overview`: toàn bộ nhận định; từng `key_topics[].topic` + `brief_discussion`; không biến đề nghị thành quyết định |
| Action Items | `task`: deliverable/commitment; `owner`: assignment có căn cứ; `raw_due_expression`: tồn tại nguyên văn/ngữ nghĩa chính xác; `priority`: chỉ khi phát biểu rõ; `context`: không thêm facts |
| Action Items rỗng | Xác nhận không có cam kết phù hợp được bỏ sót trong transcript theo phạm vi kiểm tra tối thiểu |

Owner có tên người tham dự chỉ được dùng khi transcript nêu rõ hoặc có speaker-to-participant mapping hợp lệ cho cam kết ngôi thứ nhất. Không suy luận theo thứ tự người nói, chức danh hoặc người nêu đề xuất.

### 7.4. Xử lý thất bại theo đơn vị dữ liệu

- **Summary overview unsupported:** Không thể dựng `MeetingSummary` hợp lệ; trả `502 UNVERIFIED_EVIDENCE` nếu Summary được yêu cầu.
- **Key Topic unsupported:** Có thể loại topic nếu overview vẫn hợp lệ, với các nguồn được giữ lại chính xác; không tự tạo topic thay thế.
- **Action task unsupported:** Loại Action Item; nếu tất cả items bị loại do lỗi evidence, không trả `[]` giả như một lần extraction hợp lệ không phát hiện việc.
- **Owner/priority/context unsupported:** Nếu task còn đủ bằng chứng, có thể đưa riêng field thiếu căn cứ về `null` và gắn review reason phù hợp. Không tự thay bằng giá trị khác.
- **Deadline source unsupported:** Không công bố ngày hoặc biểu thức hạn không có căn cứ; nếu policy xử lý được bằng `null` thì phải giữ review state phù hợp, nếu không thể đảm bảo an toàn thì loại item hoặc trả lỗi.
- **Verifier trả kết quả thiếu claim, trùng claim, schema lỗi hoặc provider timeout:** Không phát hành response thành công.
- **Bất kỳ module được yêu cầu nào không còn kết quả dùng được:** Toàn request trả non-2xx; không có HTTP 200 partial success.

Khi cần lọc bỏ item, nguồn và thứ tự của item còn lại phải được bảo toàn và đánh ID lại sau validation. Một kết quả `action_items: []` chỉ hợp lệ khi đó là kết quả rỗng được xác nhận, **không phải** do toàn bộ candidate items không vượt qua verification.

### 7.5. Metadata và giới hạn

- Ghi nhận `evidence_prompt_version` từ prompt bundle thực được sử dụng; không lấy từ chuỗi do LLM tự khai.
- Theo policy MVP, extraction và verification phải dùng cùng provider/model ID; nếu không thể ghi một `processing.model_id` trung thực theo Contract v1, từ chối kết quả thay vì chọn bừa một ID.
- Không tự retry provider hoặc repair malformed structured output.
- Một verifier LLM có thể sai: cần test với dữ liệu tiếng Việt gồm phủ định, câu hỏi, điều kiện, nhiều speaker và prompt injection. Không tuyên bố bảo đảm ngữ nghĩa tuyệt đối.

**File dự kiến:** `app/services/evidence.py`, schema verdict nội bộ tại `app/schemas/` hoặc `app/services/`, prompt versioned trong `app/prompts/`, test unit/integration bằng Fake Provider.

## 8. Nhóm C — Temporal & Review Safeguards

### 8.1. Thời gian

**Chỉ xác nhận deterministic một ngày tuyệt đối có đủ năm, tháng, ngày và định dạng không mơ hồ.** Mặc định nhận ISO `YYYY-MM-DD`; các định dạng khác không được tự đoán. Nếu sau này hỗ trợ `DD/MM/YYYY`, cần ghi quy tắc parse rõ ràng trước khi triển khai.

| Tình huống | `raw_due_expression` | `due_date_resolution` | `due_date` |
|---|---|---|---|
| Không có hạn | `null` | `null` | `null` |
| Ngày tuyệt đối rõ ràng, hợp lệ và có evidence | Giữ nguyên văn | `exact_date`, `needs_review=false` | Ngày ISO đã kiểm tra |
| `thứ Sáu tới`, `tuần sau`, `cuối tháng` | Giữ nguyên văn | `unresolved`, `needs_review=true` | `null` |
| Khoảng ngày hoặc biểu thức còn mơ hồ | Giữ nguyên văn | `unresolved`, `needs_review=true` trong phạm vi 03.5 | `null` |
| Ngày không hợp lệ / không có evidence | Không công bố như hạn hợp lệ | Xử lý lỗi hoặc giữ thông tin unresolved có review nếu an toàn | `null` |

- `raw_due_expression` phải phản ánh biểu thức xuất hiện trong transcript, không phải ngày model tự tính.
- `TemporalResolution.source_segment_ids` phải là tập con của source IDs thuộc Action Item và có căn cứ liên quan đến thời hạn.
- `date_range` đã có trong schema nhưng **không triển khai resolution khoảng ngày đầy đủ** trong LLM-03.5.
- Không áp dụng quy tắc giải ngày tương đối của LLM-04 sớm hơn phạm vi đã chốt.

### 8.2. Owner, priority và context

- Chỉ giữ `owner` khi có evidence về trách nhiệm; chưa xác nhận thì `null`.
- Người nói ngôi thứ nhất chỉ được ánh xạ danh tính từ mapping request hoặc nêu tên rõ ràng trong transcript.
- `priority` chỉ là `High/Medium/Low` khi có phát biểu đủ rõ; không suy ra từ mức độ khẩn cấp cảm tính hoặc deadline.
- `context` không được thêm phạm vi công việc hay trạng thái hoàn thành ngoài transcript.

### 8.3. Review reasons

Sử dụng **enum hiện có** trong `app/schemas/response.py`, không tạo chuỗi tự do:

| Tình huống | Reason |
|---|---|
| Thiếu xác nhận owner | `owner_unconfirmed` |
| Speaker không có mapping đáng tin cậy và ảnh hưởng owner | `speaker_unmapped` |
| Biểu thức thời gian không thể resolve | `temporal_unresolved` |
| Khoảng ngày cần xác nhận (nếu có xử lý được phê duyệt sau) | `date_range_needs_confirmation` |
| Claim liên quan nhưng chưa xác minh hoàn toàn và vẫn an toàn để review | `evidence_unverified` |
| Các phát biểu xung đột nhưng có thể trình bày sự bất định đúng cách | `conflicting_statements` |
| Bất định còn lại của claim | `claim_uncertain` |

Các invariants:

1. `needs_review == bool(review_reasons)`.
2. `review_reasons` không trùng; sắp xếp theo thứ tự cố định do ứng dụng quản lý để kết quả deterministic.
3. Không tự đặt `needs_review=false` chỉ để vượt qua schema.
4. Nếu thuộc tính thiếu căn cứ được chuyển thành `null`, review reasons phải phản ánh đúng tình trạng khi contract yêu cầu.
5. **Review flag không thay thế được bằng chứng** cho nội dung được công bố như sự thật.

**File dự kiến:** `app/services/temporal_safeguards.py` hoặc `app/services/review.py`, test unit/integration; tái sử dụng `app/schemas/temporal.py` và `app/schemas/response.py` thay vì tạo public schema mới.

## 9. Nhóm D — Verified Response Construction

**Đầu vào bắt buộc:** `ValidatedExtraction` đã qua A, B và C. Không nhận candidate/projection chưa xác minh.

### 9.1. Quy tắc dựng response

- Echo đúng `contract_version`, `request_id`, `meeting_id`, `transcript_revision_id` và thứ tự `requested_modules` từ request.
- Public `modules` luôn có đủ sáu key; các module không được yêu cầu là `null`.
- `meeting_summary` yêu cầu thì không được `null`. `action_items` yêu cầu có thể là `[]` nếu verifier xác nhận không có task phù hợp.
- `title`, `date`, `participants` của Summary lấy từ request, không lấy từ model.
- `duration_minutes` tính theo contract hiện có và áp dụng guard duration của mục 3 trước khi provider call.
- `source_segment_ids` đã được kiểm tra và sắp theo thời gian bắt đầu nguồn.
- `source_timestamp` của từng Action Item bằng `start` nhỏ nhất trong source IDs được xác minh, định dạng `HH:MM:SS.mmm`; không dùng timestamp do model sinh.
- Sắp Action Items theo source time tăng dần; nếu trùng thời điểm, dùng thứ tự candidate ổn định. Gán `ACT-001`, `ACT-002`, ... **sau** khi lọc và sắp xếp.
- Public `review_reasons` và `needs_review` lấy từ kết quả safeguard thực, không hardcode.
- Cuối cùng gọi Pydantic `ExtractionResponse` và `validate_response_for_request()`.

### 9.2. Processing metadata

- `provider` và `model_id` dựa trên các provider results thật. Ở MVP, dùng cùng provider/model cho extraction và verification để phù hợp với một cặp fields duy nhất trong Contract v1.
- `prompt_version` lấy từ extraction prompt đã chạy.
- `evidence_prompt_version` lấy từ verification prompt **đã chạy**, không dùng placeholder.
- `started_at` là thời điểm bắt đầu extraction thực tế; `completed_at` ghi sau khi các bước xác minh và dựng response hoàn tất, ở UTC RFC 3339.
- `token_usage` tổng hợp usage của cả extraction và verification khi **cả hai** cung cấp số liệu hợp lệ; nếu không đầy đủ thì `null`, không ước tính.
- Thời gian thực thi và token usage từ một request không được lẫn với request khác.

**File dự kiến:** `app/services/response_builder.py`, test unit/integration; tái sử dụng `app/schemas/response.py`.

## 10. Nhóm E — HTTP Integration & Error Mapping

### 10.1. Public integration

- Thực hiện concrete `ExtractionService.extract(request) -> ExtractionResponse` đi qua các bước A–D.
- Tích hợp qua composition/DI, không đưa provider logic vào `app/api/routes.py`.
- Giữ Bearer Token, request body limit và request timeout hiện tại.
- Khi verified pipeline chưa sẵn sàng (thiếu cấu hình/verifier), giữ fail-closed; không bật đường thành công bỏ qua verifier.
- `create_app()` hiện cho phép inject service để test. Kết quả 200 từ một test double do caller inject **không** được coi là bằng chứng runtime kiểm chứng ngữ nghĩa; kiểm thử nghiệm thu phải dùng composition production-like với Fake Provider và verifier thật trong pipeline.

### 10.2. Mapping lỗi dự kiến

| Nguồn lỗi | HTTP | `ErrorEnvelope.code` | Retry trong LLM Service |
|---|---:|---|---|
| Request schema/unsupported modules | 400 | `VALIDATION_ERROR` | Không |
| Duration không biểu diễn được cho Summary | 400 | `VALIDATION_ERROR` | Không |
| Provider cấu hình/auth không hợp lệ | 503 | `PROVIDER_CONFIGURATION_ERROR` | Không |
| Rate limit từ provider | 503 | `PROVIDER_RATE_LIMIT` | Không; có thể chuyển retry-after an toàn |
| Timeout của một provider call | 504 | `PROVIDER_TIMEOUT` | Không |
| Lỗi provider khác | 502 | `PROVIDER_FAILURE` | Không |
| Candidate/verifier JSON/schema không hợp lệ | 502 | `INVALID_STRUCTURED_OUTPUT` | Không |
| Source IDs sai, evidence không đủ, không thể xuất bản an toàn | 502 | `UNVERIFIED_EVIDENCE` | Không |
| Toàn request vượt timeout | 504 | `REQUEST_TIMEOUT` | Không |
| Lỗi chuẩn bị prompt/config nội bộ không phân loại thành provider config | 500 | `INTERNAL_ERROR` | Không |
| Bug runtime/response construction ngoài dự kiến | 500 | `INTERNAL_ERROR` | Không |

- Trạng thái `retryable` phải phù hợp với `app/schemas/errors.py`; lỗi validation/evidence/structured output là non-retryable. Provider timeout/rate-limit có thể đánh `retryable=true` để **Backend** quyết định retry sau này, nhưng LLM Service không tự gọi lại.
- Không trả raw provider response, exception traceback, nội dung transcript, prompt hoặc API key trong response/log công khai.
- Giới hạn tổng request hiện có mặc định `180s` và provider timeout `60s`/call; **cả extraction và verification phải nằm trong tổng budget**. Khi có cancel/timeout, không publish kết quả nửa chừng; thu hồi tài nguyên/task theo contract.
- **Không thực hiện structured-output repair**, kể cả khi model sinh JSON sai; mapping thành lỗi đã định.

**File dự kiến:** `app/services/extraction.py`, `app/services/factory.py`, `app/main.py`, `app/core/errors.py`, `app/api/` (chỉ nếu cần), cùng tests tương ứng.

## 11. Kế hoạch thực hiện và phụ thuộc

| Mốc | Nội dung | Phụ thuộc | Đầu ra | Trạng thái |
|---|---|---|---|---|
| 03.5.0 | Chốt tài liệu thiết kế A–E và policy | 03.4 | Tài liệu này | **Đã soạn; chờ review/commit** |
| 03.5.1 | Internal interfaces / typed failures / claim identities | 03.5.0 | Contracts nội bộ + tests | Chưa triển khai |
| 03.5.A | Source reference validation | 03.5.1 | `SourceValidatedExtraction` + unit tests | Chưa triển khai |
| 03.5.B | Evidence verifier + versioned prompt | 03.5.A | Verdicts + verifier tests | Chưa triển khai |
| 03.5.C | Temporal & review safeguards | 03.5.A, interfaces; phối hợp với B | `ValidatedExtraction` + tests | Chưa triển khai |
| 03.5.D | Verified response builder | 03.5.B + C | `ExtractionResponse` + tests | Chưa triển khai |
| 03.5.E | HTTP composition, error mapping | 03.5.D | Verified endpoint + integration tests | Chưa triển khai |
| 03.5.F | Full regression, review và nghiệm thu | A–E | Báo cáo kết quả thực tế | Chưa thực hiện |

Nhóm B và C có thể code song song **sau khi** thống nhất interfaces và đầu ra A. Tests của D/E có thể chuẩn bị với fake verified data nhưng không được nối production public success trước khi B/C hoàn thiện.

### 11.1. Quy tắc phối hợp và Git

- Một thay đổi logic nên có commit riêng, không bắt buộc mỗi tiểu mục là một commit.
- Commit message tuân theo Conventional Commits trong `CONTRIBUTING.md` (bằng tiếng Anh).
- Cập nhật **chính file tài liệu này** khi từng nhóm hoàn thành; không tạo báo cáo milestone mới không cần thiết.
- Mọi thay đổi code/repo thực tế phải được chủ repository phê duyệt trước; **bản thiết kế không tự cấp quyền triển khai**.

## 12. Kế hoạch kiểm thử và tiêu chí nghiệm thu

### 12.1. Ma trận test tối thiểu

| ID | Kịch bản | Kết quả mong đợi |
|---|---|---|
| A-01 | Source ID tồn tại, đúng revision, nhiều segment | Pass và sắp đúng thứ tự thời gian |
| A-02 | Source ID không tồn tại | Claim bị reject; không xuất bản sai nguồn |
| A-03 | Source IDs trùng, tham chiếu chéo request | Bị từ chối / cách ly |
| B-01 | Câu hỏi “Minh có thể làm API không?” bị sinh thành commitment | Không công bố Action Item đã giao |
| B-02 | Cam kết “Tôi sẽ làm...” với speaker mapping hợp lệ | Có thể xác nhận owner |
| B-03 | Cam kết ngôi thứ nhất thiếu speaker mapping | Không suy ra owner; `null` + reason khi thích hợp |
| B-04 | Claim có ID đúng nhưng text không hỗ trợ | Không được trả như claim supported |
| B-05 | Có phủ định/mâu thuẫn/tentative proposal | Phản ánh uncertainty đúng hoặc reject |
| B-06 | Verifier trả sai schema, thiếu/trùng claim ID | HTTP non-2xx, không auto-approve |
| B-07 | Candidate `action_items: []` nhưng transcript có cam kết rõ | Không công bố empty success thiếu kiểm chứng |
| C-01 | ISO absolute date hợp lệ | `exact_date`, không temporal review |
| C-02 | `tuần sau`, `thứ Sáu tới`, ngày không rõ | `unresolved`, `due_date=null`, review |
| C-03 | Không có deadline | Các trường deadline đều `null` |
| C-04 | Priority không được nói rõ | `priority=null` |
| C-05 | `needs_review` không khớp reasons | Pydantic từ chối |
| D-01 | Có 2 Actions với thời gian khác nhau | Sort theo source, IDs `ACT-001`, `ACT-002` |
| D-02 | Source timestamp có giờ/phút/giây/millisecond | Tính từ segment sớm nhất, không từ model |
| D-03 | Request chỉ yêu cầu 1 module | Module không yêu cầu là `null` |
| D-04 | Summary metadata khác request | Không trả response thành công |
| D-05 | Duration dương nhưng làm tròn bằng 0 | 400 trước provider, không sửa contract lén |
| D-06 | Verification không chạy hoặc thiếu version/usage | Không dựng metadata giả |
| E-01 | End-to-end Fake Provider với evidence hợp lệ | HTTP 200, `ExtractionResponse` hợp lệ |
| E-02 | Unknown source / unsupported core claim | HTTP 502 `UNVERIFIED_EVIDENCE` |
| E-03 | Provider rate limit, timeout, malformed response | Mapping đúng status/code/retryable |
| E-04 | Request timeout/cancel trong verification | Không xuất bản partial, cleanup đúng |
| E-05 | Hai request đồng thời | Không trộn IDs, claims, verdicts và usage |
| E-06 | Thiếu token / sai token | Giữ HTTP 401 hiện có |
| E-07 | Public runtime chưa có verified service | Giữ fail-closed HTTP 503 |
| E-08 | Không log/raw error chứa secrets hoặc transcript | Pass privacy checks |

### 12.2. Điều kiện hoàn thành LLM-03.5

- [ ] Test nhóm A–E thành công với provider giả; không dùng OpenRouter thật trong automated tests.
- [ ] Các invalid source IDs, unsupported claims, thiếu evidence hoặc verifier failure không trở thành HTTP 200.
- [ ] Một request Summary/Actions hợp lệ trả HTTP 200 **qua pipeline verification thực**, không phải service mock dựng sẵn response.
- [ ] Metadata, timestamp, artifact IDs, null/empty states và review reasons đúng Contract v1.
- [ ] `evidence_prompt_version` chỉ xuất hiện khi prompt verification đã được sử dụng thực tế.
- [ ] HTTP errors, retry policy và privacy guarantees được chứng minh bằng tests.
- [ ] Các bài test LLM-01 đến LLM-03.4 vẫn pass (full regression).
- [ ] Không có thay đổi không được duyệt ở public Contract v1 hoặc ngoài phạm vi LLM-03.5.
- [ ] File tài liệu này được cập nhật với source paths, kết quả test thật, giới hạn và handoff.

**Lệnh kiểm thử dự kiến**, chạy từ `apps/llm-service/` sau khi triển khai:

```bash
uv run --locked --extra test pytest -q tests/unit
uv run --locked --extra test pytest -q tests/integration
uv run --locked --extra test pytest -q tests/contract
uv run --locked --extra test pytest -q
```

## 13. Nhật ký triển khai (cập nhật khi code)

> **Quy ước:** Mục này cố ý để ở trạng thái chưa triển khai. Khi hoàn thành một nhóm, ghi rõ **file đã sửa**, **thay đổi thực tế**, **test đã chạy/kết quả**, **giới hạn** và **commit/PR**. Không đổi trạng thái chỉ vì có thiết kế.

| Nhóm | Thiết kế | Triển khai | Kiểm chứng | File/commit/ghi chú |
|---|---|---|---|---|
| Interfaces | Đã chốt | Chưa | Chưa | Cập nhật sau |
| A — Source Validation | Đã chốt | Chưa | Chưa | Cập nhật sau |
| B — Evidence Verification | Đã chốt | Chưa | Chưa | Cập nhật sau |
| C — Temporal/Review | Đã chốt | Chưa | Chưa | Cập nhật sau |
| D — Response Builder | Đã chốt | Chưa | Chưa | Cập nhật sau |
| E — HTTP Integration | Đã chốt | Chưa | Chưa | Cập nhật sau |
| F — Regression/Handoff | Đã lập kế hoạch | Chưa | Chưa | Cập nhật sau |

### 13.1. Ghi nhận theo nhóm

**Interfaces:** Chưa triển khai.  
**A — Source Validation:** Chưa triển khai.  
**B — Evidence Verification:** Chưa triển khai.  
**C — Temporal & Review:** Chưa triển khai.  
**D — Response Construction:** Chưa triển khai.  
**E — HTTP Integration:** Chưa triển khai.  
**F — Full regression:** Chưa thực hiện.

### 13.2. Các quyết định phát sinh trong triển khai

Nếu phát hiện ràng buộc source/schema khiến một quyết định trên không khả thi, ghi **vấn đề, các phương án, ảnh hưởng và quyết định được phê duyệt** tại đây trước khi thay đổi quy tắc. Không tự sửa silent policy hoặc khai báo milestone hoàn thành khi acceptance chưa đạt.

### 13.3. Kết quả regression cuối cùng

- **Baseline tham khảo:** 412 passed theo báo cáo LLM-03.4 Group D.
- **Kết quả sau LLM-03.5:** Chưa thực hiện.
- **Các test bổ sung:** Chưa có.
- **Số liệu provider thật / chi phí:** Không thuộc offline acceptance; chỉ ghi khi đã được cấp phép kiểm thử và có kết quả thật.

## 14. Giới hạn, rủi ro và handoff

1. **LLM verifier không tuyệt đối chính xác:** Cần kiểm chứng thêm trên dữ liệu có quyền sử dụng trước khi khẳng định chất lượng production.
2. **Trường `ProcessingMetadata` chỉ có một `provider/model_id`:** MVP giới hạn extraction/verification cùng provider/model. Nếu sau này tách model, phải có thiết kế metadata rõ thay vì ghi sai sự thật.
3. **Transcript dài:** Request byte limit không tương đương token/context limit; chunking và aggregation không nằm trong LLM-03.5.
4. **Temporal parsing giới hạn:** Relative dates, date ranges và timezone semantics phức tạp chuyển sang LLM-04; LLM-03.5 không tự suy diễn.
5. **Evidence verification tổng quát:** Mở rộng sang sáu module thuộc LLM-06 và các milestone liên quan.
6. **Backend integration:** LLM Service vẫn là component độc lập; kết nối NestJS/Web là công việc khác.
7. **Duration dương cực ngắn:** Quy tắc reject sớm phải được test, ghi nhận giới hạn và rà soát tương thích với contract khi triển khai.

## 15. Tài liệu tham chiếu

- [Tổng quan LLM-03](./llm-03-overview.md)
- [Báo cáo LLM-03.4 và handoff](./llm-03.4-extraction-service-report.md)
- [API Contract v1](../../llm-service-contract.md)
- [Kiến trúc LLM Service](../../llm-service-architecture.md)
- [Implementation Roadmap](../../../implementation-roadmap.md)
- [Contributing](../../../../CONTRIBUTING.md)

---

**Kết luận thiết kế:** LLM-03.5 chỉ hoàn thành khi dữ liệu đã qua source validation, semantic evidence verification, temporal/review safeguards và response construction mới được publish. Mọi đường lỗi phải fail-closed theo Contract v1. Tài liệu này sẽ được cập nhật bằng bằng chứng triển khai và kiểm thử thực tế sau khi các thay đổi được phê duyệt.
