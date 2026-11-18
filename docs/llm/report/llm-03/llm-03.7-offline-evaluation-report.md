# Báo cáo LLM-03.7 — Hạ tầng đánh giá offline và sửa lỗi P1

**Dự án:** SE2026-T15 — Vietnamese Meeting Minutes Assistant
**Thành phần:** `apps/llm-service`
**Milestone:** LLM-03.7 — Real Provider Integration & Cost Evaluation
**Phạm vi công việc lần này:** sửa bốn lỗi P1 của evaluation framework, kiểm thử offline và audit triển khai
**Branch được kiểm tra:** `feature/llm-03-provider-integration`
**Kết luận:** hạ tầng đánh giá offline đã được sửa và kiểm chứng; benchmark provider thật và các tiêu chí nghiệm thu LLM-03.7 vẫn chưa hoàn tất.

## 1. Tóm tắt điều hành

LLM-03.7 cần xác minh pipeline Summary/Action Items với provider thật, Contract v1, source evidence, chất lượng trích xuất, token usage và chi phí. Công việc này chỉ xử lý độ tin cậy của framework đánh giá offline: bốn lỗi P1 liên quan tới bỏ qua gold sai kiểu, crash khi Audio Transcript sai cấu trúc, chấm semantic grounding chưa đủ claim và review input lỗi nhưng CLI vẫn thành công hoặc crash.

Đã sửa dataset loader và Audio consistency validation; xây tập claim IDs từ response Contract v1 công khai; phân biệt review đầy đủ với review một phần; kiểm tra action, summary và semantic annotations trước khi chấm; và làm cho exit code của invalid review rõ ràng. Bộ test offline hiện có **94 test evaluation pass** và **684 test toàn LLM Service pass**. Dataset được xác thực đủ **16 case: 10 development, 6 holdout**. Lệnh dry-run development đã sinh `report.json` và `report.md` mà không có response đã lưu, vì vậy cả 10 case được đánh dấu `not_evaluated`.

Trong lần thực hiện này, không chạy inference với provider thật. Đây là kết quả dự kiến theo giới hạn an toàn, không phải bằng chứng chất lượng model. Báo cáo LLM-03.1 ghi nhận smoke test OpenRouter lịch sử cho kết nối và JSON mode; smoke test đó không thay thế yêu cầu LLM-03.7 là một extraction hoàn chỉnh được kiểm tra theo Contract v1. Do chưa có extraction provider thật, kết quả semantic, latency, token usage và chi phí benchmark, **không thể đánh dấu toàn bộ LLM-03.7 hoàn tất**.

## 2. Yêu cầu và phạm vi

Bảng dưới đây đối chiếu yêu cầu LLM-03.7 trong [tổng quan LLM-03](llm-03-overview.md) với mã nguồn và kết quả kiểm tra hiện tại. “Hoàn thành” trong bảng chỉ áp dụng cho hạ tầng offline tương ứng, không có nghĩa đã hoàn tất acceptance của benchmark provider thật.

