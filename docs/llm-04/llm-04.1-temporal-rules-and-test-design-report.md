# Báo cáo LLM-04.1 — Temporal Rules & Test Design

## A. Executive Summary

- **Mục tiêu:** xác định policy Temporal Resolution v1 và test matrix để LLM-04.2/04.3 có thể triển khai mà không tự quyết định cách diễn giải ngày.
- **Phạm vi:** documentation-only; không sửa runtime, tests, prompts, Contract v1, evaluation dataset/gold hay báo cáo LLM-03.
- **Trạng thái:** hoàn tất thiết kế LLM-04.1; chưa triển khai LLM-04.
- **Deliverables:** [Temporal Resolution Specification v1](../llm/spec/temporal-resolution-v1.md), [Temporal Test Matrix v1](../llm/spec/temporal-test-matrix-v1.md), và báo cáo này.

## B. Existing Repository State

- Product Description, Feature Overview và Roadmap mô tả temporal extraction/resolution nhưng một số ví dụ sai ngày hoặc cho LLM tính ngày; architecture và Contract v1 định nghĩa hướng deterministic. Runtime là nguồn sự thật cho phần đã chạy.
- Request schema tại apps/llm-service/app/schemas/request.py đã validate anchor_date dạng ISO, timezone bằng IANA ZoneInfo và transcript segment IDs.
- apps/llm-service/app/schemas/temporal.py có TemporalResolution ba trạng thái cùng invariant exact_date/date_range/unresolved, ordered range endpoints và source IDs non-empty/unique.
- apps/llm-service/app/services/temporal_safeguards.py hiện resolve raw_due_expression chỉ khi toàn bộ chuỗi là canonical YYYY-MM-DD và evidence verdict là SUPPORTED. UNCERTAIN giữ expression nhưng tạo unresolved với temporal_unresolved/claim_uncertain; UNSUPPORTED xóa raw due, không tạo resolution object và thêm evidence_unverified; deadline vắng mặt giữ mọi temporal fields null. Các natural-language test hiện dùng candidate đã canonical hóa, không chứng minh resolver parse raw natural language.
- Luồng apps/llm-service/app/services/verified_extraction.py là orchestration → projection → source validation → evidence verification → TemporalReviewProcessor → ResponseBuilder. apps/llm-service/app/services/response_builder.py tính lại safeguard state để xác nhận consistency. apps/llm-service/app/services/factory.py hiện tạo processor/builder riêng, chưa inject resolver.
- Contract v1 mô tả Follow-up/Timeline temporal fields, nhưng runtime hiện có mới hỗ trợ pipeline Summary/Action Items; TemporalResolver và calendar behavior tiếng Việt/tiếng Anh còn thiếu.
- Test hiện tại gồm temporal contract model/fixtures, safeguard unit tests và extraction integration dùng fake provider/verifier. Offline evaluation có metric raw expression, resolved date và status; report LLM-03.7.2 ghi case-008 unresolved. Evaluation không thay thế resolver unit test.

## C. Design Decisions

### Hành vi đã có trong Contract v1 hoặc runtime

- Chỉ meeting.anchor_date làm mốc; không dùng ngày hệ thống. meeting.timezone là IANA và anchor_date là civil date của meeting.
- TemporalResolution giữ ba trạng thái exact_date, date_range và unresolved; range endpoints inclusive; không có expression thì parent field null.
- “Thứ Sáu này” với anchor 2026-10-05 → 2026-10-09; “tuần sau” giữ range 2026-10-12..2026-10-18; ví dụ “cuối tháng” là 2026-10-31.
- Unsupported deadline không được exact-resolve; uncertain claim vẫn cần review; source ID membership không chứng minh semantic support.
- Runtime hiện chưa hỗ trợ relative dates/ranges, date có wrapper như “vào 2026-12-15”, hoặc natural date parsing.

### Policy đề xuất cần nhóm phê duyệt

- Chấp nhận ISO token đơn trong wrapper trung tính/dẫn deadline nhưng giữ nguyên raw_expression.
- Grammar ngày tự nhiên rõ ràng, weekday “this/next”, ISO week Monday–Sunday, ngày cuối tháng, và context duy nhất/đã verify cho date thiếu thành phần.
- “Cuối tuần”, slash dates mơ hồ, điều kiện/dependency-only, phủ định và mâu thuẫn chưa giải quyết đều không thành exact date.
- Correction chỉ supersede deadline cũ khi cùng target và final claim được SUPPORTED; không dùng thứ tự xuất hiện làm luật chọn ngày.
- Dùng standard library date/calendar arithmetic; resolver là pure deterministic helper, không phụ thuộc server clock.

### Ambiguity, boundaries, evidence và contract

- Đặc tả gán 16 stable rule IDs (R01–R16); từng rule phân biệt Contract v1, đề xuất và thiếu runtime.
- Chốt test boundaries: anchor đã đúng weekday, rollover tháng/năm, ISO week cross-year, leap/non-leap February, February 29, month-end và December-to-January.
- UNSUPPORTED bị loại, UNCERTAIN không thể exact-resolve, invalid source ID fail-closed, còn conditional date không được biến thành commitment.
- Không thêm public API field; raw expression giữ nguyên; verified_context nếu cần là internal-only và chỉ lấy từ evidence được xác minh.
- Ghi nhận review reason ordering trong runtime khác thứ tự ví dụ ở Contract v1: runtime đặt owner_unconfirmed trước date_range_needs_confirmation. Đề xuất giữ runtime order khi tích hợp, chưa sửa contract trong task này.

### Case-008

