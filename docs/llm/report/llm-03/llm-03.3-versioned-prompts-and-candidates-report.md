# LLM-03.3 — Versioned Prompts & Extraction Schema

## 1. Overview

- **Mục tiêu milestone:** chuẩn hóa prompt có phiên bản và biểu diễn trung gian cho nội dung trích xuất Summary/Actions trước khi xác minh và tạo response Contract v1.
- **Phạm vi báo cáo:** toàn bộ LLM-03.3.1–LLM-03.3.7, gồm Candidate Schema, Pydantic models, prompt templates, registry, renderer, parser và offline integration tests.
- **Milestone liên quan:** LLM-03.2 cung cấp provider interface và OpenRouter adapter; LLM-03.4 sẽ điều phối extraction và dựng response cuối.
- **Trạng thái:** LLM-03.3.1–LLM-03.3.7 hoàn thành; toàn milestone LLM-03.3 hoàn thành trong phạm vi versioned prompts, candidate schema và offline integration. LLM-03.4 production orchestration vẫn nằm ngoài phạm vi.
- **Tài liệu tham chiếu:** [API Contract](../../llm-service-contract.md), [kiến trúc LLM Service](../../llm-service-architecture.md), [tổng quan LLM-03](llm-03-overview.md), báo cáo [LLM-03.1](llm-03.1-provider-selection-and-smoke-test-report.md) và [LLM-03.2](llm-03.2-provider-adapter-report.md).

Candidate là nội dung do model đề xuất và chỉ được kiểm tra cấu trúc. Nó không phải response công khai đã xác minh, cũng không chứng minh claim được nguồn trích dẫn hỗ trợ.

## 2. LLM-03.3.1 — Candidate Schema Specification

### Mục tiêu thiết kế

- Chỉ chứa nội dung tối thiểu cần cho hai module đang triển khai: Meeting Summary và Action Items.
- Bắt buộc các trường đã định nghĩa, cấm trường ngoài schema và không ép kiểu ngầm.
- Giữ riêng candidate với public Contract v1; metadata cuộc họp lấy từ request, còn ID/timestamp/trạng thái review và kết quả thời gian thuộc các bước sau.
- Giữ nguyên nội dung tiếng Việt và biểu thức hạn chót gốc.
- Cấu trúc không xác nhận sự tồn tại hoặc tính đúng đắn ngữ nghĩa của nguồn.

### Kiến trúc schema

~~~text
SummaryActionsCandidate
├── meeting_summary: MeetingSummaryCandidate | null
│   ├── overview: NonBlankString
│   ├── key_topics: list[KeyTopicCandidate]
│   └── source_segment_ids: list[OpaqueId]
└── action_items: list[ActionItemCandidate] | null
    ├── task: NonBlankString
    ├── owner: NonBlankString | null
    ├── raw_due_expression: NonBlankString | null
    ├── priority: Priority | null
    ├── context: NonBlankString | null
    └── source_segment_ids: list[OpaqueId]
~~~

Tất cả trường trong bốn model đều bắt buộc vì không trường nào có giá trị mặc định. Kiểu <code>| None</code> chỉ cho phép giá trị JSON <code>null</code>; nó không làm trường trở thành tùy chọn khi bị thiếu.

### Định nghĩa bốn model

| Model | Trường | Kiểu | Bắt buộc | Nullable | Quy tắc cấu trúc |
|---|---|---|---:|---:|---|
| <code>SummaryActionsCandidate</code> | <code>meeting_summary</code> | <code>MeetingSummaryCandidate \| None</code> | Có | Có | Null khi không yêu cầu; phải có dữ liệu khi được yêu cầu. |
| <code>SummaryActionsCandidate</code> | <code>action_items</code> | <code>list[ActionItemCandidate] \| None</code> | Có | Có | Null khi không yêu cầu; phải là list khi được yêu cầu. List rỗng hợp lệ. |
| <code>MeetingSummaryCandidate</code> | <code>overview</code> | <code>NonBlankString</code> | Có | Không | Phải có ký tự không phải khoảng trắng. |
| <code>MeetingSummaryCandidate</code> | <code>key_topics</code> | <code>list[KeyTopicCandidate]</code> | Có | Không | List rỗng hợp lệ. |
| <code>MeetingSummaryCandidate</code> | <code>source_segment_ids</code> | <code>list[OpaqueId]</code> | Có | Không | Ít nhất một ID, không trùng lặp. |
| <code>KeyTopicCandidate</code> | <code>topic</code> | <code>NonBlankString</code> | Có | Không | Phải có ký tự không phải khoảng trắng. |
| <code>KeyTopicCandidate</code> | <code>brief_discussion</code> | <code>NonBlankString</code> | Có | Không | Phải có ký tự không phải khoảng trắng. |
| <code>KeyTopicCandidate</code> | <code>source_segment_ids</code> | <code>list[OpaqueId]</code> | Có | Không | Ít nhất một ID, không trùng lặp; hỗ trợ nhiều segment. |
| <code>ActionItemCandidate</code> | <code>task</code> | <code>NonBlankString</code> | Có | Không | Phải có ký tự không phải khoảng trắng. |
| <code>ActionItemCandidate</code> | <code>owner</code> | <code>NonBlankString \| None</code> | Có | Có | <code>null</code> hợp lệ. Không có validator chặn sentinel trong schema v1. |
| <code>ActionItemCandidate</code> | <code>raw_due_expression</code> | <code>NonBlankString \| None</code> | Có | Có | Giữ biểu thức gốc; không resolve thành ngày lịch. |
| <code>ActionItemCandidate</code> | <code>priority</code> | <code>Priority \| None</code> | Có | Có | Tái sử dụng enum Contract v1 (<code>High</code>, <code>Medium</code>, <code>Low</code>) hoặc null. |
| <code>ActionItemCandidate</code> | <code>context</code> | <code>NonBlankString \| None</code> | Có | Có | Null nếu không có giải thích bổ sung được hỗ trợ. |
| <code>ActionItemCandidate</code> | <code>source_segment_ids</code> | <code>list[OpaqueId]</code> | Có | Không | Ít nhất một ID, không trùng lặp; hỗ trợ nhiều segment. |