| Yêu cầu | Triển khai thực tế | Bằng chứng và kết quả | Trạng thái |
|---|---|---|---|
| Bộ dữ liệu synthetic và split riêng | Loader đọc manifest, ba file mỗi case, case IDs, split, Audio v2, request Pydantic và gold labels. | Lệnh validate: 16 case hợp lệ, 10 development, 6 holdout; tổng 65 segment và 18 gold Action Item. | Hoàn thành — offline |
| Response tuân thủ Contract v1 | Dùng `ExtractionResponse`, `validate_response_for_request` và kiểm tra timestamp theo segment nguồn. Tách cờ JSON, schema, quan hệ request/response, completed và semantic availability. | Test validation bao phủ JSON lỗi, schema lỗi, request ID/meeting/revision/module mismatch, source IDs, ordering và timestamp. | Hoàn thành — offline |
| Action matching và precision/recall/F1 | Chuẩn hóa exact text mang tính xác định; match thủ công cho paraphrase; match một-một; trường hợp mơ hồ để review. | Test exact, đảo thứ tự, duplicate, FP/FN, paraphrase, ambiguous, match conflict và empty-action. | Hoàn thành — offline |
| Owner, deadline, priority | Chấm thuộc tính trên action đã match, có denominator riêng, correct-null và fabricated counts. | Test reassignment, unknown owner, deadline unresolved/ISO, priority explicit/null. | Hoàn thành — offline |
| Structural và semantic grounding tách biệt | Structural grounding được kiểm tra tự động. Semantic review ràng buộc vào claim có thật trong response; lưu trạng thái, coverage và số claim pending. | Test source IDs hợp lệ/sai, claim lạ, review một phần và review nhiều case. Chưa có đánh giá ngữ nghĩa của model thật. | Một phần — cần reviewer |
| Summary faithfulness, coverage, actionability, grounding và hallucinations | Hỗ trợ review theo rubric, kiểm tra thang điểm, reviewer, annotation và adjudication. | Điểm Summary chưa được chấm trên output provider thật; nếu chưa có review thì giữ `pending_review`. | Một phần — cần reviewer |
| JSON và Markdown report | Sinh report theo split, per-case status, quality/operational metrics, lỗi và mức độ review. Chi phí unavailable không bị coi là 0. | Dry-run sinh hai report trong `/tmp`; không đưa output vào dataset. | Hoàn thành — offline |
| Chạy development/holdout có kiểm soát | CLI lọc split hoặc case; development-only không đưa holdout vào tập kết quả. | Test xác nhận chỉ có development case khi `--split development`; holdout kiểm tra tương tự qua CLI filter. | Hoàn thành — offline |
| Real-provider smoke test | Runner không có HTTP/provider client; `--mode live` luôn fail-closed. | Test authorization trả mã 3; không thực hiện request. | Chưa thực hiện |
| Latency/token/cost thật và so sánh model | Runner có chỗ ghi metadata response đã lưu; không có benchmark provider trong task này, giá model không được xác minh. | Không có số liệu model, token, latency hay cost từ provider trong kết quả hiện tại. | Chưa thực hiện |
| Acceptance chính thức LLM-03.7 | Overview yêu cầu tối thiểu một extraction provider thật Contract v1, evidence hợp lệ, không fabricated owner/deadline và chi phí được ghi nhận. | Chưa có bằng chứng thực nghiệm đáp ứng các tiêu chí này. | Chưa hoàn tất |

## 3. Bộ dữ liệu đánh giá

Manifest xác nhận dataset ID `se2026-t15-llm03.7-synthetic-v1`, version `1.0.0`, nguồn là các ví dụ tiếng Việt viết tay hoàn toàn synthetic. Bộ này không được tạo từ audio thực, không chứng minh chất lượng ASR và manifest ghi nhận không có API call dùng để tạo dataset.

| Thuộc tính | Kết quả đã kiểm tra |
|---|---:|
| Tổng số case | 16 |
| Development | 10 (`case-001`–`case-010`) |
| Holdout | 6 (`case-011`–`case-016`) |
| Tổng Audio segments | 65 |
| Tổng gold Action Items | 18 (10 development, 8 holdout) |
| Module được yêu cầu | `meeting_summary`, `action_items` cho cả 16 request |

Mỗi case có ba file với trách nhiệm riêng:

- `audio-transcript-v2.json`: cấu trúc `AudioTranscriptV2` gồm `schema_version=2`, source timeline, speaker list, segment IDs/timestamps/text, warnings và model metadata. Trường model trong fixture chỉ tương thích về hình dạng; không chứng minh provider audio đã chạy.
- `llm-request.json`: request chuẩn hóa Contract v1 được kiểm tra bằng `ExtractionRequest`. Segment ID, text, start/end được giữ nguyên; `speaker` ánh xạ sang `speaker_id`, literal `unknown` thành `null`; duration khớp `duration_sec`. Source offset không được cộng thêm lần nữa.
- `gold.json`: schema đánh giá `llm03.7-gold-v1`, không phải `ExtractionResponse`. Summary gold dùng `reference_overview`, `key_topics`, source references và `forbidden_claims`; action gold dùng `gold_id`, task, owner, deadline, priority, evidence và temporal status.

