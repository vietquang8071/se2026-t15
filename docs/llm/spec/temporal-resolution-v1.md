# Đặc tả Temporal Resolution v1

> **Trạng thái:** thiết kế LLM-04.1; chỉ tài liệu, chưa triển khai resolver.
> **Phạm vi contract:** Contract v1, contract_version 1.0.
> **Tài liệu liên quan:** [LLM Service contract](../llm-service-contract.md), [LLM Service architecture](../llm-service-architecture.md).

## 5.1 Overview and Scope

LLM-04 bổ sung một **TemporalResolver** deterministic để chuyển biểu thức ngày tiếng Việt/tiếng Anh thành ngày lịch hoặc khoảng ngày, theo **meeting.anchor_date** và timezone của cuộc họp. Mục tiêu LLM-04.1 là chốt chính sách và test trước khi viết resolver; deliverable của milestone này chỉ là tài liệu.

LLM-03 hiện đã có Contract v1, pipeline extraction, source validation, semantic evidence verification và **TemporalReviewProcessor**. Model **TemporalResolution** đã validate ba trạng thái đầu ra. Runtime chưa có **TemporalResolver**: safeguard hiện chỉ parse được **raw_due_expression** khi cả chuỗi đúng dạng ISO **YYYY-MM-DD**; natural language và cụm có từ bao quanh còn unresolved. Vì vậy mô tả temporal trong architecture/contract là thiết kế, không phải bằng chứng rằng runtime đã hỗ trợ.

Ranh giới trách nhiệm:

1. **LLM extraction** đề xuất artifact, cụm thời gian nguyên văn, ngữ cảnh task/event và segment IDs; không tính ngày cuối.
2. **Source validation** xác nhận ID tồn tại trong đúng transcript revision/request.
3. **Semantic evidence verification** đánh giá claim SUPPORTED, UNSUPPORTED hoặc UNCERTAIN. ID hợp lệ chỉ chứng minh traceability, không chứng minh câu chữ hỗ trợ deadline.
4. **Deterministic calendar resolution** nhận claim đã được chấp nhận và tính ngày/range bằng Python standard library. Resolver không tạo Action Item, không quyết định task có được cam kết hay không, và không thay thế evidence verifier.
5. **Response validation** giữ output trong các invariant Contract v1 và xác nhận review state nhất quán.

LLM-05 sẽ mở rộng Follow-up và Timeline; các module đó phải dùng cùng policy, anchor date và resolver để một expression không cho kết quả khác nhau giữa modules. Hiện Contract v1 mô tả các field temporal cho những module này, nhưng runtime hiện tại chưa triển khai đủ sáu modules.

**Ngoài phạm vi:** thay schema/API công khai; sửa prompt, dataset/gold, benchmark hoặc runtime; quyết định policy UI/persistence; giải quyết time-of-day, duration, holidays, locale calendars hay fuzzy date parsing; triển khai LLM-04.2/04.3/04.4/04.5. Không gọi provider trong LLM-04.1.

### Trạng thái bằng chứng trong tài liệu

- **Contract v1:** đã được ghi trong docs/llm/llm-service-contract.md; chỗ nào contract ghi “proposed” hoặc “cần nhóm chốt” vẫn là chính sách cần phê duyệt, không tự trở thành yêu cầu đã duyệt.
- **Đề xuất LLM-04.1:** quyết định cụ thể mới để LLM-04.2 không phải tự chọn. Cần nhóm chấp thuận trước khi coi là policy sản phẩm.
- **Runtime hiện tại:** chỉ các hành vi được nêu rõ ở mục này và được source/test thực thi mới được xem là đã triển khai.

## 5.2 Input Contract

Resolver là API nội bộ, không thêm public request fields. Đề xuất đầu vào tương đương:

| Giá trị | Kiểu/nguồn | Ràng buộc |
|---|---|---|
| **raw_expression** | str; từ candidate đã validate | Bắt buộc, không rỗng. Giữ nguyên đúng giá trị candidate; không ghi đè bằng chuỗi đã chuẩn hóa. Nếu không có expression, caller không gọi resolver và giữ field resolution ở parent là null. |
| **anchor_date** | datetime.date; chuyển từ meeting.anchor_date: IsoDate đã validate | Bắt buộc; là ngày dân sự địa phương của cuộc họp. Không dùng date.today(), server clock, container clock hoặc provider date. |
| **timezone** | IANA str/ZoneInfo; từ meeting.timezone | Bắt buộc, đã validate ở request bằng ZoneInfo. Không chấp nhận offset mơ hồ như UTC+7. |
| **source_segment_ids** | Sequence[str]; từ temporal claim sau source validation | Tối thiểu một ID, không trùng, thuộc đúng request/transcript revision. Lấy IDs của claim thời gian, không tự gán IDs từ toàn bộ artifact. |
| **verified_context** | tùy chọn, internal-only, chỉ dữ liệu temporal đã được source- và evidence-verified | Chỉ dùng khi thiếu thành phần ngày (ví dụ “ngày 12”) và có claim cùng task/event chỉ rõ duy nhất tháng/năm. Context phải có IDs riêng để trace; nếu context tạo nên kết quả, đưa các IDs hỗ trợ đó vào temporal source_segment_ids nếu chúng thuộc artifact. Không thêm field này vào public Contract v1. |