<code>NonBlankString</code>, <code>OpaqueId</code>, <code>ContractModel</code>, <code>ensure_unique</code> và <code>Priority</code> được tái sử dụng từ schema hiện có. <code>ContractModel</code> áp dụng strict validation, cấm extra fields và không chấp nhận coercion ngầm.

### Ma trận chọn module

| Module trong request | <code>meeting_summary</code> candidate | <code>action_items</code> candidate |
|---|---|---|
| Chỉ <code>meeting_summary</code> | Object, không được null | Bắt buộc null |
| Chỉ <code>action_items</code> | Bắt buộc null | List, không được null; list rỗng được phép |
| Cả hai module | Object, không được null | List, không được null; list rỗng được phép |
| Bất kỳ module chưa hỗ trợ nào | Helper từ chối request | Không âm thầm bỏ qua module |

<code>validate_candidate_for_request(candidate, request)</code> nhận <code>SummaryActionsCandidate</code> và <code>ExtractionRequest</code>, kiểm tra các module được yêu cầu có nằm trong tập <code>meeting_summary</code>/<code>action_items</code> không, rồi kiểm tra nullability theo ma trận. Helper trả lại candidate nếu hợp lệ và ném <code>ValueError</code> khi module không được hỗ trợ hoặc dữ liệu module không khớp request. Request có danh sách module rỗng đã bị từ chối bởi validation của Contract v1.

Validation root theo request được giữ tách khỏi structural validation: một candidate có thể parse thành công nhưng không phù hợp với module của request.

### Yêu cầu source reference

Mọi summary, topic và action candidate phải có ít nhất một <code>source_segment_id</code>; ID trong cùng trường không được trùng. <code>OpaqueId</code> được giữ nguyên chính xác. Structural validation không tra ID trong transcript: một ID có cú pháp hợp lệ nhưng không xuất hiện trong request vẫn có thể parse và qua helper. Việc kiểm tra tồn tại và bằng chứng thuộc các bước sau.

### Versioning policy

Schema nội bộ có định danh <code>candidate-v1</code>, thể hiện bằng hằng <code>CANDIDATE_SCHEMA_VERSION</code>; hằng này không được yêu cầu trong JSON do LLM sinh. Nó độc lập với public <code>contract_version = "1.0"</code> và phiên bản prompt, ví dụ <code>extract-v1.0</code>. PromptRegistry hiện trả cặp prompt/schema version trong bundle; PromptRenderer giữ metadata này cho caller. Candidate Parser hiện dùng trực tiếp model Candidate Schema v1; chưa có logic orchestration chọn parser theo version động.

### JSON hợp lệ

Ví dụ tổng hợp dùng dữ liệu meeting giả lập; đây không phải kết quả từ model thật:

~~~json
{
  "meeting_summary": {
    "overview": "Cuộc họp rà soát tiến độ và ghi nhận cam kết gửi bản ghi chú.",
    "key_topics": [
      {
        "topic": "Rà soát tiến độ",
        "brief_discussion": "Nhóm rà lại tiến độ công việc hiện tại.",
        "source_segment_ids": ["seg-a2"]
      }
    ],
    "source_segment_ids": ["seg-a1", "seg-a2"]
  },
  "action_items": [
    {
      "task": "Gửi bản ghi chú",
      "owner": "Alex",
      "raw_due_expression": "thứ Sáu này",
      "priority": null,
      "context": null,
      "source_segment_ids": ["seg-a1"]
    }
  ]
}
~~~

Summary-only hợp lệ dùng object trên tại <code>meeting_summary</code> và <code>"action_items": null</code>. Actions-only hợp lệ dùng <code>"meeting_summary": null</code> và list tại <code>action_items</code>. List actions rỗng (<code>[]</code>) hợp lệ khi module actions được yêu cầu nhưng không có cam kết hành động.

### JSON không hợp lệ

Thiếu <code>owner</code> không hợp lệ, dù owner nullable, vì trường bắt buộc phải hiện diện:

~~~json
{
  "task": "Gửi bản ghi chú",
  "raw_due_expression": null,
  "priority": null,
  "context": null,
  "source_segment_ids": ["seg-a1"]
}
~~~

Trường ngoài schema cũng không hợp lệ:

~~~json
{
  "task": "Gửi bản ghi chú",
  "owner": null,
  "raw_due_expression": null,
  "priority": null,
  "context": null,
  "source_segment_ids": ["seg-a1"],
  "id": "ACT-001"
}
~~~