Các tình huống có action rõ ràng/nhiều action, không có action, speaker mapping thiếu, request được chấp nhận, chuyển owner, deadline bị sửa, ngày ISO và priority tường minh, hai phát biểu overlap, đề xuất có điều kiện, quyết định đang chờ, prompt injection, tên owner được nói trực tiếp khi speaker unknown, hạn mơ hồ và họp nhiều chủ đề. Deadline tự nhiên trong gold được giữ `unresolved` theo hành vi LLM-03 hiện tại; case có raw deadline ISO `2026-12-15` là case duy nhất được gắn `exact_date`.

Loader xác thực nullability và temporal status, ID action duy nhất, owner/priority well-formed, source IDs tồn tại và evidence thuộc phạm vi nguồn. Các kiểm tra cấu trúc không chứng minh nhãn gold có diễn giải ngữ nghĩa hoàn hảo. README dataset yêu cầu gold được reviewer độc lập kiểm tra trước khi dùng để kết luận chất lượng model.

Đây là **16 cuộc họp synthetic ngắn**, mỗi case có 3–8 segment. 65 segment và holdout chỉ 6 case phù hợp để kiểm tra logic và tạo chẩn đoán ban đầu; không đủ đại diện cho cuộc họp thực dài hoặc kết luận thống kê đáng tin cậy.

## 4. Kiến trúc đánh giá

Luồng thực tế của runner offline:

```text
dataset-manifest.json + 3 files/case
                  |
                  v
       Dataset loader / validator
       - Audio Transcript v2
       - ExtractionRequest v1
       - Audio-to-LLM mapping
       - Gold references
                  |
                  v
   Saved ExtractionResponse JSON (optional)
                  |
                  v
       Contract / relationship validation
                  |
                  v
 Action matching + attribute scoring
       |                        |
       +---- human annotations ---+
                  |
                  v
      JSON report + Markdown report
```

| Module | Trách nhiệm |
|---|---|
| `loader.py` | Đọc manifest, phát hiện directory/file, kiểm tra case IDs và split; không đưa case lỗi vào tập đã load. So sánh số case load thành công với manifest. |
| `validation.py` | Kiểm tra Audio v2, Audio-to-request mapping, gold labels và response JSON/schema/relationship/timestamp. Không suy ra semantic correctness từ ID hợp lệ. |
| `matching.py` | Chuẩn hóa task cho exact matching; xử lý manual `match`/`not_match`, một-một, ambiguous và unmatched IDs. |
| `scoring.py` | Tính Action Item và thuộc tính; kiểm tra Summary review; xác định claim IDs từ response công khai và chấm semantic review chỉ theo annotation người dùng. |
| `runner.py` | CLI offline mặc định, lọc split/case, kiểm tra response/review input, tổng hợp metrics, fail-closed live flag và exit codes. Không có provider hoặc HTTP client. |
| `reporting.py` | Tạo JSON/Markdown và che giá trị có dạng credential theo key/value sanitizer. |

## 5. Metrics và cách diễn giải

### Contract và extraction

Mỗi response được ghi riêng các trạng thái `json_valid`, `schema_valid`, `relationship_valid`, `completed` và `semantic_evaluation_available`. JSON parse được không đồng nghĩa với extraction đúng. Schema kiểm tra đầy đủ model Contract v1, gồm phiên bản, IDs, module states, metadata, source references/review fields/temporal models; `validate_response_for_request` kiểm tra quan hệ với request. Timestamp output được so với `start` của source segment đầu tiên theo quy tắc production.