Caller phải gọi resolver **sau** source validation và semantic verification. Chỉ SUPPORTED temporal claim được chuyển sang bước tính ngày. Với UNSUPPORTED, caller xóa/loại claim temporal theo safeguard; với UNCERTAIN, giữ nguyên expression để review và không chấp nhận một exact date dù raw text có substring parse được. Resolver có thể nhận verified_context nhưng không tự đánh giá verdict hoặc tìm claim trong toàn transcript.

Matching được thực hiện trên bản sao tạm thời của raw_expression (ví dụ Unicode NFC, case-fold, trim/collapse whitespace). Không bỏ dấu tiếng Việt nếu điều đó làm tăng va chạm từ vựng. Bản sao này chỉ phục vụ matching; artifact giữ nguyên raw_expression, kể cả tiền tố như “vào”.

## 5.3 Output Contract

Output là model hiện có app.schemas.temporal.TemporalResolution; không thêm public field:

| Field | Quy tắc |
|---|---|
| status | Một trong exact_date, date_range, unresolved. |
| resolved_date | Chỉ có với exact_date, theo YYYY-MM-DD. |
| start_date, end_date | Inclusive endpoints, chỉ có với date_range. |
| needs_review | false chỉ với exact_date; true với date_range và unresolved. |
| source_segment_ids | Danh sách không rỗng, unique, thuộc temporal evidence đã validate. |

Invariant đã được schema Pydantic kiểm tra:

- **exact_date:** một ngày lịch hợp lệ; resolved_date có giá trị; range fields null; temporal needs_review=false.
- **date_range:** resolved_date=null; cả hai endpoint có giá trị và start_date <= end_date; endpoints bao gồm cả hai ngày; temporal needs_review=true.
- **unresolved:** mọi date field null; temporal needs_review=true.
- **Không có temporal expression:** field resolution ở artifact cha là null; không tạo object unresolved để thay cho “không có deadline”.

Temporal needs_review không phải overall artifact needs_review. Ví dụ deadline exact có temporal flag false nhưng Action Item vẫn cần review nếu owner chưa được xác nhận. Ngược lại, range/unresolved yêu cầu review ngay cả khi owner đã được xác nhận.

## 5.4 Temporal Resolution Rules v1

Trong từng rule, **Contract** nghĩa là hành vi đã được mô tả trong Contract v1; **Đề xuất** là policy mới/chưa được xác nhận; **Runtime thiếu** có nghĩa code hiện tại chưa thực thi rule. Contract §6.2 và architecture §5.3 vẫn ghi một số policy là đề xuất hoặc cần chốt.

### R01 — Ngày ISO độc lập

- **Loại/ví dụ:** ngày đầy đủ 2026-12-15.
- **Matching:** chấp nhận duy nhất token canonical YYYY-MM-DD; parse toàn token bằng date.fromisoformat, sau đó kiểm tra round-trip isoformat(). Không nhận format slash hoặc datetime như ngày-only.
- **Context cần:** expression có đủ năm/tháng/ngày; temporal claim SUPPORTED và có source IDs hợp lệ.
- **Tính lịch:** đây là ngày tuyệt đối; không dịch theo anchor_date hoặc timezone.
- **Output/review:** ngày hợp lệ → exact_date, không cần temporal review. Ngày không hợp lệ → R10.
- **Biên:** 2024-02-29 hợp lệ; 2026-02-29 không hợp lệ. Có hai ISO dates thì áp R11, không tùy ý chọn một.
- **Nguồn/trạng thái:** Contract v1 §6.2; runtime hiện tại hỗ trợ đúng dạng raw expression ISO canonical và verdict SUPPORTED (test_unambiguous_iso_deadline_resolves_deterministically).

### R02 — ISO date có từ dẫn ngữ cảnh