Input tại evaluation case-008 có anchor 2026-11-23; SEG-0002 nói “Tôi sẽ gửi checklist bảo mật vào 2026-12-15” và SEG-0003 xác nhận hạn 2026-12-15. Gold đặt due_date 2026-12-15/exact_date và raw expression 2026-12-15. LLM-03.7.2 report ghi prediction raw_due_expression “vào 2026-12-15”, due_date null/unresolved. Parser hiện parse toàn chuỗi bằng date.fromisoformat, nên từ dẫn “vào” làm lỗi dù ISO token hợp lệ.

Policy mới chỉ tách đúng một ISO token từ raw candidate đã được evidence verifier xác nhận; không quét transcript, không bỏ wrapper khỏi raw field, và không lấy ngày từ claim phủ định/conditional/unsupported hoặc task khác. Vì yêu cầu bảo toàn raw, regression phải assert candidate raw “vào 2026-12-15” được giữ nguyên và date vẫn exact. Chênh lệch raw string với gold cần được xử lý khi đánh giá LLM-04.5; không thay dataset/gold trong LLM-04.1.

## D. Test Design Summary

- **Tổng:** 43 cases, toàn bộ R01–R16 có ít nhất một case.
- **Phân loại:** 10 positive, 10 boundary, 11 negative/ambiguous, 12 evidence/integration.
- **Coverage hiện có theo từng assertion của matrix:** 10 covered, 14 partial, 19 missing. Các case “partial” không được tính là đã kiểm chứng policy mới.
- **Khoảng trống chính:** parser deterministic cho raw natural language/wrapper; weekday/week/month arithmetic; context completion; range và reason composition; condition/negation/conflict semantics; case-008 passing regression.
- **Placement:** resolver unit, TemporalReviewProcessor unit, contract/request validation, extraction integration dùng fake provider/verifier và offline evaluation sau LLM-04.4.

Chi tiết coverage từng case và tên test hiện có nằm trong [Temporal Test Matrix v1](../llm/spec/temporal-test-matrix-v1.md).

## E. Files Created or Modified

- **Created:** docs/llm/spec/temporal-resolution-v1.md — input/output contract, 16 rules, calendar/evidence/review policy, integration guidance và case-008.
- **Created:** docs/llm/spec/temporal-test-matrix-v1.md — 43 case có expected state, evidence, review reasons, test level và existing coverage.
- **Created:** docs/llm-04/llm-04.1-temporal-rules-and-test-design-report.md — báo cáo milestone bằng tiếng Việt.
- **Modified:** none.

## F. Verification

- Đã xác minh các file được yêu cầu tồn tại và đọc nội dung liên quan tại product docs, architecture/Contract v1, schemas, safeguards, pipeline, tests, fixtures, evaluation và LLM-03.7 reports.
- Đã đọc trực tiếp request/transcript/gold của case-008 và đoạn lỗi tương ứng trong report LLM-03.7.2.
- Đã kiểm tra Git working tree sạch trước khi tạo branch; fetch origin/develop thành công và branch mới bắt đầu từ base commit được ghi ở mục I.
- Đã rà soát tính nhất quán thủ công giữa rules, matrix, schema invariants, source/evidence gates và review reason order. Các check cho thấy 43 matrix rows, 16 rule IDs có test reference; các Markdown link targets được kiểm tra tồn tại.
- git diff --cached --check thành công trên đúng ba file staged (exit 0).
- **Runtime/application tests không chạy:** thay đổi chỉ là tài liệu và không được yêu cầu chạy tests/provider. Không có live provider request hoặc paid inference.

## G. Known Limitations and Open Decisions

- Nhóm cần xác nhận policy ISO-week Monday–Sunday, next-weekday semantics, “cuối tháng” là exact date hay range, và có hỗ trợ “cuối tuần” hay không.
- Cần xác nhận mức độ hỗ trợ natural-language grammar, slash-date locale và trường hợp context bổ sung tháng/năm.
- Negation, conditional commitment và correction cần phối hợp evidence verifier; parser một mình không thể xác nhận speech act hay target.
- Current LLM-03 runtime chỉ xử lý Action Items/summary và canonical raw ISO; Follow-up/Timeline chưa có end-to-end implementation.
- Contract example về review-reason order không khớp với implementation. Đặc tả ghi rõ mismatch; cần task tài liệu riêng để đồng bộ.
- Case-008 gold dùng raw expression ngắn hơn candidate hiện được report. Regression ưu tiên raw preservation và exact date; LLM-04.5 cần diễn giải riêng raw-expression metric mà không sửa gold tùy tiện.
- Tài liệu không chứng minh resolver đã hoạt động; cần LLM-04.2, .3 và .4 trước khi bật hành vi.

## H. Next Steps

1. **LLM-04.2 — Implement TemporalResolver:** thực hiện policy được nhóm chấp thuận và unit tests theo matrix.
2. **LLM-04.3 — Pipeline Integration:** nối evidence gate, TemporalReviewProcessor, ValidatedExtraction, factory và ResponseBuilder; giữ shared deterministic behavior.
3. **LLM-04.4 — Automated Tests:** bổ sung contract/safeguard/integration cases, gồm case-008 regression và các calendar boundaries.
4. **LLM-04.5 — Evaluation:** đánh giá offline date/status correctness và raw-expression behavior; giữ nguyên gold trừ khi có quyết định dataset riêng.

## I. Git Information

- **Repository:** vietquang8071/se2026-t15
- **Branch:** docs/llm-04-temporal-rules-and-test-design
- **Base branch/commit:** origin/develop — c58d999fc8d19b2e84b99ffe5d4df28b493c767a
- **Documentation commit hash:** sẽ được cung cấp trong final task response. Tài liệu không thể ghi hash của chính commit chứa nó mà vẫn giữ nguyên hash.
- **Push result:** sẽ được xác nhận sau khi push đúng branch; final task response là trạng thái authoritative.
- **Pull request/merge:** không tạo.