`contract_compliance` và `extraction_success_rate` nêu numerator/denominator theo response file. Response lỗi được giữ trong failure analysis; không biến lỗi thành danh sách action rỗng. Thiếu response là `not_evaluated`, không phải model failure.

### Action Item và thuộc tính

- TP/FP/FN, predicted/expected counts, precision, recall và F1 chỉ kết luận khi matching đã rõ. Task exact sau normalization có thể match tự động; task paraphrase tiếng Việt hoặc cạnh tranh giữa nhiều cặp phải review thủ công. Không dùng list position làm match key.
- Cả gold và prediction không có action được ghi `correct_empty`; không tạo TP giả. Precision/recall/F1 có denominator bằng 0 là `null`. Nếu còn ambiguity, metrics cuối cùng vẫn `null` thay vì ép FP/FN.
- Owner metrics chỉ dùng action đã match: accuracy, correct-null-owner rate, unsupported owner count và wrong-owner count. Gold reassignment dùng owner cuối cùng.
- Deadline gồm raw expression accuracy, resolved date accuracy, temporal status accuracy, fabricated count và correct-null-deadline rate; từng metric có denominator riêng. Raw phrase được so theo rubric. LLM-03 chỉ phân giải chuỗi ISO canonical; không yêu cầu resolver ngày tương đối của LLM-04.
- Priority accuracy và correct-null-priority rate chỉ xét action đã match. Priority không suy luận từ tầm quan trọng của nhiệm vụ; priority không có trong gold nhưng được prediction điền là fabricated.

### Grounding và Summary

Structural grounding kiểm tra source IDs tồn tại trong transcript tương ứng, thứ tự/list constraints, temporal source subsets và `source_timestamp`. Đây chỉ là tính hợp lệ cấu trúc; không gọi nó là semantic grounding accuracy.

Semantic grounding là review người dùng. Claim IDs lấy từ **public `ExtractionResponse` đã lưu**, sau filtering: `summary.overview`, `summary.key_topics[i]`, `actions[i].task` và các field khác chỉ khi non-null (`owner`, `raw_due_expression`, `priority`, `context`). Chỉ số action theo thứ tự trong public response, không lấy index candidate nội bộ; production `SourceValidator` có thể giữ candidate index trước khi `ResponseBuilder` sắp xếp và phát public IDs. `due_date` được đo ở temporal attribute metrics; claim identity của evidence verifier là raw deadline expression. Khi action list rỗng, `actions.absence` là claim review riêng để xác nhận không bỏ sót commitment. Null optional field không tạo claim.

Semantic review có `expected_claim_count`, `reviewed_claim_count`, `pending_claim_count` và `review_coverage`. Không có annotation là `pending_review`; một phần annotation là `partial_review`; chỉ khi mọi claim của response có verdict hợp lệ mới là `reviewed`. Partial review có thể cung cấp `provisional_accuracy`, nhưng `accuracy` cuối cùng giữ `null` khi còn claim pending. Aggregate giữ số case fully reviewed/partial/pending; có bất kỳ claim pending nào thì aggregate final accuracy vẫn `null`.

Summary review nhận faithfulness 1–5, required-fact coverage 0–1, conciseness/actionability 1–5, semantic source grounding 0–1 và hallucination annotations/count. Validator không tự tạo semantic score. Khi chưa có human review, các trường Summary giữ pending/null, không ghi điểm 0 hoặc 1. Gold `reference_overview`, `key_topics`, source IDs và `forbidden_claims` được đưa vào review context.

### Operational metrics

Khi response JSON đã lưu có metadata, runner ghi provider/model, prompt/evidence prompt versions, latency tính từ timestamps và token usage được provider báo cáo. Nếu thiếu usage, status là unavailable và token count là `null`. Bare response JSON không có HTTP status hoặc attempt count. Giá ước tính và billed cost giữ unavailable; không suy ra chi phí bằng 0 từ usage vắng mặt.