- **Loại/ví dụ:** “vào 2026-12-15”, “hạn 2026-12-15”, “by 2026-12-15”, “due on 2026-12-15”.
- **Matching:** **Đề xuất** nhận đúng một ISO token trong raw expression có wrapper trung tính/dẫn deadline; wrapper được bảo toàn. Không dùng regex quét transcript rồi lấy bất kỳ ngày nào. Nếu có nhiều ngày, phủ định, câu hỏi/proposal hoặc quan hệ giữa token và target không rõ, dùng R11/R13/R14.
- **Context cần:** một token date, temporal claim được verifier xác nhận là deadline/date của đúng task/event; segment IDs chứng minh ngữ nghĩa.
- **Tính lịch:** parse token tuyệt đối theo R01.
- **Output/review:** token hợp lệ và được hỗ trợ → exact_date, needs_review=false; unsupported → không resolve, xử lý theo R13/evidence safeguard.
- **Biên:** giữ nguyên raw_expression="vào 2026-12-15"; không chấp nhận ngày trong câu được trích dẫn hoặc câu về một task khác.
- **Nguồn/trạng thái:** mở rộng đề xuất cho R01; case-008 là regression bắt buộc; runtime thiếu vì hiện gọi date.fromisoformat(raw_due) trên cả chuỗi.

### R03 — Ngày tự nhiên tiếng Việt đầy đủ

- **Loại/ví dụ:** “ngày 15 tháng 12 năm 2026”, “15 tháng 12 năm 2026”.
- **Matching:** **Đề xuất triển khai** grammar ngày đủ thành phần, có tên/đơn vị ngày-tháng-năm rõ ràng; không đoán thứ tự từ số slash, không lấy các số riêng lẻ.
- **Context cần:** ngày/tháng/năm tường minh và claim SUPPORTED.
- **Tính lịch:** tạo date(year, month, day); ValueError đi R10.
- **Output/review:** ngày hợp lệ → exact_date; ngày không hợp lệ → unresolved + temporal_unresolved.
- **Biên:** không bổ sung năm từ server clock; không biến ngày thiếu năm thành exact theo anchor trừ R09 và context đã verify.
- **Nguồn/trạng thái:** dạng ngày đầy đủ được nêu trong Contract v1 §6.2; grammar cụ thể và resolver còn thiếu trong runtime. Test hiện có dùng transcript natural language nhưng candidate đã canonical ISO, nên chỉ bao phủ từng phần.

### R04 — Ngày tự nhiên tiếng Anh đầy đủ

- **Loại/ví dụ:** “December 15, 2026”, “15 December 2026”.
- **Matching:** chỉ grammar rõ tháng bằng chữ và đủ năm; 03/04/2026 không thuộc rule này.
- **Context cần:** ngày đầy đủ và temporal claim SUPPORTED.
- **Tính lịch:** parse tháng có tên theo bảng cố định locale-independent rồi tạo date; không dùng locale môi trường.
- **Output/review:** ngày hợp lệ → exact_date; ngày không hợp lệ → R10.
- **Biên:** month name không khớp, năm thiếu, hoặc cả hai cách đọc khả dĩ → unresolved, không chọn locale của server.
- **Nguồn/trạng thái:** Contract v1 §6.2; implementation/parsing tự nhiên còn thiếu. Existing test chỉ xác nhận pipeline nhận canonical candidate được verifier hỗ trợ.

### R05 — Ngày trong tuần

- **Loại/ví dụ:** “thứ Sáu này”, “this Friday”, “next Tuesday”, “thứ Sáu tuần sau”.
- **Matching:** **Đề xuất** chỉ hỗ trợ tên weekday có deictic rõ. “weekday này”/“this weekday” = lần xuất hiện đầu tiên cùng hoặc sau anchor; nếu anchor chính là weekday đó thì cùng ngày. “weekday tuần sau”/“next weekday” = weekday đó trong ISO week kế tiếp. Weekday không có mốc như “thứ Sáu”, và “thứ Sáu tới” chưa được quy định rõ, trả unresolved cho tới khi policy được chốt.
- **Context cần:** anchor date và temporal claim SUPPORTED; expression phải xác định đúng một weekday.
- **Tính lịch:** date.weekday() (Monday=0) và số ngày chênh lệch trên date, không dùng timezone duration.
- **Output/review:** một ngày → exact_date, không cần temporal review.
- **Biên:** anchor trùng weekday trả chính anchor; target có thể rollover tháng/năm. “Thứ Sáu hoặc thứ Hai” không phải một weekday duy nhất, dùng R11.
- **Nguồn/trạng thái:** Contract v1 §6.2 xác nhận “Thứ Sáu này” và ví dụ 2026-10-05 → 2026-10-09; cách hiểu next <weekday> là đề xuất; runtime hiện chưa resolve weekday.