Các chuỗi rỗng/toàn khoảng trắng, danh sách source rỗng/trùng ID, priority ngoài enum, kiểu sai và JSON malformed cũng bị từ chối.

### Candidate và response cuối

Candidate chỉ chứa nội dung ứng viên và source IDs. Candidate không có <code>title</code>, <code>date</code>, <code>duration_minutes</code>, <code>participants</code>, artifact <code>id</code>, <code>due_date</code>, <code>due_date_resolution</code>, <code>source_timestamp</code>, <code>needs_review</code> hoặc <code>review_reasons</code>. Không bổ sung bốn business modules còn lại. Candidate structural-valid không phải artifact đã được xác minh và không thay thế response Contract v1.

### Ranh giới validation

**Đã thực hiện — structural validation:** field presence/type, nullability bắt buộc, strict enum, chuỗi không blank, list source không rỗng/không trùng, cấm extra fields và root module-selection consistency.

**Để các milestone tiếp theo xử lý — reference/ngữ nghĩa:** kiểm tra source ID tồn tại trong transcript; dẫn chứng hỗ trợ claim; xác minh owner; phân biệt cam kết với đề xuất; xác minh deadline; quyết định review flags; gộp các action trùng lặp. Các test ở đây không chứng minh độ chính xác extraction hoặc chống hallucination.

### Quyết định và trade-off

- **Owner sentinel:** theo phê duyệt, schema chỉ dùng <code>owner: NonBlankString | None</code>; không thêm validator cấm <code>"Unknown"</code>/<code>"Unassigned"</code>. Prompt và semantic checks sau này cần hướng model dùng null nếu chưa xác định.
- **Priority:** tái sử dụng <code>Priority</code> từ public response schema để enum candidate thống nhất Contract v1; không suy luận priority từ urgency, chức danh hoặc deadline ở tầng cấu trúc.
- **Request-aware helper:** giữ đúng phạm vi cho module hiện hỗ trợ, từ chối module khác một cách tường minh thay vì âm thầm bỏ qua.
- **Không kiểm tra tồn tại source tại đây:** model chỉ có cấu trúc, không đủ ngữ cảnh để xác nhận ID hoặc bằng chứng.
- **Không sửa Contract v1:** candidate được thêm độc lập, không thay đổi public response/request models.

Không còn câu hỏi thiết kế chặn hai task đã duyệt. Rủi ro còn lại là chất lượng/ý nghĩa candidate chỉ có thể xác định sau bước reference và semantic validation.

**Trạng thái phê duyệt:** người dùng đã phê duyệt LLM-03.3.1 và LLM-03.3.2, kèm quyết định không chặn owner sentinel.

## 3. LLM-03.3.2 — Pydantic Candidate Models

### Tổng quan triển khai

- <code>SummaryActionsCandidate</code>, <code>MeetingSummaryCandidate</code>, <code>KeyTopicCandidate</code>, <code>ActionItemCandidate</code> được triển khai trong <code>app/schemas/candidates.py</code>.
- <code>_SourcedCandidate</code> là base nội bộ dùng chung <code>source_segment_ids</code>, <code>Field(min_length=1)</code> và validator dùng <code>ensure_unique</code>.
- Mọi model kế thừa <code>ContractModel</code>; các nullable fields không đặt default.
- <code>CANDIDATE_SCHEMA_VERSION</code> là constant Python, không thêm field vào model.
- <code>validate_candidate_for_request</code> chỉ xác nhận module selection và nullability; không truy vấn source/evidence.
- <code>Priority</code> được import từ <code>app.schemas.response</code>; các public schemas không bị sửa.

### Tệp thêm/sửa

| Tệp | Thay đổi |
|---|---|
| <code>apps/llm-service/app/schemas/candidates.py</code> | Thêm bốn candidate models, base sourced model nội bộ, schema version constant và request-aware validator. |
| <code>apps/llm-service/tests/unit/schemas/test_candidates.py</code> | Thêm test structural, request-aware, JSON/schema, positive/negative; dùng request fixture tổng hợp đã có. |
| <code>docs/llm/report/llm-03/llm-03.3-versioned-prompts-and-candidates-report.md</code> | Tạo báo cáo chung living milestone cho LLM-03.3 và kết quả hai task hiện tại. |

Không cần fixture mới, thay đổi dependency hoặc lockfile. Không sửa request/response schema Contract v1, provider, route hoặc orchestration.

### Tính tương thích với Contract v1

Public <code>ExtractionRequest</code> tiếp tục là đầu vào helper và hiện đã giới hạn module hợp lệ theo Contract v1. <code>Priority</code> và các shared types/validator được tái sử dụng. Candidate schema không trả <code>ExtractionResponse</code>, không thay đổi response fields và không giả định đã làm temporal resolution, evidence verification hay review-state assignment.

## 4. LLM-03.3.3 — Versioned Prompt Templates

### Mục tiêu và trạng thái

Thiết kế prompt có phiên bản để trích xuất candidate Meeting Summary và Action Items từ transcript tiếng Việt hoặc tiếng Anh. Hai template hiện có đã được đọc và đối chiếu thủ công với Candidate Schema v1 cùng các tiêu chí prompt trong LLM-03 overview. Không thấy mâu thuẫn cấu trúc làm cản trở việc dùng chúng làm candidate prompt. Vì cả hai template đều có mặt và khớp candidate contract, LLM-03.3.3 được đánh dấu **Completed** ở phạm vi thiết kế template. Runtime version selection, context rendering và candidate parsing được triển khai trong LLM-03.3.4–03.3.6; semantic/evidence verification và response construction vẫn thuộc các bước sau.