## 6. Bốn lỗi P1 và bản sửa

| Lỗi | Nguyên nhân và hành vi sai trước đó | Sửa đổi | Regression tests và kết quả |
|---|---|---|---|
| **P1-01 — bỏ qua gold sai top-level** | Loader chỉ gọi `validate_gold` khi `gold` là object; `[]`, `null` hoặc string có thể bị bỏ qua, trong khi `valid` chỉ kiểm tra issue và manifest có giá trị. Count trước đây chủ yếu dựa trên manifest entries. | Không-object `gold.json` sinh `gold_invalid` với path `gold.json`; case có bất kỳ lỗi case-level nào không được append vào loaded cases. `DatasetLoadResult.valid` so loaded IDs/count/split với manifest, loader so loaded total/split với manifest và expected counts. File không được sửa tự động. | Thêm test cho gold `[]`, `null`, string; case thiếu file/skipped; manifest khai 16 nhưng chỉ 15 load; `cases_total` lệch kể cả khi tắt fixed expected counts; CLI invalid dataset trả 2 và chỉ rõ case/file. Pass trong suite evaluation cuối. |
| **P1-02 — Audio malformed làm crash** | Consistency checker gọi `len()` trên `segments` mà không bảo đảm là list; loader vẫn có thể gọi consistency dù structural validation đã có lỗi. | Loader chỉ chạy consistency khi Audio structural validation sạch. Checker còn kiểm tra kiểu list, segment object/fields, timestamps, duration và offset trước khi so sánh; trả `ValidationIssue` có path thay vì phát sinh TypeError cho malformed payload. Không sửa/fill dữ liệu. | Test `segments=null/string/object/[null]`, thiếu ID, timestamp sai, thiếu duration, speaker sai kiểu; kiểm tra consistency trực tiếp với malformed segment/offset; Audio fixture hợp lệ và `unknown -> null`. CLI invalid dataset trả 2, không traceback. Pass. |
| **P1-03 — semantic grounding chấm sai** | Review validator chỉ kiểm tra `claim_id` là string khác rỗng; không xác minh claim tồn tại trong response và cho phép một phần claim mang status `reviewed`/accuracy đầy đủ. | Thêm `reviewable_claim_ids(response)` trên public response; từ chối claim ngoài response, duplicate và verdict sai; tính expected/reviewed/pending counts và coverage; tạo `partial_review`; final accuracy chỉ có khi đủ claim. Aggregate giữ partial/pending cases và provisional accuracy riêng. | Test unknown/duplicate IDs, verdict/reviewer sai, full/partial review, null optional fields không thành claim, public-order IDs, no-action `actions.absence`, multi-case aggregate. Pass. |
| **P1-04 — review input không fail đúng** | Runner bắt lỗi Summary/semantic rồi ghi `invalid_review` nhưng return code vẫn có thể 0; matcher gọi `.get()` trực tiếp trên `null` trong `action_matches`. | Validate cấu trúc root/case, case ID, field được nhận diện, Summary ranges/reviewer, semantic claims, decision shape/fields/verdict/references/duplicate và one-to-one conflicts trước khi chấm. Matcher cũng phòng vệ với non-object/unhashable IDs. CLI trả 3 cho input review invalid, 1 cho response invalid, 2 cho dataset invalid, 0 cho input hợp lệ—even review còn pending. | Test invalid score/reviewer/semantic claim, `action_matches=[null]`, sai array/field/decision, missing action reference, conflicting assignment, unknown case, invalid encoding, incomplete/complete review, invalid response/dataset và live authorization. Pass. |

Exit-code precedence được ghi trong README và code: live request bị từ chối trước với 3; offline dataset lỗi trả 2 trước khi đọc review; review input lỗi trả 3 trước khi tạo report; response validation failures trả 1 sau khi ghi report; nếu không có các lỗi trên trả 0. Khi review không có response hợp lệ để đối chiếu, review đó bị từ chối, không bị coi là pending hợp lệ.