### R06 — Tuần hiện tại

- **Loại/ví dụ:** “tuần này”, “this week”.
- **Matching:** phrase phải chỉ rõ “tuần này”; không suy luận từ “trong tuần” nếu không có mốc.
- **Context cần:** anchor date và claim được hỗ trợ.
- **Tính lịch:** ISO week chứa anchor, từ Monday đến Sunday inclusive.
- **Output/review:** date_range, temporal needs_review=true, reason date_range_needs_confirmation.
- **Biên:** tuần có thể chạy qua tháng/năm; giữ cả hai endpoint, không gán ngày đại diện.
- **Nguồn/trạng thái:** Contract v1 §6.2; runtime chưa tạo range.

### R07 — Tuần kế tiếp

- **Loại/ví dụ:** “tuần sau”, “next week”.
- **Matching:** phrase phải định danh tuần kế tiếp, không phải “trong vài ngày tới”.
- **Context cần:** anchor date và claim được hỗ trợ.
- **Tính lịch:** ISO week ngay sau tuần chứa anchor, Monday–Sunday inclusive.
- **Output/review:** date_range, temporal review true, reason date_range_needs_confirmation; không ép thành Monday deadline.
- **Biên:** qua tháng/năm theo ISO week; ví dụ anchor 2026-10-05 → 2026-10-12 đến 2026-10-18.
- **Nguồn/trạng thái:** Contract v1 §6.2 mô tả kết quả; architecture/contract ghi cần nhóm xác nhận ISO Monday–Sunday. LLM-04.1 đề xuất giữ quy tắc ISO để có kết quả deterministic; chờ xác nhận. Runtime hiện unresolved với “tuần sau”.

### R08 — Cuối tháng và cuối tháng sau

- **Loại/ví dụ:** “cuối tháng”, “end of this month”, “cuối tháng sau”, “end of next month”.
- **Matching:** “cuối tháng” phải liên hệ được với tháng anchor; “tháng sau” phải nói rõ tương đối với tháng họp. “cuối tuần” không thuộc rule.
- **Context cần:** anchor date và claim được hỗ trợ.
- **Tính lịch:** ngày cuối tháng bằng calendar.monthrange(year, month)[1]; đổi tháng/năm bằng arithmetic tháng, không dùng số ngày cố định.
- **Output/review:** policy này diễn giải “cuối” thành một ngày cuối tháng và trả exact_date, temporal review false. Đây là độ chính xác được proposal đặt ra, không suy ra rằng mọi câu đời thực đều rõ.
- **Biên:** tháng 2 nhuận/không nhuận; tháng 12 sang tháng 1; nếu transcript chỉ xác định “cuối tuần/tháng gần cuối” hoặc mốc khoảng thì R11/unresolved.
- **Nguồn/trạng thái:** Contract v1 có ví dụ cuối tháng → 2026-10-31 nhưng tự đánh dấu policy đề xuất; “cuối tháng sau” là đề xuất trong architecture. Cần nhóm phê duyệt trước khi coi là rule sản phẩm. Runtime chưa hỗ trợ.

### R09 — Thiếu thành phần ngày

- **Loại/ví dụ:** “ngày 12”, “15 tháng 12”.
- **Matching:** không tự lấy tháng/năm đang thiếu từ anchor_date. Chỉ hoàn thiện khi verified_context có đúng một tháng/năm gắn ngữ nghĩa với cùng task/event.
- **Context cần:** unique, SUPPORTED temporal context, source IDs cho expression lẫn thông tin bổ sung; nếu không có thì không đủ.
- **Tính lịch:** sau khi đủ ngày/tháng/năm, kiểm tra bằng date(year, month, day) như R03.
- **Output/review:** context duy nhất → exact date; context thiếu/nhiều khả năng → unresolved, review true, temporal_unresolved.
- **Biên:** không lấy ngày từ artifact khác, topic khác hoặc unrelated segment; nếu context mâu thuẫn, R11.
- **Nguồn/trạng thái:** Contract v1 §6.2 cho phép resolve “Ngày 12” chỉ khi transcript xác định duy nhất tháng/năm; runtime chưa có context resolver.

### R10 — Ngày lịch không hợp lệ