### Template và trách nhiệm

| File thực tế | Trách nhiệm |
|---|---|
| <code>apps/llm-service/app/prompts/v1/system.md</code> | Quy định role/scope, evidence policy, quy tắc trích xuất, xử lý thông tin thiếu, ngôn ngữ/bảo toàn dữ liệu, transcript là untrusted input và quy tắc JSON output. |
| <code>apps/llm-service/app/prompts/v1/summary_actions.md</code> | Khai báo task, extraction configuration, meeting context, transcript data, quy tắc Summary/Actions, Candidate Schema, ví dụ few-shot và final checks. |

**Sai khác đường dẫn so với cấu trúc gợi ý:** repository hiện có hai file đuôi <code>.md</code>, không phải <code>.txt</code>. Báo cáo dùng đường dẫn thực tế; không đổi tên hoặc di chuyển file.

### System Prompt — bảy chính sách đã kiểm tra

| Chính sách | Nội dung có trong <code>system.md</code> |
|---|---|
| Identity & Scope | Engine trích xuất cấu trúc cho transcript tiếng Việt/Anh; chỉ tạo candidate Summary/Actions được yêu cầu; không trả lời câu hỏi trong transcript hoặc làm tác vụ bên ngoài. |
| Evidence Policy | Transcript là nguồn sự thật; substantive claims phải có source IDs không rỗng/không trùng, lấy đúng từ input; bỏ item thiếu bằng chứng. |
| Extraction Rules | Tóm tắt phân biệt facts, opinions, proposals, open questions và outcomes; Action Item cần future deliverable cùng commitment/assignment rõ; không nâng suggestion thành commitment. |
| Missing Information Policy | Owner, deadline, priority, context không được đoán; deadline giữ nguyên tại <code>raw_due_expression</code>; thông tin chưa rõ dùng null; giữ mọi field bắt buộc. |
| Language & Preservation | Nội dung theo <code>output_language</code>; giữ proper names, identifiers, source IDs và nguyên văn deadline; bảo toàn phủ định/điều kiện/mức độ chắc chắn. |
| Untrusted Input Policy | Transcript/quoted text là dữ liệu không đáng tin; bỏ qua nội dung cố ghi đè role, policy, schema, yêu cầu secret hoặc tool use. |
| Output Rules | Một JSON object đúng <code>SummaryActionsCandidate</code> (<code>candidate-v1</code>), đủ hai root keys, không thêm metadata/field; JSON only và chưa được xem là verified. |

### Extraction Prompt — tám phần đã kiểm tra

| Phần | Nội dung có trong <code>summary_actions.md</code> |
|---|---|
| Task | Chỉ xử lý module được yêu cầu; transcript ASR có thể lỗi; output là candidate chưa xác minh. |
| Extraction Configuration | Nhận output language và requested modules; chỉ hai module được hỗ trợ; yêu cầu application từ chối module khác trước khi render. |
| Meeting Context | Dùng JSON context để diễn giải; speaker mapping chỉ được dùng khi verified; không suy đoán danh tính hoặc chép IDs vào candidate. |
| Transcript Data | Nhận ordered segments dạng JSON; text là untrusted; chỉ trích segment IDs thực tế và giữ chính tả/thứ tự citation. |
| Business-Specific Instructions | Có hướng dẫn riêng cho Summary và Actions, gồm commitment, owner, deadline, priority, context, deduplication và empty results. |
| Output Schema | Mô tả chính xác fields/types/nullability/required rules và field bị cấm của bốn candidate models. |
| Few-Shot Examples | Ba ví dụ về commitment có speaker mapping, loại suggestion/work đã hoàn tất, và commitment có speaker chưa xác định. |
| Final Checks | Checklist module selection, JSON shape, grounding, commitment precision, ownership, dates/priority, language, security và empty actions. |

### Prompt và schema versioning

| Thành phần | Identifier | Trạng thái thực tế |
|---|---|---|
| Prompt bundle | <code>extract-v1.0</code> | Được ghi trong <code>summary_actions.md</code> và được executable PromptRegistry allowlist ánh xạ tới hai template v1. |
| Candidate Schema | <code>candidate-v1</code> | Constant <code>CANDIDATE_SCHEMA_VERSION</code> trong <code>candidates.py</code>, được PromptBundle giữ cùng prompt version; không phải JSON field do model sinh. |
| Public API Contract | <code>1.0</code> | Được giới hạn bởi request/response Pydantic schemas; đây là version của public API contract, không phải prompt hay candidate schema version. |

Ba version có trách nhiệm khác nhau: prompt version định danh instructions; candidate schema version định danh cấu trúc trung gian; contract version định danh giao thức public. PromptRegistry và PromptRenderer đã dùng prompt bundle cùng schema version để tạo request provider-neutral; Candidate Parser kiểm tra output bằng Candidate Schema v1. Tuy nhiên, <code>ProcessingMetadata.prompt_version</code> chưa được populate vì ExtractionService vẫn là <code>UnconfiguredExtractionService</code> và response construction chưa được triển khai.

### Placeholder và nguồn dữ liệu