## 7. Kiểm thử và xác thực

> Tất cả lệnh dưới đây chạy trong `apps/llm-service`. Runner được giữ offline; không dùng lệnh smoke test provider. `UV_CACHE_DIR` được đặt trong `/tmp` vì cache mặc định ở home read-only trong môi trường này.

| Lệnh thực tế | Kết quả quan sát |
|---|---|
| `env UV_CACHE_DIR=/tmp/llm037-uv-cache uv run --locked --extra test pytest -q tests/evaluation` | **94 passed**, 0 failed, 0 skipped. |
| `env UV_CACHE_DIR=/tmp/llm037-uv-cache uv run --locked --extra test python -m evaluation.runner validate-dataset` | Exit 0: `Dataset 1.0.0 valid: 16 cases (10 development, 6 holdout).` |
| `env UV_CACHE_DIR=/tmp/llm037-uv-cache uv run --locked --extra test python -m evaluation.runner run --split development --output-dir /tmp/llm03.7-review-dry-run` | Exit 0; tạo `report.json` và `report.md`; 10 case, 0 response evaluated, 10 skipped. Action/Contract/Summary/semantic metrics không có denominator và được ghi `null`/`not_evaluated`. |
| `env UV_CACHE_DIR=/tmp/llm037-uv-cache uv run --locked --extra test pytest -q` | **684 passed in 2.45s**, 0 failed, 0 skipped. |

Test fixture toàn service tự xóa `OPENROUTER_API_KEY` và chặn outbound HTTP qua `httpx` sync/async transport. Bộ test hiện tại gồm regression Contract/API và Fake/Mock provider tests; chúng xác nhận policy và contract, không đo hiểu ngữ nghĩa của model thật. Thử nghiệm invalid input xác nhận exit code 1/2/3 tương ứng; live mode kể cả có `--ack-live`, `--max-cases` và `--spend-limit-usd` hợp lệ vẫn bị từ chối với mã 3.

Không có test nào bị fail trong lần chạy cuối. Không có test bị skip trong kết quả pytest cuối. Các lỗi trong quá trình test-first ban đầu được sửa trước lần chạy cuối; số liệu trong bảng chỉ là kết quả cuối cùng.

## 8. An toàn vận hành và chi phí

- Offline là mặc định. Runner không import HTTP client, không gọi `/v1/extractions`, không gọi OpenRouter và không đọc token để suy ra quyền chạy live.
- `--mode live` không phải chế độ chạy inference hiện hữu: nó kiểm tra acknowledgment/case cap/spending limit dương rồi vẫn trả 3 vì chưa có giá hiện hành đã xác minh hoặc cơ chế enforce chi phí trước request. Không có hard cap được tuyên bố.
- Không chạy real-provider extraction, model comparison, paid benchmark, live smoke test hay local service inference trong task này. Không có concurrency/retry trong runner offline.
- Test harness chặn HTTP và xóa biến `OPENROUTER_API_KEY`; report sanitizer có test che token/API-key/authorization dạng giá trị.
- Ngân sách tổng LLM của dự án là **$2.00**. Mức **$0.50 cho LLM-03.7 chỉ là đề xuất, chưa được phê duyệt** và không được dùng làm spending authorization.
- Candidate model IDs trong dataset/report cũ, availability và giá hiện tại chưa được kiểm tra. Phải xác minh lại trước benchmark. Không có số cost/usage nào được tạo hoặc ước lượng trong lần chạy offline này.

Pipeline production được audit nhưng không chỉnh sửa: FastAPI `POST /v1/extractions` yêu cầu token; `VerifiedExtractionService` điều phối candidate extraction → projection → `SourceValidator` → `EvidenceVerifier` → `TemporalReviewProcessor` → `ResponseBuilder`. Provider factory chọn OpenRouter theo server settings; runner không override model. Extraction và evidence verification có thể dùng hai provider generations; public token usage chỉ được gộp khi usage của cả hai có mặt. Temporal safeguards hiện chỉ resolve raw date canonical ISO; cụm ngày tự nhiên còn unresolved/reviewable, khác với temporal resolution tương lai của LLM-04.