- **Loại/ví dụ:** “30/02/2026”, “2026-02-29”.
- **Matching:** parse theo grammar của rule tương ứng rồi xác thực calendar; không “sửa” thành ngày gần nhất.
- **Context cần:** không cần thêm context để kết luận date đã đủ thành phần nhưng invalid.
- **Tính lịch:** constructor datetime.date/date.fromisoformat; mọi ngày không tồn tại là parse failure.
- **Output/review:** unresolved, các date fields null, review true, reason temporal_unresolved; request có anchor_date không hợp lệ vẫn bị request schema từ chối trước resolver.
- **Biên:** 2024-02-29 hợp lệ; không nhuận 2026-02-29 invalid.
- **Nguồn/trạng thái:** Contract v1 §6.2 cấm tự sửa và yêu cầu unresolved hoặc từ chối invalid generated output; schema đã validate ngày output, nhưng resolver rule còn thiếu.

### R11 — Mơ hồ, nhiều lựa chọn hoặc mâu thuẫn

- **Loại/ví dụ:** “thứ Sáu hoặc thứ Hai”, “03/04/2026”, hai deadline khác nhau không có correction rõ.
- **Matching:** không chọn substring đầu/cuối, không biến các ngày không liên tiếp thành date range; date_range chỉ dành cho một khoảng liên tục được nói ra.
- **Context cần:** cần claim/source evidence để phân biệt cách đọc; nếu evidence không giải được mâu thuẫn, giữ nguyên uncertainty.
- **Tính lịch:** không tính một ngày đại diện.
- **Output/review:** unresolved, temporal review true + temporal_unresolved; nếu còn publish artifact có mâu thuẫn đã xác nhận thì thêm conflicting_statements.
- **Biên:** “cuối tuần” chưa có định nghĩa ngày/khoảng; unresolved cho đến khi nhóm duyệt policy. Hai dates khác task không phải mâu thuẫn nếu target được tách đúng.
- **Nguồn/trạng thái:** Contract v1 §6.2 yêu cầu unresolved khi mơ hồ/mâu thuẫn; ngưỡng cụ thể để xem “cuối tuần” là policy đề xuất chưa được phê duyệt.

### R12 — Điều kiện và dependency trigger

- **Loại/ví dụ:** “nếu dữ liệu về trước 2026-12-15 thì gửi bản nháp”, “sau khi có dữ liệu”.
- **Matching:** resolver chỉ tính ngày có trong phrase; trigger không phải ngày. Resolver không kết luận điều kiện đã xảy ra và không biến conditional plan thành commitment.
- **Context cần:** evidence phải hỗ trợ cả target và modality/condition. Claim UNCERTAIN không được đưa vào nhánh exact-date.
- **Tính lịch:** date được nói rõ chỉ có thể tính sau khi semantic gate xác nhận expression liên quan đúng target; điều kiện vẫn được giữ riêng trong artifact/context.
- **Output/review:** pure dependency trigger trong Follow-up được giữ làm target_trigger_or_date, không tạo date resolution nếu không có date phrase. Nếu trigger bị đưa vào field deadline như deadline date, unresolved + temporal_unresolved. Conditional commitment UNCERTAIN không được exact-resolve.
- **Biên:** date chỉ là điều kiện (“nếu x trước ngày …”) không mặc nhiên là hạn hoàn thành task; không sinh Action Item từ ngày đó.
- **Nguồn/trạng thái:** phân biệt Action Item/Follow-up ở Product Description; quy tắc gate này là đề xuất mới. Runtime không có resolver cho dependency.

### R13 — Phủ định và ngày bị bác bỏ

- **Loại/ví dụ:** “không cần trước 2026-12-15”, “không phải ngày 15”.
- **Matching:** không resolve chỉ vì có ISO substring; phải xác định expression là deadline được khẳng định, không phải ngày bị phủ định/nhắc để loại trừ.
- **Context cần:** semantic verdict và source evidence về scope phủ định.
- **Tính lịch:** không tính ngày phủ định thành deadline.
- **Output/review:** nếu không có deadline được khẳng định, parent resolution null; nếu candidate gán ngày bị verifier UNSUPPORTED, xóa raw deadline/date và gắn evidence_unverified. Nếu scope phủ định chưa rõ và claim hữu ích còn lại, unresolved/review.
- **Biên:** “không muộn hơn ngày X” là deadline được khẳng định (có thể exact); “không phải X mà Y” là correction theo R14.
- **Nguồn/trạng thái:** evidence safety Contract v1 §7 và safeguard hiện tại loại unsupported temporal claim; phân loại phủ định chi tiết là đề xuất.

### R14 — Correction và superseded deadline

