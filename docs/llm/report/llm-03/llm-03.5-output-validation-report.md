# LLM-03.5 — Output Validation, Evidence & Error Mapping

> **Dự án:** SE2026-T15 — Meeting Minutes Assistant  
> **Thành phần:** `apps/llm-service`  
> **Nhánh tham chiếu:** `feature/llm-03-provider-integration`  
> **Tài liệu:** Thiết kế kỹ thuật kiêm báo cáo triển khai LLM-03.5  
> **Ngày khởi tạo bản thiết kế:** 14/11/2026  
> **Trạng thái:** **Đã xử lý R1–R3; regression cuối đạt 542 tests offline**
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

**Quy tắc cụ thể hóa cho duration rất ngắn (D-15):** Không sửa schema/không tự ép `duration_minutes=0.01`. Nếu request yêu cầu `meeting_summary` và `round(duration_seconds / 60, 2) <= 0`, từ chối sớm với `400 VALIDATION_ERROR` trước khi gọi provider. Quy tắc đã triển khai trong preflight và được kiểm tra cả ở unit lẫn HTTP integration; request chỉ yêu cầu Actions không bị từ chối vì quy tắc projection của Summary. Contract v1 không thay đổi.

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

Các tên `SourceValidatedExtraction`, `EvidenceVerifiedExtraction`, `ValidatedExtraction`, `SourceValidator`, `EvidenceVerifier`, `TemporalReviewProcessor`, `ResponseBuilder` được đề xuất khi viết thiết kế và hiện đã được triển khai trong `apps/llm-service/app/`.

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
      "status": "supported"
    },
    {
      "claim_id": "actions[0].owner",
      "status": "uncertain"
    }
  ]
}
```

- `status` chỉ nhận một trong ba giá trị đã chốt.
- `claim_id` do application kiểm soát, không phải artifact ID do model sinh.
- Output triển khai chỉ nhận `claim_id` và `status`; không nhận explanation/reason tự do từ verifier.
- Verdict phải được parse bằng schema strict; không coi lời giải thích tự do là chứng cứ để bypass gate.
- Với provider timeout, output thiếu/truncated hoặc verdict bất hợp lệ, trả lỗi theo policy; không tự cho phép `supported`.
- Có thể tách verdict theo từng thuộc tính để `owner` hoặc `priority` trở về `null` mà không làm mất task đã được xác minh.

### 5.4. Interface đã triển khai — LLM-03.5.1

Các model nội bộ được triển khai trong `apps/llm-service/app/services/validation_models.py`:

- `ClaimIdentity` mang `request_id`, `transcript_revision_id`, `claim_id`, nội dung claim và source IDs; nội dung và nguồn bị ẩn khỏi `repr`.
- `SourceSegmentReference` ghi ID, thời điểm bắt đầu và vị trí gốc của segment.
- `SourceValidatedExtraction` gắn projection với claim/source index, kiểm tra request/revision và ID trùng.
- `VerificationStatus` chỉ nhận `supported`, `uncertain`, `unsupported`; `VerificationVerdict` yêu cầu status tường minh.
- `VerificationMetadata` lưu provider, model, prompt version, usage và thời điểm thực tế.
- `EvidenceVerifiedExtraction` kiểm tra trọn vẹn claim set, không nhận claim lạ/trùng/thiếu hoặc verdict thuộc request/revision khác.
- `ValidatedExtraction` chỉ nhận evidence-verified state và kiểm tra số lượng safeguard metadata theo Action Items.
- `ValidationStageFailure` cùng các subtype `SourceValidationFailure`, `EvidenceVerificationFailure`, `TemporalSafeguardFailure`, `ResponseConstructionFailure` mang lỗi đã sanitize, không mang transcript/candidate.

Test `apps/llm-service/tests/unit/services/test_validation_models.py` kiểm tra khởi tạo hợp lệ, status lạ, claim trùng, verdict thiếu/thừa, cách ly request và ẩn dữ liệu trong `repr`. Chạy `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/unit/services/test_validation_models.py` từ `apps/llm-service/`: **7 passed**. Chạy ban đầu không cấu hình cache dừng trước pytest do `/home/vitquay1708/.cache/uv` chỉ đọc; lần chạy nêu trên dùng cache trong `/tmp` và đã thực thi test.

### 5.5. Interface verifier đã triển khai — nhóm B

`EvidenceVerifier.verify(SourceValidatedExtraction) -> EvidenceVerifiedExtraction` chỉ phụ thuộc `LLMProvider`, `PromptRegistry` và `PromptRenderer`; verifier nhận prompt version từ `EvidencePromptBundle` đã thực sự render. `EvidenceVerificationOutput`/`VerificationCheck` là schema private strict; `EvidenceVerifiedExtraction` cưỡng chế cùng `request_id`/revision và một verdict cho mỗi claim. Không có field cho verifier sửa candidate hoặc cấp artifact ID.

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

### 6.1. Triển khai và kiểm chứng nhóm A

`apps/llm-service/app/services/source_validation.py` triển khai `SourceValidator.validate(ProjectedExtraction)`. Validator tạo index theo request/revision hiện tại; sắp source IDs theo `(segment.start, transcript_order)`; cấp claim IDs deterministic cho Summary, từng topic, từng Action Item và `actions.absence`. Nó không có dependency lên `LLMProvider`.

Summary overview thiếu nguồn hợp lệ làm stage thất bại. Topic hoặc Action Item riêng lẻ có source sai bị loại mà không sửa ID; nếu mọi Action Item không rỗng đều bị loại thì stage thất bại thay vì phát sinh `[]` giả. Candidate bản gốc được giữ trong projection; source-validated copy chỉ chứa các item còn dùng được và IDs đã chuẩn hóa.

`apps/llm-service/tests/unit/services/test_source_validation.py` kiểm tra nguồn hợp lệ nhiều segment, source lạ, duplicate, thứ tự thời gian và tie-break, loại topic lỗi an toàn, cùng cách ly hai request dùng chung segment IDs. Chạy `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/unit/services/test_source_validation.py tests/unit/services/test_validation_models.py` từ `apps/llm-service/`: **13 passed** (6 source-validation cases, 7 interface cases). Không gọi provider.

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

### 7.6. Triển khai verifier và kiểm chứng

Verifier triển khai tại `apps/llm-service/app/services/evidence.py` (`EvidenceVerifier`) và phụ thuộc `LLMProvider`. Output strict nằm trong `app/schemas/verification.py` (`EvidenceVerificationOutput`, `VerificationCheck`). Prompt bundle/version được đăng ký trong `app/prompts/registry.py`, render provider-neutral bởi `app/prompts/renderer.py`; bundle ban đầu `evidence-v1.0` nằm tại `app/prompts/v1/evidence_system.md` và `app/prompts/v1/evidence_verification.md`. Sau hardening F7, runtime thực thi bundle `evidence-v1.1` tại `app/prompts/v1_1/evidence_system.md` và `app/prompts/v1_1/evidence_verification.md`; `evidence-v1.0` được giữ nguyên. Verifier dùng một generation, `json_object`, temperature 0; không retry/repair. Model/provider phải khớp kết quả extraction. Metadata ghi usage và thời gian của provider result thật, được response builder ở nhóm D kết hợp.

Kiểm tra status và complete claim-set được thực hiện trước khi trả `EvidenceVerifiedExtraction`; mọi lỗi parse/schema/ID ánh xạ `INVALID_STRUCTURED_OUTPUT`. Prompt chỉ trình bày transcript/claim dưới dạng JSON data và system prompt cấm thực thi instruction nằm trong dữ liệu. `actions.absence` là claim bắt buộc khi extraction trả danh sách rỗng và yêu cầu verifier rà toàn transcript.

`tests/unit/services/test_evidence_verification.py` sử dụng `FakeProvider`, không gọi OpenRouter. Case cover supported output, thiếu/thừa/trùng claim, status lạ, field thừa, JSON sai, question bị gán nhầm thành task nhưng verdict `unsupported` vẫn giữ nguyên, empty-actions assessment, prompt injection text và timeout không retry. Chạy `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/unit/services/test_evidence_verification.py tests/unit/services/test_source_validation.py tests/unit/services/test_validation_models.py` từ `apps/llm-service/`: **24 passed** (11 verifier, 6 source, 7 interface).

**Giới hạn đánh giá:** fake provider chứng minh hợp đồng, ranh giới prompt và xử lý verdict; không chứng minh độ chính xác ngữ nghĩa của model thật. Enforcement chính sách lọc unsupported/uncertain claims nằm ở safeguard nhóm C, sau đó được kiểm thử end-to-end ở nhóm E.

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

### 8.4. Triển khai Temporal & Review Safeguards

`apps/llm-service/app/services/temporal_safeguards.py` cung cấp `TemporalReviewProcessor.process(EvidenceVerifiedExtraction) -> ValidatedExtraction`. `supported` là bắt buộc cho Action task; unsupported/uncertain task bị loại và nếu không còn task dùng được thì trả `UNVERIFIED_EVIDENCE`. Empty Actions chỉ được giữ khi `actions.absence` được xác minh `supported`. Overview unsupported làm thất bại; unsupported topic có thể được loại; uncertainty an toàn được giữ với reason `claim_uncertain`.

Deadline chỉ resolve nếu chuỗi ISO hợp lệ và canonical; ngày tương đối, mơ hồ hoặc invalid giữ raw expression, `due_date=null`, `unresolved`, `temporal_unresolved`. Unsupported deadline bị xóa và đánh `evidence_unverified`. Owner không được suy ra: thiếu/không được xác minh sẽ thành null; nếu không có source speaker mapping thì thêm `speaker_unmapped`. Priority/context thiếu evidence thành null. Review reasons được unique và sắp theo thứ tự enum Contract v1. `TemporalResolution.source_segment_ids` lấy từ claim deadline đã source-validate, là subset nguồn của Action.

Kiểm thử tại `tests/unit/services/test_temporal_safeguards.py` cover ISO, relative, ambiguous/invalid date, không có deadline, unsupported owner/priority/task/overview, speaker unmapped/mapped, verified empty Actions và empty Actions bị mâu thuẫn. Chạy `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/unit/services/test_temporal_safeguards.py tests/unit/services/test_source_validation.py tests/unit/services/test_evidence_verification.py tests/unit/services/test_validation_models.py` từ `apps/llm-service/`: **36 passed** (12 safeguard, 6 source, 11 verifier, 7 interface).

**Giới hạn:** verifier chỉ trả ba status, không phát reason chuyên biệt cho mâu thuẫn; hiện uncertainty được biểu diễn bằng `claim_uncertain`. Cách đánh giá verdict ngữ nghĩa trên model thật chưa được thực hiện.

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

### 9.3. ResponseBuilder đã triển khai

`apps/llm-service/app/services/response_builder.py` cung cấp `ResponseBuilder.build(ValidatedExtraction)`. Hàm từ chối input ngoài type đã safeguarded, echo chính xác identity và module order, tạo đủ sáu module keys, dựng Summary metadata từ request, dùng verified candidate text, và tạo Action Items sau khi sort theo source time với candidate order ổn định. IDs `ACT-nnn` cấp sau lọc/sort; timestamp lấy từ segment sớm nhất và định dạng millisecond. Builder aggregate usage chỉ khi hai lần provider đều có usage, dùng prompt versions từ hai lần chạy thật, tạo UTC interval và chạy `ExtractionResponse` cùng `validate_response_for_request()`.

`apps/llm-service/app/services/preflight.py` bổ sung `SummaryDurationNotRepresentableError`: Summary request bị chặn trước provider nếu `round(duration_seconds / 60, 2) <= 0`; Actions-only không chịu guard này. Public schema/Contract v1 không đổi.

`tests/unit/services/test_response_builder.py` cover Summary-only, Actions-only, combined, verified empty Actions, sorting/IDs/timestamps, request metadata, usage đầy đủ/thiếu, thiếu evidence prompt metadata, dữ liệu meeting/source sai và guard short-duration/provider invocation. Chạy `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/unit/services/test_response_builder.py` từ `apps/llm-service/`: **13 passed**. Chạy chung với tests 03.5.1/A/B/C: **49 passed**.

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

### 10.3. HTTP pipeline đã triển khai

`apps/llm-service/app/services/verified_extraction.py` triển khai `VerifiedExtractionService.extract()` theo thứ tự preflight/extraction, projection, source validation, verifier, temporal/review và `ResponseBuilder`. `services/factory.py` dùng cùng một provider identity/model và `ProviderTimeoutBound` cho cả hai lần gọi; `main.py` composition mặc định đi qua pipeline này, nên thiếu `OPENROUTER_API_KEY` trả lỗi cấu hình thay vì fallback unverified. `core/errors.py` ánh xạ lỗi typed sang `ErrorEnvelope` đã có; provider retry-after chỉ được chuyển tiếp nếu hữu hạn, dương và không vượt một ngày. Unexpected exception trả thông báo nội bộ đã sanitize. `/health` không phụ thuộc provider.

`apps/llm-service/app/api/dependencies.py` chuyển app-state getters sang `async def`. Trong HTTP integration, synchronous FastAPI dependencies bị treo trong AnyIO worker thread trước khi endpoint chạy; sau chuyển đổi, pipeline chạy bình thường. Tests mới dùng `httpx.ASGITransport` vì `fastapi.testclient.TestClient` treo khi khởi tạo trong môi trường này ngay cả với app tối thiểu. Bearer auth và middleware giới hạn body được giữ nguyên.

Test `apps/llm-service/tests/integration/test_verified_extraction_service.py` chạy qua FastAPI, composition production-like và fake provider, verifier thật; không dùng OpenRouter. Chạy `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/integration/test_verified_extraction_service.py` từ `apps/llm-service/`: **32 passed**. Cover ba tổ hợp Summary/Actions success, empty Actions có/không có evidence, source sai, claim trung tâm unsupported, question/conditional/rejected task, source đúng nhưng text không liên quan, owner đúng/sai và mapping speaker có/không, unsupported priority/deadline, lỗi schema extraction/verifier, provider config/rate limit/provider timeout/failure, request timeout/cancellation, Summary duration làm tròn về 0, auth thiếu/sai, health và fail-closed mặc định, isolation concurrency, cùng sanitize exception.

**Giới hạn checkpoint:** full unit/integration/contract regression được ghi nhận tại 13.3. Starlette `TestClient` treo khi khởi tạo trong môi trường này; test integration dùng `httpx.ASGITransport` cùng ASGI lifespan và đã kiểm tra cancellation đến provider call. Không có live provider calls.

## 11. Kế hoạch thực hiện và phụ thuộc

| Mốc | Nội dung | Phụ thuộc | Đầu ra | Trạng thái |
|---|---|---|---|---|
| 03.5.0 | Chốt tài liệu thiết kế A–E và policy | 03.4 | Tài liệu này | **Đã chốt; nội dung thiết kế được giữ và cập nhật bằng kết quả triển khai** |
| 03.5.1 | Internal interfaces / typed failures / claim identities | 03.5.0 | Contracts nội bộ + tests | **Hoàn tất; unit tests 7/7 passed** |
| 03.5.A | Source reference validation | 03.5.1 | `SourceValidatedExtraction` + unit tests | **Hoàn tất; 6 source cases và 7 interface cases passed** |
| 03.5.B | Evidence verifier + versioned prompt | 03.5.A | Verdicts + verifier tests | **Hoàn tất; hardening cập nhật bundle thực thi lên `evidence-v1.1`** |
| 03.5.C | Temporal & review safeguards | 03.5.A, interfaces; phối hợp với B | `ValidatedExtraction` + tests | **Hoàn tất; 12 safeguard cases, 36 combined tests passed** |
| 03.5.D | Verified response builder | 03.5.B + C | `ExtractionResponse` + tests | **Hoàn tất; 13 builder cases, 49 combined tests passed** |
| 03.5.E | HTTP composition, error mapping | 03.5.D | Verified endpoint + integration tests | **Hoàn tất; 32 HTTP integration tests passed** |
| 03.5.F | Full regression, review và nghiệm thu | A–E | Báo cáo kết quả thực tế | **Hardening hoàn tất; 319 unit + 94 integration + 111 contract = 524 passed** |

Nhóm B và C có thể code song song **sau khi** thống nhất interfaces và đầu ra A. Tests của D/E có thể chuẩn bị với fake verified data nhưng không được nối production public success trước khi B/C hoàn thiện.

### 11.1. Quy tắc phối hợp và Git

- Một thay đổi logic nên có commit riêng, không bắt buộc mỗi tiểu mục là một commit.
- Commit message tuân theo Conventional Commits trong `CONTRIBUTING.md` (bằng tiếng Anh).
- Cập nhật **chính file tài liệu này** khi từng nhóm hoàn thành; không tạo báo cáo milestone mới không cần thiết.
- Phần triển khai này được người dùng ủy quyền trực tiếp; không tạo branch, commit, push, merge hoặc PR.

### 11.2. Trạng thái hậu kiểm và hardening

| Finding | Trạng thái | Kiểm chứng hiện tại |
|---|---|---|
| F9 — Cô lập provider/network trong test | **Đã xử lý; nghiệm thu pass** | 101 focused tests pass; final full regression 524 passed |
| F6/F8 — Test empty Actions và duration | **Đã xử lý; nghiệm thu pass** | 4 focused tests pass; final full regression 524 passed |
| F7 — Grounding theo cited sources | **Đã xử lý; nghiệm thu pass** | 60 focused tests pass; fake verdict không chứng minh semantic accuracy model thật; final 524 passed |
| F2 — Attribution owner theo speaker | **Đã xử lý; nghiệm thu pass** | 13 focused tests pass, gồm fake verifier `supported` nhưng mapping mâu thuẫn; final 524 passed |
| F1 — Summary uncertain publication | **Đã xử lý; nghiệm thu pass** | 19 safeguard tests pass; final full regression 524 passed |
| F3 — Exact-date evidence | **Đã xử lý; nghiệm thu pass** | 24 safeguard tests pass; exact date chỉ resolve khi literal ISO ở cited source và không có correction rõ; final 524 passed |
| F4 — Claim-level provenance | **Đã harden phần có thể chứng minh; giới hạn còn lại được ghi rõ** | Temporal sources hẹp về segment chứa literal raw deadline khi có; 25 safeguard tests; final 524 passed |
| F5 — Verified-data invariants | **Đã xử lý; nghiệm thu pass** | 91 focused tests pass; final full regression 524 passed |
| HTTP mapping / ASGI review | **Đã rà soát; hành vi hiện hữu đúng, thêm lifecycle regression tests** | 59 focused tests pass; final full regression 524 passed |

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

- [x] Test nhóm A–E thành công với provider giả; không dùng OpenRouter thật trong automated tests.
- [x] Các invalid source IDs, unsupported claims, thiếu evidence hoặc verifier failure không trở thành HTTP 200.
- [x] Summary/Actions hợp lệ trả HTTP 200 qua pipeline verification thực.
- [x] Metadata, timestamp, artifact IDs, null/empty states và review reasons theo Contract v1.
- [x] `evidence_prompt_version` lấy từ prompt verification thực tế.
- [x] HTTP errors, retry policy và privacy guarantees được kiểm tra.
- [x] Regression unit/integration/contract/full suite đều pass.
- [x] Public Contract v1 không đổi; không có implementation ngoài phạm vi đã ủy quyền.
- [x] Báo cáo ghi source paths, kết quả test, giới hạn và handoff.

**Lệnh kiểm thử dự kiến**, chạy từ `apps/llm-service/` sau khi triển khai:

```bash
uv run --locked --extra test pytest -q tests/unit
uv run --locked --extra test pytest -q tests/integration
uv run --locked --extra test pytest -q tests/contract
uv run --locked --extra test pytest -q
```

### 12.3. Test coverage đã chạy theo checkpoint

- **03.5.1:** `tests/unit/services/test_validation_models.py` — 7 passed (status, duplicate/missing/extra claim, request isolation và `repr`).
- **03.5.A:** `tests/unit/services/test_source_validation.py` — 6 source cases; chạy cùng interfaces: 13 passed. Cover source IDs hợp lệ/lạ/trùng, ordering/tie-break, loại topic riêng lẻ và request IDs độc lập.
- **03.5.B:** `tests/unit/services/test_evidence_verification.py` — 11 verifier cases; chạy cùng A/interfaces: 24 passed. Tất cả provider output là fixture/fake; không gọi OpenRouter.
- **03.5.C:** `tests/unit/services/test_temporal_safeguards.py` — 12 safeguard cases; chạy cùng các unit test A/B/interfaces: 36 passed.
- **03.5.D:** `tests/unit/services/test_response_builder.py` — 13 builder cases; chạy cùng A–C/interfaces: 49 passed.
- **03.5.E:** `tests/integration/test_verified_extraction_service.py` — **32 passed**. Fake provider qua production-like service factory; HTTP success/failure, evidence/temporal/owner, auth, timeout/cancellation, concurrency, default fail-closed và privacy cases; không có live OpenRouter calls.
- **03.5.F:** 290 unit, 92 integration, 111 contract và 493 full regression tests passed. Mỗi lệnh được chạy với `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q ...` từ `apps/llm-service/`.
- **Hậu kiểm F9:** baseline trước hardening chạy full suite: **493 passed in 2.77s**. Sau cô lập môi trường/network, `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/integration/test_verified_extraction_service.py tests/unit/providers/test_openrouter.py` — **101 passed**. Ca mới mô phỏng `OPENROUTER_API_KEY` có giá trị và kiểm tra default runtime vẫn fail-closed; test harness chặn outbound HTTP mặc định. Final full regression sau hardening: **524 passed** (xem 13.3).
- **Hậu kiểm F6/F8:** `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/integration/test_verified_extraction_service.py -k 'empty_actions or duration'` — **4 passed, 30 deselected**. Positive empty Actions dùng transcript thảo luận không chốt việc; negative giữ cam kết rõ và verdict `unsupported`. Hai duration tests gọi `ExtractionRequest.model_validate()` trước HTTP, kiểm tra segment hợp lệ, Summary bị chặn trước provider và Actions-only vẫn chạy hai provider calls thành công.
- **Hậu kiểm F7:** `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/unit/services/test_evidence_verification.py tests/unit/prompts/test_registry.py tests/integration/test_verified_extraction_service.py` — **60 passed**. Tests dùng fake provider; kiểm tra correct/incorrect cited source mapping, uncited fact, contradiction, proposal, Summary grounding, prompt injection, complete-transcript empty-action review và version thực thi.
- **Hậu kiểm F2:** `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/unit/services/test_temporal_safeguards.py tests/integration/test_verified_extraction_service.py -k 'owner or speaker or first_person or hypothetical or quoted or explicit_named or different_speakers'` — **12 passed, 39 deselected**. Bao gồm explicit named assignment khác speaker, first-person đúng/sai/mất mapping dù verdict fake là `supported`, quoted/hypothetical, nhiều speakers và HTTP pipeline.
- **Hậu kiểm F1:** `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/unit/services/test_temporal_safeguards.py` — **19 passed**. Thêm ca assertive overview “Nhóm đã hoàn thành triển khai.” với verdict `uncertain` phải fail `UNVERIFIED_EVIDENCE`; Key Topic uncertain bị loại, không rewrite wording và không phát cờ review để hợp thức hóa claim.
- **Hậu kiểm F3:** `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/unit/services/test_temporal_safeguards.py` — **24 passed**. Cover literal ISO trong cited source, date chỉ ở uncited source, ngày ISO sai, leap date hợp lệ, relative/ambiguous/invalid expressions, diễn đạt khác chuẩn để lại unresolved và correction ISO mâu thuẫn ở segment khác.
- **Hậu kiểm F4:** `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/unit/services/test_temporal_safeguards.py` — **25 passed**. Khi raw deadline xuất hiện nguyên văn trong một subset của Action Item sources, `TemporalResolution.source_segment_ids` chỉ giữ subset đó, theo source order đã chuẩn hóa.
- **Hậu kiểm F5:** `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/unit/services/test_validation_models.py tests/unit/services/test_source_validation.py tests/unit/services/test_temporal_safeguards.py tests/unit/services/test_response_builder.py tests/integration/test_verified_extraction_service.py` — **91 passed**. Bao gồm stale/foreign source và revision, complete claim/verdict coverage, requested-module state, unsupported retained field, review/temporal consistency, mutable nested-source corruption, builder type boundary và full verified pipeline.
- **Hậu kiểm HTTP/ASGI:** `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/unit/test_asgi_client.py tests/integration/test_runtime.py tests/integration/test_verified_extraction_service.py` — **59 passed**. Error/status/retryability tests hiện hữu pass; hai test mới xác nhận app lifespan được shutdown khi HTTPX client enter/exit lỗi. Không có code sản xuất mapping lỗi thay đổi.
- **Rà soát bổ sung F2:** Sau review lần cuối, phạm vi từ vựng ngôi thứ nhất được thu hẹp: chỉ `tôi`/`I` được dùng để ánh xạ speaker trực tiếp; `mình`/`em`/`anh`/`chị`/`we` được coi là ambiguous và owner bị null nếu không có assignment nêu tên. Lệnh focused speaker/owner tương ứng — **13 passed, 47 deselected**.
- **Rà soát bổ sung F1:** Assertive overview test dùng chính câu “Nhóm đã hoàn thành triển khai.” với verdict `uncertain`; temporal safeguard suite sau cập nhật test — **26 passed**.

## 13. Nhật ký triển khai (cập nhật khi code)

> **Quy ước:** Mỗi checkpoint ghi file thay đổi, implementation, lệnh và kết quả test, giới hạn, cùng commit/PR nếu có. Không ghi commit/PR không tồn tại.

| Nhóm | Thiết kế | Triển khai | Kiểm chứng | File/commit/ghi chú |
|---|---|---|---|---|
| Interfaces | Đã chốt | Hoàn tất | Đã kiểm chứng | `app/services/validation_models.py`; `tests/unit/services/test_validation_models.py`; 7 passed |
| A — Source Validation | Đã chốt | Hoàn tất | Đã kiểm chứng | `app/services/source_validation.py`; `tests/unit/services/test_source_validation.py`; 13 kết hợp với interface tests passed |
| B — Evidence Verification | Đã chốt | Hoàn tất; sau hardening runtime dùng `evidence-v1.1` | Đã kiểm chứng | Ban đầu `evidence-v1.0`; v1.1 bổ sung cited-source grounding; fake provider |
| C — Temporal/Review | Đã chốt | Hoàn tất | Đã kiểm chứng | `app/services/temporal_safeguards.py`; 12 safeguard cases; 36 combined passed |
| D — Response Builder | Đã chốt | Hoàn tất | Đã kiểm chứng | `app/services/response_builder.py`, preflight Summary duration guard; 13 builder cases; 49 combined passed |
| E — HTTP Integration | Đã chốt | Hoàn tất | Đã kiểm chứng | `services/verified_extraction.py`, `services/factory.py`, `core/errors.py`, `main.py`, `api/dependencies.py`; 32 focused integration tests passed |
| F — Regression/Handoff | Đã lập kế hoạch | Hoàn tất | Đã kiểm chứng | 290 unit, 92 integration, 111 contract; full suite 493 passed; `git diff --check` sạch |

### 13.1. Ghi nhận theo nhóm

**Interfaces — LLM-03.5.1:** Hoàn tất; `validation_models.py` định nghĩa `ClaimIdentity`, `SourceValidatedExtraction`, `VerificationVerdict`/`VerificationStatus`, `VerificationMetadata`, `EvidenceVerifiedExtraction`, `ValidatedExtraction` và typed failures. Test: `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/unit/services/test_validation_models.py` — **7 passed**. Giới hạn: stage factories và runtime wiring được bổ sung ở các checkpoint A–E; full regression đã hoàn tất.

**A — Source Validation:** Hoàn tất; `source_validation.py` kiểm tra và sắp xếp sources theo thời gian, loại topic/item riêng lẻ không hợp lệ theo policy, fail khi Summary overview không có source hoặc không còn Action Item có thể dùng. Chạy `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/unit/services/test_source_validation.py tests/unit/services/test_validation_models.py` — **13 passed**; source validator không phụ thuộc provider. Giới hạn: semantic assessment thuộc nhóm B.

**B — Evidence Verification (checkpoint triển khai ban đầu):** `EvidenceVerifier` ban đầu dùng `evidence-v1.0` registry bundle, strict `EvidenceVerificationOutput`, một call qua provider abstraction, request-bound verdicts và metadata. Chạy `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/unit/services/test_evidence_verification.py tests/unit/services/test_source_validation.py tests/unit/services/test_validation_models.py` — **24 passed**. Sau hậu kiểm F7, runtime dùng prompt mới immutable `evidence-v1.1`; chi tiết và test mới ở 13.4. Fake provider kiểm chứng schema/policy boundary, không đo accuracy model thật; C thực thi cách công bố theo verdict.

**C — Temporal & Review:** Hoàn tất implementation; `TemporalReviewProcessor` áp dụng exact-ISO-only resolution, null hóa field không đủ evidence, chặn Action task không được supported, kiểm tra empty-result verdict và sinh review reasons deterministic. Chạy `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/unit/services/test_temporal_safeguards.py tests/unit/services/test_source_validation.py tests/unit/services/test_evidence_verification.py tests/unit/services/test_validation_models.py` — **36 passed**. Giới hạn: chưa benchmark semantic model thật; conflicts không có status riêng trong verifier schema.

**D — Response Construction:** Hoàn tất; `ResponseBuilder` chỉ nhận `ValidatedExtraction`, dựng sáu module states, metadata/timestamps/usage thật, Action IDs và timestamps deterministic, rồi validate Contract v1. `preflight.py` từ chối Summary duration bị round về 0 trước provider. Chạy `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/unit/services/test_response_builder.py` — **13 passed**; combined A–D/interfaces — **49 passed**. Public schemas giữ nguyên.

**E — HTTP Integration:** Hoàn tất; composition mặc định dùng `VerifiedExtractionService`, error mapping dùng thông điệp cố định theo code, không phản chiếu raw exception. HTTP integration tests dùng `ASGITransport` — **32 passed**; `api/dependencies.py` dùng async app-state getters sau khi trace thấy sync dependency treo trước endpoint trong AnyIO worker ở môi trường này. Test cancellation xác nhận hủy request truyền xuống provider call.

**F — Full regression:** Hoàn tất; lệnh unit **290 passed**, integration **92 passed**, contract **111 passed**, full suite **493 passed**. Suite integration cũ được chuyển sang helper `tests/asgi_client.py`, giữ app lifespan và loop cho test context, vì `TestClient` bị treo ở môi trường hiện tại. Các test mặc định được cập nhật để kỳ vọng `VerifiedExtractionService` fail-closed; không dùng live provider.

### 13.2. Các quyết định phát sinh trong triển khai

- Không phát hiện xung đột cần thay đổi API Contract v1 hoặc quyết định D-01 đến D-15.
- `create_app()` mặc định được nối vào `VerifiedExtractionService` theo scope E; thiếu provider credentials vẫn trả `PROVIDER_CONFIGURATION_ERROR` và không có đường unverified.
- `get_settings`/`get_extraction_service` chuyển sang async sau khi integration trace cho thấy sync dependency bị treo trong AnyIO worker tại môi trường hiện tại.
- Integration test harness chuyển từ Starlette `TestClient` sang helper `tests/asgi_client.py` dựa trên `ASGITransport`, vì `TestClient` treo trước khi app lifespan bắt đầu; đây là thay đổi test-only để chạy regression trong môi trường hiện tại.
- Không thêm dependency. Không dùng provider thật. Không tạo branch, commit, push, merge hoặc PR.

### 13.3. Kết quả regression trước remediations R1–R3

- **Baseline tham khảo:** 412 passed theo báo cáo LLM-03.4 Group D.
- **Baseline trước hardening:** 290 unit + 92 integration + 111 contract = **493 passed** (kết quả lịch sử LLM-03.5, không dùng làm kết quả hiện tại).
- **Kết quả checkpoint trước remediation:** 319 unit + 94 integration + 111 contract = **524 passed**; full suite **524 passed in 2.95s**, không có test thất bại.
- **Lệnh tại checkpoint trước remediation** (chạy từ `apps/llm-service/`, dùng uv cache ở `/tmp` do cache mặc định chỉ đọc):
  - `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/unit` — **319 passed in 1.36s**.
  - `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/integration` — **94 passed in 1.83s**.
  - `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/contract` — **111 passed in 0.49s**.
  - `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q` — **524 passed in 2.95s**.
- **Các test bổ sung:** 31 test mới sau hậu kiểm: F9 isolation, F6/F8 scenario correction, F7 prompt/source grounding, F2 owner attribution, F1/F3/F4 temporal/review, F5 internal invariants và ASGI lifecycle. Fake provider/verifier toàn bộ; không có live provider calls.
- **Số liệu provider thật / chi phí:** Không thuộc offline acceptance; chỉ ghi khi đã được cấp phép kiểm thử và có kết quả thật.

### 13.4. Nhật ký hậu kiểm và hardening

**F9 — Cô lập provider trong test (đã xử lý):** Review xác nhận `make_settings()` trước đây không truyền rõ `openrouter_api_key`, nên `Settings` có thể đọc credential từ môi trường. Thêm `tests/conftest.py` autouse fixture xóa biến môi trường provider và chặn `httpx.HTTPTransport`/`AsyncHTTPTransport` outbound; helper pipeline đặt `openrouter_api_key=None` tường minh. Thêm integration test mô phỏng biến `OPENROUTER_API_KEY` được export, xác minh default runtime trả lỗi cấu hình, `/health` vẫn hoạt động và response không lộ khóa. Files: `apps/llm-service/tests/conftest.py`, `apps/llm-service/tests/integration/test_verified_extraction_service.py`. Test: integration verified-pipeline + OpenRouter adapter **101 passed**; baseline full suite ngay trước sửa đổi **493 passed**. Không sửa production credential-loading. Giới hạn: test isolation chặn HTTPX transports phổ biến; test thủ công `tests/manual/openrouter_smoke.py` vẫn là công cụ chủ ý gọi mạng và không thuộc pytest.

**F6/F8 — Sửa test empty Actions và Summary duration (đã xử lý):** Positive empty Actions nay dùng transcript thảo luận không có commitment; test đối chứng vẫn dùng cam kết “Tôi sẽ gửi...” và yêu cầu fake verifier trả `unsupported`. Docstring nêu rõ fake verdict kiểm tra pipeline policy chứ không chứng minh semantic accuracy. Duration cases đặt segment start/end hợp lệ và validate payload bằng `ExtractionRequest` trước HTTP; Summary phải trả `VALIDATION_ERROR` mà không gọi provider, còn Actions-only với cùng duration vẫn hoàn tất. File đổi: `apps/llm-service/tests/integration/test_verified_extraction_service.py`. Test mục tiêu: **4 passed, 30 deselected**. Không thêm heuristic tổng quát để phát hiện commitments.

**F7 — Grounding theo đúng cited segments (đã xử lý):** Nguyên nhân xác nhận: prompt `evidence-v1.0` không phân biệt đủ rõ cited evidence với ngữ cảnh transcript khác. Giữ nguyên bundle đã công bố và đăng ký prompt mới bất biến `evidence-v1.1`; verifier runtime lấy phiên bản từ bundle đã render. System prompt yêu cầu claim chỉ được `supported` nếu chính các segment trong `source_segment_ids` đủ chứng minh nội dung; segment khác chỉ hỗ trợ context, chronology, contradiction/qualification và phát hiện commitment bị bỏ sót trong empty Actions. User prompt cung cấp toàn transcript và JSON claim/source map; transcript vẫn là untrusted data. Files: `apps/llm-service/app/prompts/registry.py`, `app/prompts/v1_1/evidence_system.md`, `app/prompts/v1_1/evidence_verification.md`, `app/services/evidence.py`, tests verifier và HTTP version assertion. Chạy verifier/registry/integration focus: **60 passed**. Tests dùng fake verdict, vì vậy xác nhận bundle/mapping/policy plumbing chứ không chứng minh model thật luôn tuân thủ. Giới hạn: claim-level source IDs cho các field thuộc Action Item vẫn kế thừa source của item như giới hạn F4 ở checkpoint sau.

**F2 — Owner attribution chống verdict sai (đã xử lý):** Tái hiện: `TemporalReviewProcessor` trước đây chỉ xem speaker mapping khi owner đã null; verdict `supported` có thể giữ owner trái với mapping của phát biểu ngôi thứ nhất. Thêm safeguard xác định hẹp cho cấu trúc `tôi`/`I` commitment trong cited segment, ánh xạ speaker ID sang participant display name, và null hóa owner khi mapping thiếu/mâu thuẫn hoặc nhiều speaker attribution xung đột. Các đại từ tiếng Việt/Anh mơ hồ như `mình`/`em`/`anh`/`chị`/`we` không được dùng để suy ra speaker owner; quote, giả định và phủ định cũng không được coi là commitment trực tiếp. Có nhận diện riêng một số assignment nêu tên như “Minh nhận ...”; không loại owner chỉ vì speaker khác. Khi không đủ chắc chắn, owner thành null và review. Files: `apps/llm-service/app/services/temporal_safeguards.py`, unit safeguards và HTTP integration tests. Checkpoint ban đầu: **12 passed**; review bổ sung sau thu hẹp pronoun: **13 passed, 47 deselected**. Giới hạn: đây là safeguard từ vựng/cấu trúc hẹp, không phải classifier tiếng Việt tổng quát; paraphrase, câu ghép phức tạp và attribution ngầm vẫn phụ thuộc verifier; fake tests không đo semantic accuracy model thật.

**F1 — Không publish Summary uncertain như sự kiện (đã xử lý):** Tái hiện: overview `uncertain` trước đó được giữ nguyên assertive text với `claim_uncertain`; Key Topic uncertain cũng được giữ. Processor nay fail request bằng `UNVERIFIED_EVIDENCE` nếu overview requested không supported, và bỏ Key Topic có verdict `uncertain` giống claim unsupported tùy chọn. Không tự sửa câu, không dùng cờ review để xuất bản nội dung assertive chưa xác minh. Files: `apps/llm-service/app/services/temporal_safeguards.py`, `tests/unit/services/test_temporal_safeguards.py`. Kết quả: **19 passed**. Test fake kiểm tra policy mapping, không kết luận độ chính xác verifier model.

**F3 — Exact date phải được cited evidence hỗ trợ (đã xử lý):** Nguyên nhân xác nhận: parse canonical ISO và verdict `supported` trước đó đủ để publish exact dù chuỗi ngày không có trong cited segment. Processor hiện chỉ resolve exact ISO canonical nếu ngày hợp lệ, literal ISO xuất hiện trong chính các cited source của Action Item, verifier trả `supported`, và không có correction rõ chứa candidate cùng ngày ISO khác. Nếu thiếu literal/có correction thì `due_date=null`, resolution `unresolved` và review reasons `evidence_unverified` hoặc `conflicting_statements`; ngày diễn đạt khác chuẩn giữ unresolved, không normalize. Files: `apps/llm-service/app/services/temporal_safeguards.py`, temporal unit tests. Kết quả: **24 passed**. Giới hạn: correction detector chỉ nhận diện các marker rõ ràng cùng nhiều ISO dates; mâu thuẫn diễn đạt tự nhiên khác vẫn thuộc semantic verifier/LLM-04.

**F4 — Độ chính xác temporal provenance (đã harden một phần, giới hạn ghi nhận):** Review xác nhận `ClaimIdentity` hiện nhận source IDs của toàn Action Item cho task/owner/deadline/priority/context; Contract v1 không có field claim-level và candidate schema hiện tại cũng không cung cấp claim-level references. Không suy diễn IDs mới. Bổ sung narrowing an toàn cho `TemporalResolution`: nếu raw deadline xuất hiện literal trong một hoặc một số cited item segments, chỉ các segment khớp được ghi ở resolution, giữ thứ tự nguồn; test xác nhận segment không liên quan bị loại. Nếu biểu thức tương đối/paraphrase không xuất hiện nguyên văn, hệ thống giữ source list item-level do verifier phải đánh giá ngữ nghĩa trong tập đó; không giả vờ có claim-level attribution. Files: `apps/llm-service/app/services/temporal_safeguards.py`, `tests/unit/services/test_temporal_safeguards.py`. Kết quả: **25 passed**. Giới hạn còn lại cần thiết: claim-level nguồn riêng cho task/owner/priority/context và deadline paraphrase đòi hỏi schema/verifier capability mở rộng, ngoài remediation scope; source validation + v1.1 cited-set verifier vẫn bắt buộc.

**F5 — Ràng buộc verified data và response boundary (đã xử lý):** Thêm `SourceValidatedExtraction.validate_invariants()` để đối chiếu request/module state, transcript source index + revision, source membership/order, candidate-to-claim content/source map và claim completeness. `EvidenceVerifiedExtraction.validate_invariants()` tái kiểm tra source state cùng complete verdict set. `ValidatedExtraction.validate_invariants()` kiểm tra request/module compatibility, overview/task/field verdict support, retained topics/items, source references, deadline-resolution consistency và review reason enum/order/state. `ResponseBuilder.build()` gọi lại các invariant và chạy `TemporalReviewProcessor` deterministic lần nữa; nếu state không bằng kết quả safeguards tính lại thì không xây response. Tests còn mô phỏng nested Pydantic source list bị sửa sau khi dataclass được tạo. Files: `apps/llm-service/app/services/validation_models.py`, `app/services/response_builder.py`, `tests/unit/services/test_validation_models.py`, `tests/unit/services/test_response_builder.py`. Focus set unit + end-to-end fake-provider: **91 passed**. Contract v1 không đổi; không có đường `ProjectedExtraction` trực tiếp sang builder. Giới hạn: semantic accuracy tiếp tục phụ thuộc verifier; deterministic revalidation chỉ kiểm tra state/policy và không xác nhận phán đoán model.

**Task 6 — HTTP error mapping và ASGI harness (đã rà soát):** Đọc đầy đủ `app/core/errors.py`, `app/schemas/errors.py`, `app/services/verified_extraction.py`, provider errors/timeout wrapper, middleware, route và `tests/asgi_client.py`. Xác nhận source validation/unsupported mandatory evidence → 502 `UNVERIFIED_EVIDENCE`; candidate/verifier schema → 502 `INVALID_STRUCTURED_OUTPUT`; provider config/rate limit/timeout/failure → 503/503/504/502 với retry invariants; request budget → 504 `REQUEST_TIMEOUT`; request validation giữ contract hiện hữu. Cancellation `asyncio.CancelledError` không bị swallow; exception/log sanitize không phản chiếu nội dung. ASGI helper quản lý lifespan trên cùng event loop, và `asyncio.Runner.close()` shutdown async generators kể cả khi client context enter/exit lỗi; thêm hai regression tests trực tiếp cho hai nhánh này. Files mới: `apps/llm-service/tests/unit/test_asgi_client.py`; production mapping/helper không đổi vì chưa thấy lỗi hành vi. Lệnh runtime + verified pipeline + ASGI focus: **59 passed**. Hạn chế: test helper vẫn dựa trên HTTPX ASGITransport và asyncio.Runner; live network tiếp tục bị chặn bởi `tests/conftest.py`.

**Kiểm tra Contract v1 và phạm vi:** Không thay đổi `app/schemas/request.py`, `app/schemas/response.py` hoặc `app/schemas/errors.py`; không thêm dependency, provider retry, structured-output repair, verification bypass hay business module. `git diff --check` pass; không có staged changes.

## 14. Giới hạn, rủi ro và handoff

1. **LLM verifier không tuyệt đối chính xác:** Cần kiểm chứng thêm trên dữ liệu có quyền sử dụng trước khi khẳng định chất lượng production.
2. **Trường `ProcessingMetadata` chỉ có một `provider/model_id`:** MVP giới hạn extraction/verification cùng provider/model. Nếu sau này tách model, phải có thiết kế metadata rõ thay vì ghi sai sự thật.
3. **Transcript dài:** Request byte limit không tương đương token/context limit; chunking và aggregation không nằm trong LLM-03.5.
4. **Temporal parsing giới hạn:** Relative dates, date ranges và timezone semantics phức tạp chuyển sang LLM-04; LLM-03.5 không tự suy diễn.
5. **Evidence verification tổng quát:** Mở rộng sang sáu module thuộc LLM-06 và các milestone liên quan.
6. **Backend integration:** LLM Service vẫn là component độc lập; kết nối NestJS/Web là công việc khác.
7. **Duration dương cực ngắn:** Summary request làm tròn thành `0.0` bị reject trước provider; Actions-only vẫn được chấp nhận theo projection hiện tại. Unit và HTTP tests xác nhận hai nhánh.
8. **Semantic accuracy:** Prompt v1.1 và fake-provider tests không thay thế đánh giá model thật; chưa có live-model benchmark trong remediation.
9. **Owner attribution:** Guard xác định hẹp cho `tôi`/`I`, quote, giả định và một số assignment pattern; paraphrase hoặc câu tiếng Việt phức tạp vẫn cần verifier và có thể phải review.
10. **Claim-level provenance:** Deadline literal được narrow theo segment khớp; task/owner/priority/context và deadline paraphrase vẫn dùng source set của Action Item do schema hiện tại không có provenance riêng theo field.

## 15. Tài liệu tham chiếu

- [Tổng quan LLM-03](./llm-03-overview.md)
- [Báo cáo LLM-03.4 và handoff](./llm-03.4-extraction-service-report.md)
- [API Contract v1](../../llm-service-contract.md)
- [Kiến trúc LLM Service](../../llm-service-architecture.md)
- [Implementation Roadmap](../../../implementation-roadmap.md)
- [Contributing](../../../../CONTRIBUTING.md)

---

**Kết luận checkpoint trước remediation:** LLM-03.5 hardening tại thời điểm ghi nhận đã đạt **524 passed**. Kết quả chỉ publish sau source validation, semantic evidence verification, temporal/review safeguards và response construction; mọi lỗi bắt buộc fail-closed theo Contract v1. Không có live provider call hoặc commit/push/PR.

## MVP Final Remediation — R1, R2, R3

### R1 — Deadline Verification & Human Review

- **Nguyên nhân:** Safeguard cũ yêu cầu biểu thức deadline xuất hiện nguyên văn trong transcript và quét từ khóa correction trên toàn transcript. So sánh literal làm rớt ngày tự nhiên tương đương ISO; việc chọn source bằng literal cũng tạo độ chính xác provenance không có căn cứ.
- **Quyết định MVP:** Dùng verdict semantic verifier cho quan hệ deadline/evidence; Python chỉ parse ngày ISO canonical và giữ trạng thái review nhất quán.
- **Giải pháp triển khai:** Bỏ điều kiện deadline phải khớp nguyên văn để công bố `exact_date`. Với ngày canonical và verdict `supported`, giữ deadline; với `uncertain`, giữ expression, để ngày null và resolution unresolved; với `unsupported`, xóa expression và resolution nhưng giữ task đã được xác minh. Temporal resolution giữ nguyên claim-level source IDs.
- **File thay đổi:** `apps/llm-service/app/services/temporal_safeguards.py`; unit/integration tests tương ứng.
- **Test bổ sung:** ISO nguyên văn, ngày tiếng Việt/Anh tương đương, deadline thiếu năm/tương đối uncertain, ngày không hợp lệ, deadline unsupported cùng task supported, source hợp lệ nhưng verifier unsupported và review state của Contract v1.
- **Kết quả kiểm thử:** `tests/unit/services/test_temporal_safeguards.py` — **31 passed**; `tests/integration/test_verified_extraction_service.py` — **38 passed**. Đây là kiểm chứng chính sách pipeline với verdict scripted, không phải đánh giá độ chính xác semantic của model thật.
- **Giới hạn còn lại:** Python không chứng minh nội dung ngày bằng NLP; kết quả semantic phụ thuộc verifier. Ngày không canonical được giữ unresolved để người dùng xác nhận.

### R2 — Owner Attribution

- **Nguyên nhân:** Guard cũ so task bằng phần giao từ khóa trên cả câu, nên commitment ngôi thứ nhất cho task trước có thể bị ghép nhầm với task được giao tên sau đó trong cùng segment.
- **Quyết định MVP:** EvidenceVerifier quyết định owner của từng Action Item; Python chỉ giữ một integrity check hẹp cho mâu thuẫn speaker mapping rõ ràng.
- **Giải pháp triển khai:** Bỏ overlap từ khóa, nhận diện assignment theo nhiều mẫu và suy luận owner từ mọi speaker trong source. Guard chỉ xét commitment ngôi thứ nhất tường minh khi nguyên văn task xuất hiện trong cùng clause đơn giản; tách clause ở dấu câu liên kết thông dụng. Named owner trong clause không bị speaker của segment ghi đè. Verdict uncertain/unsupported tiếp tục xóa owner và gắn review.
- **File thay đổi:** `apps/llm-service/app/services/temporal_safeguards.py`; unit/integration tests tương ứng.
- **Test bổ sung:** Hai assignment trong một câu; named assignment từ speaker khác; first-person có mapping/mâu thuẫn; speaker mapping thiếu; câu hypothetical/quoted theo verdict uncertain; nhiều cited segments với task khác nhau; verdict supported/uncertain/unsupported.
- **Kết quả kiểm thử:** `tests/unit/services/test_temporal_safeguards.py` — **33 passed**; `tests/integration/test_verified_extraction_service.py` — **40 passed**. Hai lời hứa trong cùng segment được giữ đúng owner; ordinary successful request vẫn có đúng hai provider generations.
- **Giới hạn còn lại:** Guard chỉ nhận diện exact task phrase trong clause rõ ràng; paraphrase và quan hệ owner-task phức tạp thuộc verifier. Test quote/hypothetical đã đổi sang verdict uncertain vì kỳ vọng Python tự phân loại ngữ nghĩa trước đây không phù hợp ranh giới đã duyệt.

### R3 — Deadline Correction

- **Nguyên nhân:** Regex correction gom các ngày và từ khóa trong một segment mà không biết ngày nào thuộc Action Item nào; scan cục bộ cũng không hiểu chronology xuyên nhiều segment.
- **Quyết định MVP:** Verifier chịu trách nhiệm liên hệ deadline với task, chronology và trạng thái xác nhận cuối; Python không sửa candidate hoặc suy diễn correction.
- **Giải pháp triển khai:** Xóa `_explicit_date_conflict()`, `_DATE_CORRECTION`, `_ISO_DATE` và nhánh review conflict phát sinh từ global scan. Ngày chỉ được giữ exact khi candidate ISO canonical và verdict deadline là `supported`; verdict `uncertain` giữ unresolved; `unsupported` xóa deadline mà không thay bằng ngày khác.
- **File thay đổi:** `apps/llm-service/app/services/temporal_safeguards.py`; unit/integration tests tương ứng.
- **Test bổ sung:** Correction UI không ảnh hưởng deadline API dù cùng segment có ngày cũ/mới; final natural-language date được giữ khi verdict supported; correction proposal uncertain vẫn unresolved; obsolete candidate unsupported bị xóa không thay thế; có đúng hai provider generations.
- **Kết quả kiểm thử:** `tests/unit/services/test_temporal_safeguards.py` — **35 passed**; `tests/integration/test_verified_extraction_service.py` — **41 passed**. Các test chứng minh Python xử lý đúng verdict giả lập, không chứng minh model thật nhận diện correction chính xác.
- **Giới hạn còn lại:** Verifier chỉ trả verdict, không sửa candidate; ngày cuối đúng chỉ được xuất nếu extraction ban đầu đưa ngày đó và verifier hỗ trợ, nếu không người dùng cần sửa khi review.

### Cập nhật Evidence Verification Prompt

- **Phiên bản mới:** Runtime chuyển sang prompt bất biến `evidence-v1.2`; `evidence-v1.0` và `evidence-v1.1` vẫn được đăng ký, file cũ không bị ghi đè.
- **Chính sách bổ sung:** Prompt yêu cầu attribution theo task riêng, phân biệt first-person/named assignment, câu nhiều assignment, quote/question/proposal/conditional/rejected; đối chiếu deadline với task, chronology, later references, correction confirmed vs đề xuất, date natural-language tương đương ISO và không chuyển correction qua task khác.
- **Grounding:** Các cited segment được xét kết hợp để support; uncited transcript chỉ cung cấp chronology/correction/contradiction/context và không thay thế positive grounding. Giữ strict `checks` output, claim IDs và verdict enum hiện tại.
- **Context nội bộ:** Renderer bổ sung `action_item_context` cho các claim của Action Item (task/owner/deadline/priority/context), cùng anchor date/timezone; transcript đầy đủ và participant mapping đã có tiếp tục được gửi. Không thêm field vào public Contract v1 hoặc output verifier.
- **File thay đổi:** `app/prompts/registry.py`, `app/prompts/renderer.py`, `app/prompts/v1_2/evidence_system.md`, `app/prompts/v1_2/evidence_verification.md`, `app/services/evidence.py`; prompt/evidence/integration tests.
- **Kết quả kiểm thử:** `tests/unit/services/test_evidence_verification.py` — **20 passed**; `tests/unit/prompts/test_registry.py tests/unit/prompts/test_renderer.py` — **19 passed**; `tests/integration/test_verified_extraction_service.py` — **41 passed**. HTTP integration xác nhận public response ghi đúng `evidence-v1.2` và vẫn đúng hai provider generations.
- **Giới hạn còn lại:** Prompt là hướng dẫn cho model, không phải đảm bảo semantic accuracy; cần human review cho thông tin uncertain.

### Regression cuối sau remediations

- **Baseline được xác nhận trước remediation:** **524 passed** trên working tree hiện tại.
- **Unit:** `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/unit` — **330 passed**.
- **Integration:** `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/integration` — **101 passed**.
- **Contract:** `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/contract` — **111 passed**.
- **Toàn bộ suite:** `uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q` — **542 passed in 4.23s**; tăng 18 test so với baseline 524.
- Không gọi live provider, không thêm dependency, không đổi Contract v1, không thêm lần generation thứ ba. `git diff --check` sạch; không stage, commit hoặc push.
- Kết quả scripted provider xác nhận chính sách xử lý verdict và mapping trong pipeline; không chứng minh khả năng hiểu ngữ nghĩa của model thật.