## 9. Giới hạn đã biết

1. **Quy mô và đại diện:** chỉ 16 case handwritten synthetic, 65 segment, 18 gold actions; transcript ngắn, không có audio thật, không phản ánh ASR noise hoặc cuộc họp dài.
2. **Holdout nhỏ:** 6 case chỉ cho kết quả exploratory. Không tune trên holdout; cần giữ split riêng cho một lần so sánh cuối.
3. **Gold quality:** validator xác nhận schema, IDs và consistency, không thay thế independent semantic review của gold labels.
4. **Paraphrase tiếng Việt:** exact normalization minh bạch nhưng không phân loại tương đương nghĩa tự động. Các cặp khó cần reviewer; unresolved match khiến final action metrics pending.
5. **Summary và semantic evidence:** cả hai cần con người chấm. Runner có annotation validation, chưa có reviewer scores cho output provider thật.
6. **Chưa đo end-to-end:** không có extraction thật trong task này; chưa có model quality, success rate thực, latency, token consumption, failure rate hoặc comparison.
7. **Cost:** offline saved responses không chứa billed cost. Giá ước tính không có nếu chưa xác minh model/pricing/usage; thiếu usage không có nghĩa cost bằng 0. Live fail-closed hiện chưa thể bảo đảm giới hạn chi tiêu cứng.
8. **LLM-03 và LLM-04:** hiện chỉ chấp nhận exact ISO date để resolve; không đánh giá khả năng xử lý relative Vietnamese date theo kỳ vọng LLM-04.
9. **Provider khác nhau:** free và paid model có thể hỗ trợ structured output, availability, token usage, chất lượng evidence và giá khác nhau; không thể giả định kết quả của model này áp dụng cho model khác.

## 10. Việc còn lại trước real-provider testing

Các bước sau cần được thực hiện trong task được phê duyệt riêng; không bước nào được chạy trong lần này:

1. Có người review độc lập gold labels và chốt các điểm diễn giải/action boundaries còn mơ hồ.
2. Xác minh lại model IDs, availability, structured-output support, provider route và pricing tại thời điểm chạy.
3. Phê duyệt spending authorization rõ ràng trong ngân sách tổng $2; không dùng đề xuất $0.50 nếu chưa được chấp thuận. Chốt maximum case count và quy trình dừng nếu cost không thể enforce trước request.
4. Chọn hoặc xây dựng cơ chế chạy live an toàn gọi endpoint LLM Service hiện có, dùng `LLM_SERVICE_TOKEN`, giữ nguyên request body, lưu response/log ngoài dataset và không gửi gold labels. Không gọi OpenRouter trực tiếp từ runner.
5. Sau phê duyệt, chạy một free-model smoke test có kiểm soát, xác minh một response hoàn chỉnh theo Contract v1, source references, owner/deadline safeguards và response metadata.
6. Chạy development comparisons với model/config/prompt cố định, theo dõi errors và reviewer decisions. Không dùng holdout để tuning.
7. Dùng holdout một lần cho so sánh cuối sau khi phương pháp được khóa; báo riêng split/model, denominator và bất định của mẫu nhỏ.
8. Thu latency và input/output tokens thực; ghi rõ missing usage, estimated cost và actual billed cost là các khái niệm khác nhau. Tổng hợp Summary, semantic grounding và hallucination review của con người.
9. Viết báo cáo benchmark model/cost có giới hạn, lỗi, reviewer adjudication và chứng cứ không lộ credential.

## 11. Trạng thái milestone

**LLM-03.7 offline evaluation infrastructure đã được sửa và kiểm chứng: 94 evaluation tests và 684 regression tests pass; dataset 16/16 hợp lệ. Real-provider benchmarking vẫn đang chờ phê duyệt và thực hiện.**