- **Loại/ví dụ:** “Hạn cũ 2026-12-15; chốt lại chuyển sang 2026-12-20”.
- **Matching:** chọn ngày mới chỉ khi correction nói rõ cùng target và evidence verifier xác nhận phiên bản mới; giữ raw expression đúng candidate/correction. Không suy luận “câu nói muộn hơn luôn thắng”.
- **Context cần:** cùng task/event, thứ tự/correction rõ và status SUPPORTED cho final claim.
- **Tính lịch:** resolve final supported expression bằng rule phù hợp; date cũ không còn là due date active.
- **Output/review:** correction rõ + verified → resolve ngày cuối; unresolved conflict → R11, review true. Không thay candidate unsupported bằng ngày khác chỉ vì parser tìm thấy substring.
- **Biên:** hai artifact/task khác nhau có thể giữ hai deadline; correction không xác định target thì unresolved.
- **Nguồn/trạng thái:** test safeguard hiện có kiểm tra supported/uncertain/unsupported correction ở dạng candidate ISO; precedence semantics là policy đề xuất. Resolver tự nó không thực hiện verification.

### R15 — Không có temporal expression

- **Loại/ví dụ:** raw_due_expression=null.
- **Matching:** không cố đoán deadline từ ngày họp, task text hoặc server date.
- **Context cần:** không cần.
- **Tính lịch:** không chạy resolver.
- **Output/review:** field resolution ở parent null; không tạo unresolved, không thêm temporal_unresolved chỉ vì thiếu deadline. Parent vẫn có thể cần review vì owner/evidence khác.
- **Biên:** khác với expression có mặt nhưng mơ hồ (R11), hoặc non-date trigger đưa nhầm vào due field (R12).
- **Nguồn/trạng thái:** Contract v1 §5.7 và safeguard runtime (test_missing_deadline_has_all_temporal_fields_null).

### R16 — Civil-date, timezone và calendar arithmetic

- **Loại/ví dụ:** mọi rule tương đối; request có anchor_date=2026-10-05, timezone=Asia/Ho_Chi_Minh.
- **Matching:** timezone dùng IANA key đã validate. Date-only expression không có giờ/phút.
- **Context cần:** anchor là ngày dân sự địa phương đã được caller cung cấp; không chuyển từ server timezone.
- **Tính lịch:** Python standard library datetime.date, date.weekday(), date.fromisocalendar(), calendar.monthrange() và date arithmetic. Không fixed month length, không thêm 24 giờ để thay calendar math.
- **Output/review:** trạng thái lấy từ R01–R15; timezone sai/anchor thiếu là lỗi request ở boundary, không phải unresolved expression.
- **Biên:** tuần ISO băng qua năm; tháng 12 sang tháng 1; leap day; không tạo giờ local hoặc DST policy khi output chỉ là date.
- **Nguồn/trạng thái:** Contract v1 §6.1 và architecture §5.2; request đã validate IsoDate và ZoneInfo; resolver calendar arithmetic còn thiếu.

## 5.5 Calendar Boundaries

- **Anchor đúng weekday:** R05 trả chính anchor_date nếu phrase là “weekday này”/“this weekday” và anchor đã trùng weekday; đây là quy tắc Contract v1 cho “Thứ Sáu này”.
- **Weekday sang tháng/năm mới:** tính trên date và weekday index; ví dụ 2026-12-31 + expression “thứ Sáu này” → 2027-01-01. Không có phép tính giờ.
- **ISO week qua năm:** ISO week có thể bắt đầu tháng 12 hoặc kết thúc tháng 1. R06/R07 luôn tính Monday–Sunday; dùng date.isocalendar()/date.fromisocalendar() hoặc phép date tương đương, không so sánh year number đơn lẻ.
- **Năm nhuận/29 tháng 2:** date(2024, 2, 29) hợp lệ; date(2026, 2, 29) không hợp lệ. Ngày cuối tháng lấy calendar.monthrange.
- **Cuối tháng:** lấy ngày cuối theo calendar của đúng tháng. December-to-January tăng year và month theo lịch; không giả định mọi tháng 30/31 ngày.
- **Invalid dates:** giữ expression, trả unresolved theo R10; không auto-correct 30/02, 31/04 hoặc 2026-02-29.
- **Date-only và timezone:** meeting.anchor_date đã là civil date tại meeting.timezone; v1 không biến date thành midnight datetime, không dịch ngày theo UTC/DST. Timezone vẫn cần hợp lệ theo request Contract v1, nhưng không dùng system timezone.

## 5.6 Ambiguity and Evidence Safety