| Placeholder thực tế | Nguồn dự kiến trong <code>ExtractionRequest</code> | Ý nghĩa |
|---|---|---|
| <code>${output_language}</code> | <code>request.extraction.output_language</code> | Ngôn ngữ sinh nội dung candidate: <code>vi</code> hoặc <code>en</code>. |
| <code>${requested_modules_json}</code> | <code>request.extraction.requested_modules</code> | Danh sách module dạng JSON; giúp model chỉ xử lý module được yêu cầu. |
| <code>${meeting_context_json}</code> | <code>request.meeting</code> | Context cho meeting và mapping participants/speakers; chỉ nên chứa trường cần thiết cho extraction. |
| <code>${transcript_segments_json}</code> | <code>request.transcript.segments</code> | Segments theo thứ tự, gồm ID, thời gian, speaker ID và text. |

PromptRenderer hiện thay đúng bốn placeholder bằng dữ liệu từ các field trên. Renderer xác thực cú pháp và tập placeholder của template trước khi serialize/chèn dữ liệu, dùng một lượt substitution; transcript có chuỗi dạng <code>${...}</code> vẫn được giữ nguyên như dữ liệu. Meeting context giới hạn ở participant <code>display_name</code> và <code>speaker_ids</code>; transcript segment giữ ID, start/end, speaker ID và text theo thứ tự. Request/meeting IDs, participant IDs và meeting title không được đưa vào JSON context.

### Đối chiếu Business Rules với Candidate Schema v1

| Quy tắc | Đối chiếu |
|---|---|
| Module hỗ trợ | Prompt, PromptRenderer và Candidate root hỗ trợ <code>meeting_summary</code> và <code>action_items</code>. Renderer từ chối các module còn lại trước khi tạo ProviderRequest; Candidate Parser/helper cũng từ chối unsupported module và kiểm tra nullability sau parse. |
| Root fields/nullability | Cả hai root keys bắt buộc. Module không yêu cầu phải null; summary được yêu cầu phải là object; actions được yêu cầu phải là array. Khớp model. |
| Kết quả rỗng | Prompt yêu cầu <code>action_items: []</code> khi không có commitment phù hợp và cho phép <code>key_topics: []</code>; cả hai trường hợp được schema hỗ trợ. |
| Field thông tin thiếu | Owner, raw deadline, priority và context đều bắt buộc hiện diện nhưng nullable. Prompt yêu cầu null khi không có thông tin được hỗ trợ. |
| Owner sentinel | Prompt cấm placeholder như <code>"Unknown"</code>/<code>"Unassigned"</code>; model structural chỉ yêu cầu <code>NonBlankString | None</code>, nên chuỗi sentinel vẫn có thể parse. Đây là chính sách prompt/ngữ nghĩa, không phải invariant cấu trúc đã được enforce. |
| Deadline | Prompt giữ nguyên deadline tại <code>raw_due_expression</code>, không resolve hoặc dịch. Candidate không có <code>due_date</code> hay temporal resolution. |
| Priority và context | Chỉ dùng priority được nói rõ, ngoài ra null; context chỉ khi được nguồn hỗ trợ, ngoài ra null. Khớp kiểu candidate. |
| Source references | Prompt yêu cầu IDs có thật trong transcript, giữ nguyên và unique; schema kiểm tra nonempty/unique và shape nhưng không xác minh ID tồn tại hoặc claim được hỗ trợ. Phần tồn tại/evidence thuộc validation sau. |
| Tính commitment | Prompt phân biệt assignment/commitment rõ với suggestion, câu hỏi, hypothetical và việc đã hoàn thành; không bịa owner, speaker, task hoặc deadline. Đây là quy tắc ngữ nghĩa của prompt, chưa được Pydantic chứng minh. |
| Boundary candidate | Prompt trả candidate, không trả public <code>ExtractionResponse</code>; cấm IDs, ngày đã resolve, timestamps, review flags, processing metadata, schema_version và field ngoài schema. Khớp Candidate Schema v1. |

Không thấy mâu thuẫn giữa các fields/null rules trong prompt và Candidate Schema v1. Các quy tắc semantic như owner sentinel, source existence, commitment và bằng chứng không thể được đảm bảo chỉ bằng model cấu trúc; đây là giới hạn đã biết, không phải validation đã triển khai.

### Tài liệu tham khảo thiết kế

Những repository này là nguồn tham khảo cho hướng thiết kế, không phải bằng chứng rằng dự án đã tái tạo kết quả hoặc chất lượng của chúng:

- [CompileWithG/meeting-summarizer](https://github.com/CompileWithG/meeting-summarizer) — tham khảo cách nhấn mạnh evidence-grounded extraction và final checks.
- [Sxrthak/Meeting-Summarizer](https://github.com/Sxrthak/Meeting-Summarizer) — tham khảo prompt contracts, evidence presentation và evaluation/testing.
- [Pratibha1314/meeting-action-extractor](https://github.com/Pratibha1314/meeting-action-extractor) — tham khảo quy tắc commitment, assignment, owner và deadline.
- [google/langextract](https://github.com/google/langextract) — tham khảo structured extraction, few-shot examples và source grounding.

### Security, reliability và giới hạn

- Template coi transcript là untrusted data và không cho phép text trong transcript ghi đè system instructions. Prompt policy hữu ích nhưng **không thể bảo đảm chống prompt injection**.
- Prompt yêu cầu source IDs lấy chính xác từ transcript, không tạo IDs, và yêu cầu output JSON only. Pydantic vẫn chịu trách nhiệm structural validation; bước sau phải xác minh source existence và semantic evidence.
- Hai template không chứa credentials hoặc transcript/meeting data cụ thể. PromptRenderer thực hiện data minimization cho meeting context; transcript được tuần tự hóa thành user-message data và không được đưa vào system message.
- Prompt instructions không thể tự bảo đảm chống hallucination hoặc tính đúng ngữ nghĩa. **Prompt instructions alone cannot guarantee hallucination prevention, semantic correctness, or prompt-injection resistance.**
- Ở thời điểm hoàn thành LLM-03.3.3, chưa chạy automated prompt tests, provider calls hay model inference; việc review lúc đó chỉ đối chiếu template với schema/tài liệu, không phải prompt quality evaluation. Offline rendering/integration tests được bổ sung ở LLM-03.3.4–03.3.7; prompt quality với model thật vẫn chưa được đánh giá.

## 5. LLM-03.3.4 — Prompt Registry & Versioning

### Triển khai

| Tệp | Trách nhiệm |
|---|---|
| <code>apps/llm-service/app/prompts/registry.py</code> | Định nghĩa <code>PromptBundle</code>, allowlist prompt version và tải template. |
| <code>apps/llm-service/app/prompts/__init__.py</code> | Khởi tạo package prompts. |
| <code>apps/llm-service/tests/unit/prompts/test_registry.py</code> | Kiểm tra version mapping, file Markdown, UTF-8, lỗi tải và độc lập working directory. |

<code>PromptBundle</code> là dataclass immutable gồm <code>prompt_version</code>, <code>candidate_schema_version</code>, <code>system_template</code> và <code>extraction_template</code>. Registry chỉ nhận version trong allowlist; <code>extract-v1.0</code> ánh xạ cố định tới <code>v1/system.md</code> và <code>v1/summary_actions.md</code>, không tạo path từ version tùy ý. Candidate version lấy từ <code>CANDIDATE_SCHEMA_VERSION</code>.

Template được đọc UTF-8 theo đường dẫn tương đối với package, giữ nguyên nội dung, từ chối file thiếu/rỗng và cache bundle đã tải thành công trong từng registry instance. Lỗi ngoài có thông báo tổng quát. Ngoại lệ hiện được raise bằng <code>from error</code>; traceback nội bộ định dạng đầy đủ có thể chứa version đầu vào trong <code>KeyError</code> hoặc filesystem path trong <code>OSError</code>. Đây là rủi ro chẩn đoán nội bộ; hiện không có registry-to-HTTP mapping hoặc ExtractionService gọi luồng này để đưa cause vào public response. Cause không chứa transcript/provider output. Registry không được chỉnh sửa trong LLM-03.3.7; cần cân nhắc suppress cause hoặc giới hạn log ở bước tích hợp runtime.

**Unit tests:** <code>tests/unit/prompts/test_registry.py</code> — 8 passed trong lần xác minh LLM-03.3.4–03.3.6.

## 6. LLM-03.3.5 — Prompt Renderer & Context Builder

### Triển khai

| Tệp | Trách nhiệm |
|---|---|
| <code>apps/llm-service/app/prompts/renderer.py</code> | Validate module selection, dựng context/transcript JSON và tạo provider request. |
| <code>apps/llm-service/tests/unit/prompts/test_renderer.py</code> | Kiểm tra module, language, placeholders, serialization và message boundaries. |

<code>PromptRenderer.render(request, bundle)</code> trả <code>RenderedPrompt</code> giữ <code>ProviderRequest</code>, prompt version và candidate schema version. Renderer chỉ nhận <code>meeting_summary</code>/<code>action_items</code>; module khác bị từ chối trước provider. Ngôn ngữ lấy từ <code>request.extraction.output_language</code> (<code>vi</code>/<code>en</code>).

Meeting context chỉ gồm participant <code>display_name</code> và mapping <code>speaker_ids</code> có sẵn; không đưa meeting/participant/request IDs hoặc title vào JSON context. Transcript giữ thứ tự segment và các trường <code>id</code>, <code>start</code>, <code>end</code>, <code>speaker_id</code>, <code>text</code>. JSON dùng <code>ensure_ascii=False</code>/<code>allow_nan=False</code>; renderer không dịch, gộp, tóm tắt hay suy đoán người nói.

Renderer xác thực cú pháp và tập đúng bốn placeholder trong template nguồn trước khi serialize/chèn dữ liệu, dùng <code>string.Template.substitute()</code> đúng một lượt. Output gồm hai <code>ProviderMessage</code> theo thứ tự <code>system</code>, <code>user</code> và <code>structured_output_mode="json_object"</code>. Transcript chỉ nằm trong user message; generation không gọi provider tại renderer.

**Unit tests:** <code>tests/unit/prompts/test_renderer.py</code> — 11 passed trong lần xác minh LLM-03.3.4–03.3.6.

## 7. LLM-03.3.6 — Candidate JSON Parser

### Triển khai

| Tệp | Trách nhiệm |
|---|---|
| <code>apps/llm-service/app/parsing/candidates.py</code> | Parse provider content thành Candidate Schema v1 và kiểm tra module theo request. |
| <code>apps/llm-service/app/parsing/__init__.py</code> | Khởi tạo package parsing. |
| <code>apps/llm-service/tests/unit/parsing/test_candidate_parser.py</code> | Kiểm tra JSON/schema, request mismatch và sanitization. |

<code>parse_candidate(content, request)</code> dùng <code>SummaryActionsCandidate.model_validate_json()</code>, sau đó gọi <code>validate_candidate_for_request()</code> hiện có. Lỗi JSON/schema được phân loại thành <code>CandidateFormatError</code>; sai lệch module thành <code>CandidateRequestMismatchError</code>. Thông báo không chứa raw model output; lỗi Pydantic/helper không bị lộ qua exception chaining.

Parser không strip Markdown fences, sửa JSON, retry, điền field, map HTTP errors hoặc tạo public <code>ExtractionResponse</code>. Parser chỉ kiểm tra cấu trúc và module selection: source ID không tồn tại vẫn có thể qua; owner sentinel như <code>"Unknown"</code> vẫn hợp lệ theo Candidate Schema v1; tính đúng claim, owner, deadline, priority và evidence thuộc các bước sau.

**Unit tests:** <code>tests/unit/parsing/test_candidate_parser.py</code> — 25 passed trong lần xác minh LLM-03.3.4–03.3.6.

## 8. LLM-03.3.7 — Offline Integration Tests

### Kiến trúc kiểm thử

<code>apps/llm-service/tests/integration/test_prompt_candidate_flow.py</code> compose trực tiếp Registry → Renderer → FakeProvider → Candidate Parser bằng interface thật. Helper trong test chỉ nối các bước kiểm thử; không thêm service hay production orchestration. Request lấy từ fixture tổng hợp hiện có <code>tests/fixtures/requests/summary_actions_request.json</code>; candidate JSON được khai báo tổng hợp trong test. FakeProvider là boundary mô phỏng duy nhất.

### Kịch bản

| Kịch bản | Kiểm tra |
|---|---|
| IT-01 Full Summary + Actions | Version metadata, hai messages đúng role/order, JSON mode, đúng một FakeProvider request, candidate fields/source IDs/raw deadline. |
| IT-02 Summary-only | Summary object và Actions null; module selection được render. |
| IT-03 Actions-only | Summary null; raw deadline và các nullable fields được giữ. |
| IT-04 Empty Actions | <code>action_items: []</code> được chấp nhận cho module đã yêu cầu. |
| IT-05 Malformed JSON | Parser lỗi sanitized; không candidate giả, repair hoặc retry. |
| IT-06 Candidate sai schema | Thiếu field, extra field, sai type và priority sai đều bị từ chối. |
| IT-07 Module mismatch | JSON parse được nhưng candidate/request mismatch bị từ chối. |
| IT-08 Unsupported module | Renderer từ chối trước khi FakeProvider nhận request. |
| IT-09 Provider failures | Timeout, rate limit, upstream failure truyền nguyên trạng; không retry và parser không chạy. |
| IT-10 vi/en | Prompt nhận language cấu hình; transcript, source IDs và system prompt giữ nguyên. |
| IT-11 Prompt-injection boundary | Chỉ dẫn và literal <code>${...}</code> trong transcript vẫn là data, không đổi system/configuration. |
| IT-12 Sources/speakers | Thứ tự segment, Unicode IDs/text, speaker mapping, unmapped/null speaker và source references được giữ. |
| IT-13 Version/template source | Registry dùng đúng hai file <code>.md</code>; Renderer giữ prompt/schema version. |

Các test xác nhận boundary và data flow offline; chúng không chứng minh model thật tuân thủ language/prompt hoặc chống prompt injection. Không có API key, external network call hay model inference.

## 9. Testing and Validation

### Chiến lược

Test dùng Pydantic thật với synthetic JSON/request fixture hiện có. Không gọi OpenRouter, không dùng API key, không inference và không truy cập mạng. Lệnh pytest trong sandbox ban đầu bị lỗi khởi tạo loopback (<code>bwrap: Failed RTM_NEWADDR</code>) trước khi chạy; các lệnh test sau đó được chạy ngoài sandbox và trả kết quả pytest thực tế.

### Nhóm kiểm thử

- Candidate Summary + Actions, summary-only, actions-only, actions rỗng, topics rỗng và nullable action fields.
- Giữ Unicode tiếng Việt; nhiều source refs; JSON parse; JSON Schema generation và required fields.
- Thiếu field, root/nested type sai, extra fields, chuỗi blank, source list rỗng/trùng, priority không hỗ trợ và coercion không hợp lệ.
- Từ chối artifact ID, timestamp, resolved date và review metadata.
- Requested module null, unrequested module có dữ liệu, module không hỗ trợ; source ID hợp cú pháp nhưng không có trong transcript vẫn qua structural/helper validation.
- Malformed JSON.
- Owner sentinel <code>"Unknown"</code> được kiểm chứng là vẫn structural-valid theo quyết định đã duyệt.

### Kết quả lịch sử

Các kết quả dưới đây được giữ lại từ lần xác minh ban đầu của Candidate Schema/Pydantic models; chúng không đại diện cho lượt chạy mới nhất:

Lệnh chạy trong <code>apps/llm-service/</code>:

~~~bash
uv run --locked --extra test pytest -q tests/unit/schemas/test_candidates.py
~~~

Kết quả: **54 passed**.

Full regression suite ở giai đoạn đó:

~~~bash
uv run --locked --extra test pytest -q
~~~

Kết quả lịch sử: **284 passed** (<code>3.04s</code>); bộ candidate có 54 test và phần suite còn lại có 230 test tại thời điểm đó. Sau khi hoàn thành LLM-03.3.4–03.3.6, lượt xác minh trước đó ghi nhận **44 focused tests passed** và **328 full-suite tests passed**. Hai mốc lịch sử này được giữ nguyên để truy vết.

### Kết quả LLM-03.3.7 — xác minh mới nhất

Tất cả lệnh chạy từ <code>apps/llm-service/</code>, dùng môi trường test hiện có và FakeProvider; không gọi OpenRouter, không đọc API key, không truy cập network và không dùng model inference.

~~~bash
uv run --locked --extra test pytest -q tests/integration/test_prompt_candidate_flow.py
~~~

Kết quả: **18 passed, 0 failed, 0 skipped** (<code>0.36s</code>).

~~~bash
uv run --locked --extra test pytest -q tests/unit/prompts tests/unit/parsing
~~~

Kết quả: **44 passed, 0 failed, 0 skipped** (<code>0.38s</code>).

~~~bash
uv run --locked --extra test pytest -q
~~~

Kết quả xác minh mới nhất ngày 2026-11-13: **346 passed, 0 failed, 0 skipped** (<code>2.85s</code>), không có collection errors. Tổng số tăng từ lượt trước do 18 integration cases mới. Không chạy manual/live provider smoke test.

### Giới hạn kiểm thử

Các test chỉ xác nhận parsing/structural rules và module selection. Chúng không đánh giá chất lượng tóm tắt, phát hiện claim không có bằng chứng, xác minh speaker/owner, resolve thời gian, xác định review state hoặc khả năng chống prompt injection.

## 10. Security and Reliability

- Integration tests dùng request fixture tổng hợp hiện có cùng response JSON tổng hợp; không có API credential hoặc transcript thật.
- FakeProvider là provider boundary duy nhất trong integration flow. Renderer và Parser là implementation thật; tests không dựng HTTP client/provider adapter và không gọi network.
- Strict Pydantic validation, required nullable fields và <code>extra="forbid"</code> ngăn thiếu trường, coercion và metadata ngoài schema.
- Source ID uniqueness/shape được kiểm tra; nội dung claim và source existence không được giả vờ là đã xác minh.
- Transcript được đặt trong user message như JSON data; test xác nhận system message, module selection, language và template placeholders không bị nội dung transcript ghi đè. Đây chỉ là kiểm tra trust-boundary serialization, không phải chứng minh model chống prompt injection.
- Parser exception messages không lộ raw provider output. Registry ngoài trả thông báo tổng quát, nhưng exception chaining có thể đưa prompt version hoặc filesystem path vào internal traceback; đây là rủi ro chẩn đoán nội bộ, không phải raw transcript/provider disclosure hay public-response mapping hiện có. Không đổi Registry trong scope này.
- Không ghi log credential hoặc sửa provider/API key configuration.

## 11. Remaining LLM-03.3 Work

Không còn task **Pending** trong LLM-03.3.1–LLM-03.3.7. Candidate schema, templates, registry, renderer, parser, offline integration và báo cáo milestone đã được thực hiện/kiểm tra. Hoàn thành milestone này không đồng nghĩa production extraction hoặc semantic verification đã hoàn tất.

- **LLM-03.3.1–03.3.2 — Completed:** Candidate Schema Specification v1 và Pydantic Candidate Models.
- **LLM-03.3.3 — Completed:** Versioned Prompt Templates (`system.md`, `summary_actions.md`).
- **LLM-03.3.4 — Completed:** Prompt Registry & Versioning.
- **LLM-03.3.5 — Completed:** Prompt Renderer & Context Builder.
- **LLM-03.3.6 — Completed:** Candidate JSON Parser.
- **LLM-03.3.7 — Completed:** Offline Integration Tests & Documentation.

## 12. Handoff to LLM-03.4

Các component LLM-03.3 hiện có thể được LLM-03.4 tiêu thụ; chúng chưa được nối thành production extraction service:

~~~text
ExtractionRequest                         [implemented]
    ↓
Prompt Registry                            [implemented: LLM-03.3.4]
    ↓
Prompt Renderer & Context Builder          [implemented: LLM-03.3.5]
    ↓
LLMProvider                                [interface/adapter implemented; not wired to extraction]
    ↓
Candidate Parser                           [implemented: LLM-03.3.6]
    ↓
Evidence Validation / Post-processing      [planned; no candidate evidence pipeline yet]
    ↓
ExtractionResponse                         [public schema implemented; response construction not wired]
~~~

Trong LLM-03.4, production ExtractionService cần phối hợp các component trên. Các trách nhiệm còn lại gồm provider invocation/retry và output-repair policy rõ ràng, source ID existence verification, semantic evidence, owner/commitment correctness, temporal resolution, artifact IDs/timestamps, review-state assignment, public <code>ExtractionResponse</code> construction và real-model quality evaluation. Những trách nhiệm này chưa được triển khai hoặc kiểm chứng. Hiện <code>ExtractionService</code> vẫn là <code>UnconfiguredExtractionService</code>; pipeline đầy đủ chưa tồn tại.