Theo acceptance trong [LLM-03 overview](llm-03-overview.md), milestone LLM-03.7 **chưa hoàn tất** cho đến khi có ít nhất một real-provider extraction hợp lệ theo Contract v1, evidence/owner/deadline review và cost/usage được ghi nhận. Lần chạy hiện tại không tạo các bằng chứng đó.

## 12. Tài liệu tham khảo

### Evaluation code và test

- [Evaluation README](../../../../apps/llm-service/evaluation/README.md)
- [Dataset loader](../../../../apps/llm-service/evaluation/loader.py), [validation](../../../../apps/llm-service/evaluation/validation.py), [matching](../../../../apps/llm-service/evaluation/matching.py), [scoring](../../../../apps/llm-service/evaluation/scoring.py), [runner](../../../../apps/llm-service/evaluation/runner.py), [reporting](../../../../apps/llm-service/evaluation/reporting.py)
- [Evaluation tests](../../../../apps/llm-service/tests/evaluation/): [loader](../../../../apps/llm-service/tests/evaluation/test_loader.py), [validation](../../../../apps/llm-service/tests/evaluation/test_validation.py), [matching](../../../../apps/llm-service/tests/evaluation/test_matching.py), [scoring](../../../../apps/llm-service/tests/evaluation/test_scoring.py), [runner](../../../../apps/llm-service/tests/evaluation/test_runner.py), [reporting](../../../../apps/llm-service/tests/evaluation/test_reporting.py)
- [Dataset manifest](../../../../apps/llm-service/evaluation/datasets/llm-03.7-evaluation/dataset-manifest.json), [dataset README](../../../../apps/llm-service/evaluation/datasets/llm-03.7-evaluation/README.md), [evaluation rubric](../../../../apps/llm-service/evaluation/datasets/llm-03.7-evaluation/evaluation-rubric.md)

### Contract, Audio và production integration

- [LLM Service Contract v1](../../llm-service-contract.md)
- [Audio Service API / Transcript v2](../../../audio-service-api.md)
- Audio implementation types: [audio-types.ts](../../../../apps/audio/src/audio/audio-types.ts) and [audio-transcript.ts](../../../../apps/audio/src/audio/audio-transcript.ts)
- [Request schema](../../../../apps/llm-service/app/schemas/request.py), [response schema](../../../../apps/llm-service/app/schemas/response.py), [temporal schema](../../../../apps/llm-service/app/schemas/temporal.py)
- [FastAPI route](../../../../apps/llm-service/app/api/routes.py), [runtime settings](../../../../apps/llm-service/app/core/config.py), [application factory](../../../../apps/llm-service/app/main.py)
- [SourceValidator](../../../../apps/llm-service/app/services/source_validation.py), [EvidenceVerifier](../../../../apps/llm-service/app/services/evidence.py), [temporal safeguards](../../../../apps/llm-service/app/services/temporal_safeguards.py), [response builder](../../../../apps/llm-service/app/services/response_builder.py), [verified service](../../../../apps/llm-service/app/services/verified_extraction.py), [OpenRouter adapter](../../../../apps/llm-service/app/providers/openrouter.py)

### Milestone history

- [LLM-03 overview](llm-03-overview.md)
- [LLM-03.1 provider selection and smoke test](llm-03.1-provider-selection-and-smoke-test-report.md)
- [LLM-03.2 provider adapter](llm-03.2-provider-adapter-report.md)
- [LLM-03.3 prompts and candidates](llm-03.3-versioned-prompts-and-candidates-report.md)
- [LLM-03.4 extraction service](llm-03.4-extraction-service-report.md)
- [LLM-03.5 validation and evidence](llm-03.5-output-validation-report.md)
- [LLM-03.6 offline tests and Contract integration](llm-03.6-offline-tests-and-contract-integration-report.md)