| Tình huống | Xử lý v1 |
|---|---|
| “Ngày 12” thiếu tháng/năm | Chỉ resolve khi verified context của cùng target chỉ ra duy nhất tháng/năm; nếu không, R09 → unresolved. Anchor date không tự cung cấp phần thiếu. |
| “Thứ Sáu hoặc thứ Hai” | Hai lựa chọn không liên tục; unresolved, không lấy lựa chọn đầu hoặc gộp thành range. |
| “Cuối tuần” | Unresolved cho tới khi nhóm duyệt định nghĩa ngày cụ thể hay range. |
| Nhiều deadline mâu thuẫn | Correction rõ và được SUPPORTED xử lý theo R14; còn lại unresolved + review. |
| Explicit correction | Chỉ thay deadline cũ khi cùng target và correction cuối được verify; unsupported candidate không được thay thế bằng ngày tìm thấy ở segment khác. |
| Negated deadline | Không parse thành due date; unsupported candidate bị loại như hiện tại, hoặc unresolved nếu scope còn mơ hồ. |
| Conditional commitment | Không chuyển condition thành confirmed task. Nếu temporal claim UNCERTAIN, không trả exact_date; giữ review. |
| Dependency trigger (”sau khi có dữ liệu”) | Không phải calendar date. Follow-up giữ trigger raw; không tạo ngày. Nếu bị đặt trong due-date field, unresolved. |
| Unsupported evidence | UNSUPPORTED không thể tạo exact_date. Theo safeguard hiện tại, raw due bị clear, temporal resolution null và thêm evidence_unverified. |
| Uncertain evidence | UNCERTAIN không thể tạo exact_date; giữ raw, trả unresolved nếu raw temporal expression có mặt, thêm temporal_unresolved và claim_uncertain. |
| Source ID hợp lệ nhưng text không entail claim | Không đủ để resolve. Source validator xác nhận ID membership; evidence verifier phải xác nhận semantic support. |
| Parseable substring | Không đủ. Resolver chỉ nhận expression đã trích và verify; phải tôn trọng wrapper, target, phủ định, correction và quan hệ với task/event. |

Nếu deadline claim UNSUPPORTED, không dùng date parser để “cứu” claim; nếu deadline UNCERTAIN, một ISO token parse được vẫn không được xác nhận thành date. Calendar calculation không thêm Action Item, không đổi candidate task/owner, và không thay trạng thái commitment.

## 5.7 Review Reason Mapping

Temporal resolution gắn thêm reason vào review state của artifact cha; không thay thế các reason đã có:

| Trạng thái/điều kiện | Temporal model | Review reason |
|---|---|---|
| Exact date và evidence SUPPORTED | exact_date, temporal needs_review=false | Không thêm temporal reason. |
| Range | date_range, temporal needs_review=true | date_range_needs_confirmation. |
| Có expression nhưng không đủ/ambiguous/invalid | unresolved, temporal needs_review=true | temporal_unresolved. |
| Claim UNCERTAIN | Không exact; unresolved nếu claim còn được giữ | temporal_unresolved + claim_uncertain. |
| Claim UNSUPPORTED | Raw due cleared theo safeguard; resolution null | evidence_unverified, không giả làm unresolved temporal object. |
| Conflict còn được giữ để review | thường unresolved | temporal_unresolved + conflicting_statements. |
| Không có expression | Parent resolution null | Không thêm temporal reason. |

Overall needs_review bằng bool(review_reasons). Exact temporal result không xóa owner_unconfirmed, speaker_unmapped, evidence_unverified hoặc claim_uncertain từ các claim khác. TemporalResolution.needs_review chỉ mô tả độ chắc chắn của lịch, không phải toàn bộ Action Item.

**Thứ tự hiện có trong runtime (temporal_safeguards.py):** owner_unconfirmed, date_range_needs_confirmation, temporal_unresolved, evidence_unverified, conflicting_statements, speaker_unmapped, claim_uncertain. LLM-04.3 phải giữ thứ tự deterministic này khi ghép reason. Contract §5.8 có ví dụ date_range_needs_confirmation trước owner_unconfirmed, trái với thứ tự runtime; tài liệu này chọn thứ tự runtime làm compatibility baseline và ghi nhận cần đồng bộ ví dụ trong một task tài liệu riêng.

## 5.8 Architectural Integration Notes

### LLM-04.2 — Resolver

Architecture hiện dự kiến app/services/temporal_resolver.py. Phần triển khai nên là pure deterministic calendar logic, nhận input nội bộ ở §5.2, trả model Contract v1 và không gọi provider/system clock. Unit tests cho R01–R16 thuộc LLM-04.4. Không thay TemporalResolution public schema chỉ để đưa thêm parsing metadata.

### LLM-04.3 — Pipeline

Luồng hiện tại trong VerifiedExtractionService.extract là CandidateExtractionOrchestrator → ExtractionProjector → SourceValidator → EvidenceVerifier → TemporalReviewProcessor → ResponseBuilder.

- TemporalReviewProcessor là nơi phù hợp để điều phối status gate và gọi resolver sau evidence verifier; chỉ exact SUPPORTED claim mới được đưa qua resolver. ValidatedExtraction hiện mang action due dates, resolutions và review-reason tuples; giữ Contract v1 null/exact/range semantics.
- ResponseBuilder hiện gọi lại TemporalReviewProcessor().process(extraction.evidence_verified) và so sánh với ValidatedExtraction để chống state sai. Khi processor nhận resolver/configuration mới, factory và builder cần dùng cùng policy/instance (hoặc cấu hình immutable tương đương); nếu builder tạo processor mặc định khác, một kết quả hợp lệ có thể bị reject ở consistency check.
- ResponseBuilder tiếp tục map due_date chỉ từ exact result, giữ resolution object cho range/unresolved và validate response theo request. Các ID phải vẫn là source IDs từ claim, không phải IDs do resolver đoán.
- factory.py hiện tạo processor và builder riêng; chưa có resolver injection. Chốt wiring và dependency ownership trong LLM-04.3 trước khi sửa code.
- LLM-05 cần gọi cùng resolver cho Follow-up và Timeline. Cùng raw expression + anchor/timezone + evidence phải cùng kết quả bất kể module; module nào không yêu cầu hoặc không có expression vẫn giữ semantics null/empty theo Contract v1.

LLM-04.1 không thay TemporalReviewProcessor, ValidatedExtraction, VerifiedExtractionService, ResponseBuilder, factory hoặc schemas. Nếu implementation cần thay interface, đó là thay đổi LLM-04.2/04.3 và phải tiếp tục tương thích Contract v1.

## Case-008 Regression — LLM-03.7

Input thật ở apps/llm-service/evaluation/datasets/llm-03.7-evaluation/cases/case-008/ có anchor_date=2026-11-23, timezone Asia/Ho_Chi_Minh; SEG-0002 ghi “Tôi sẽ gửi checklist bảo mật vào 2026-12-15.” và SEG-0003 nhắc “ghi rõ hạn 2026-12-15.” Gold yêu cầu Action Item “Gửi checklist bảo mật”, raw_due_expression 2026-12-15, due_date 2026-12-15 và status exact_date, với deadline evidence ở hai segment đó. Report LLM-03.7.2 ghi prediction là raw_due_expression “vào 2026-12-15”, due_date null, unresolved; report xác nhận khác biệt chính là raw expression có thêm từ “vào” so với gold. Theo yêu cầu bảo toàn raw candidate, regression phải giữ “vào 2026-12-15” nếu đó là giá trị resolver nhận; LLM-04.5 cần đánh giá chênh lệch raw phrase riêng, không sửa gold tại đây.

Safeguard hiện gọi date.fromisoformat(raw_due) trên toàn chuỗi và chỉ chấp nhận round-trip khi parsed_date.isoformat() == raw_due. Chuỗi “vào 2026-12-15” không phải ISO token nguyên chuỗi nên thất bại dù có ngày hợp lệ bên trong. R02 đề xuất nhận wrapper trung tính có một ISO token, giữ nguyên raw candidate, rồi parse riêng token sau khi deadline claim được semantic verifier SUPPORTED.

Để tránh false positive, resolver không quét cả transcript tìm ngày bất kỳ, không lấy token từ unrelated task, ngày bị phủ định, câu hỏi/proposal, conditional hoặc claim unsupported/uncertain. Source IDs phải thuộc request; verifier phải hỗ trợ đúng claim và target. Gold/source IDs không thay thế semantic entailment. Không sửa input/gold/report hiện có.

**Regression LLM-04.4:** dùng case-008 làm extraction integration fixture; assert raw expression vẫn giữ “vào 2026-12-15”, exact due_date=2026-12-15, exact_date, temporal review false và deadline source IDs chỉ ra SEG-0002/SEG-0003 (hoặc tập con thật sự đủ chứng minh). Thêm unit parameter cho “vào 2026-12-15” và “by 2026-12-15”; counterpart unsupported/uncertain và expression có hai ngày phải không trả exact. Không chạy/ghi lại benchmark trong LLM-04.1.
