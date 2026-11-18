# Báo cáo LLM-03.7.2 — Runner DeepSeek và đánh giá development

**Dự án:** SE2026-T15 — Vietnamese Meeting Minutes Assistant

**Thành phần:** `apps/llm-service`

**Milestone:** LLM-03.7.2 — Real Provider Smoke Test & Development Evaluation

**Branch được kiểm tra:** `feature/llm-03-provider-integration`

**Ngày xác minh:** 2026-11-18

**Kết luận:** Runner và hạ tầng đánh giá offline đã được triển khai. Hai lỗi P1 về success rate live và semantic quality gate đã được sửa, với kết quả xác minh mới nhất ở mục 14. Smoke test DeepSeek và benchmark development chưa chạy; cần phê duyệt trả phí riêng.

## 1. Tóm tắt điều hành

LLM-03.7.2 bổ sung một runner thủ công, độc lập với `evaluation.runner`, để sau này gửi request qua endpoint FastAPI hiện có tới LLM Service. Runner mặc định chỉ chạy preflight không mạng. Khi được phê duyệt riêng, chế độ smoke chỉ có thể xử lý `case-001`; chế độ development chỉ nhận `case-001` đến `case-010`, yêu cầu cờ phê duyệt riêng, giới hạn số case, mức chi tiêu được cấp và xác nhận giới hạn chi tiêu ở cấp tài khoản/API key. Các response hợp lệ được lưu ngoài dataset rồi chấm bằng evaluator offline hiện có.

Các kết quả ghi nhận ở lần xác minh ban đầu, trước phần remediation P1:

- Dataset hợp lệ: 16 case, gồm 10 development và 6 holdout.
- 123 test trong `tests/evaluation` pass.
- Offline dry-run development sinh JSON và Markdown report; 10 case ở trạng thái `not_evaluated` do không có response đã lưu.
- Preflight DeepSeek hoàn tất với kết quả `READY`, đồng thời báo rõ không gửi network request.
- Toàn bộ 713 test của LLM Service pass.

Không gọi OpenRouter hoặc bất kỳ provider nào. Không có response DeepSeek, benchmark score, token usage, latency inference hay chi phí benchmark để báo cáo. Preflight đọc cấu hình runtime nhưng không xác minh trạng thái account-level spend cap. Mức `$0.25` vẫn chưa được phê duyệt; runner không tuyên bố hay thực thi hard monetary cap. Vì các acceptance criteria về extraction thật và đánh giá chất lượng chưa có bằng chứng, **LLM-03.7.2 chưa hoàn tất**.

## 2. Mục tiêu và phạm vi

Phạm vi thực hiện gồm runner thủ công cho smoke/development, test giả lập HTTP, hướng dẫn vận hành và báo cáo kỹ thuật này. `evaluation.runner` tiếp tục offline và fail-closed; không có sửa đổi production extraction, prompt, provider adapter, contract, fixture, gold label hay `.env`.

Các giới hạn được áp dụng:

- Không chạy holdout; lựa chọn case ngoài danh sách development bị từ chối trước request.
- Smoke authorization và development authorization là hai cờ riêng. Cờ smoke không thể mở quyền chạy development.
- Output chỉ ghi ngoài dataset và dùng chế độ tạo file độc quyền; file đã có không bị ghi đè.
- Chỉ gửi `llm-request.json` nguyên trạng qua endpoint local có Bearer authentication. Không gửi gold hay review annotations.
- Thực thi tuần tự, timeout hữu hạn, không retry tự động, không theo redirect và không dùng proxy theo biến môi trường.
- Mọi test của runner dùng mock HTTP transport. Không test nào trong pytest gửi request thật.

## 3. Baseline và thành phần hiện có

Endpoint `POST /v1/extractions` của FastAPI kiểm tra Bearer token, parse `ExtractionRequest` rồi gọi extraction service đã được cấu hình trong runtime. Service hiện có dùng OpenRouter adapter thông qua pipeline candidate extraction, source validation, EvidenceVerifier, temporal safeguard và response builder. Evidence verification là một provider generation bổ sung; do đó một extraction có thể phát sinh hơn một generation.

OpenRouter adapter hiện gửi model từ cấu hình, `response_format: {"type": "json_object"}`, `require_parameters=true` và `allow_fallbacks=false`. Không có mã nào trong task này thay đổi hành vi đó. `allow_fallbacks=false` không đồng nghĩa với việc pin một provider upstream; request vẫn không chỉ định `provider.order` hay provider cụ thể. Public Contract v1 ghi provider là `openrouter` và model ID, nhưng không cho runner biết endpoint provider thực tế đã xử lý request.

Evaluator offline vẫn nhận response đã lưu, kiểm tra Contract v1 và quan hệ với request, rồi chấm Action Items và các thuộc tính theo framework LLM-03.7. Nếu không có response, case vẫn là `not_evaluated`, không bị tính là model failure hoặc dự đoán rỗng.

## 4. Xác minh model và runtime

Preflight an toàn chạy bằng cấu hình `.env` cục bộ. Chỉ trạng thái hiện diện của credential được in; giá trị secret không được đọc ra log hay đưa vào báo cáo.

Kết quả preflight ngày 2026-11-18:

| Hạng mục | Kết quả |
|---|---|
| Dataset | 16 case hợp lệ; development 10, holdout 6 |
| LLM Service token và OpenRouter key | Được cấu hình; giá trị được che giấu |
| Model cấu hình | `deepseek/deepseek-v4.1-flash-1017` |
| Structured output mode | `json_object` |
| Max output tokens | 8192 |
| Request/provider timeout | 180 giây / 60 giây |
| Endpoint mà runner định dùng | `http://127.0.0.1:8000/v1/extractions` |
| Network request trong preflight | Không |
| Account/API-key spending restriction | Chưa được runner kiểm tra độc lập |

Trang model OpenRouter hiện công bố model ID này và mức giá headline `$0.036/M` input, `$0.50/M` output; trang cũng hiển thị giá khác nhau theo provider và có mức cache-read riêng. OpenRouter liệt kê nhiều provider endpoint. Vì vậy giá headline không phải giá được xác nhận cho route của một request cụ thể. [Trang model và giá OpenRouter](https://openrouter.ai/deepseek/deepseek-v4.1-flash-1017)

Trang model hiện cũng mô tả structured output qua JSON Schema. Tài liệu OpenRouter nói hỗ trợ structured output thay đổi theo từng provider endpoint, và route mặc định có thể được chọn theo giá, thông lượng, độ trễ và độ tin cậy. Runtime hiện dùng `json_object`, không phải `json_schema`, và không pin upstream provider. Do chưa có extraction request thật nên khả năng tương thích của đúng route với cấu hình runtime **chưa được kiểm chứng end-to-end**. [Hướng dẫn structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs), [hướng dẫn provider routing](https://openrouter.ai/docs/guides/routing/provider-selection)

Thông tin pricing và model trên là ảnh chụp tài liệu công khai tại thời điểm kiểm tra; cần xác minh lại ngay trước lần chạy trả phí. Không truy cập account dashboard hoặc API quản lý để xác minh giới hạn chi tiêu. Preflight `READY` chỉ có nghĩa cấu hình cục bộ đạt các kiểm tra tĩnh, không có nghĩa được phép tiêu tiền.

## 5. Thay đổi triển khai

`evaluation.deepseek_runner` được tách khỏi `evaluation.runner`:

1. **Preflight mặc định:** xác thực dataset, split, biến cấu hình, model ID cố định, output token limit, JSON mode, timeout và loopback endpoint. Không tạo HTTP client.
2. **Smoke:** yêu cầu `--authorize-smoke`, `--max-cases 1`, mức chi tiêu dương và `--confirm-account-spending-limit`; chọn cố định `case-001`.
3. **Development:** yêu cầu `--authorize-development` riêng; chỉ chọn case development, tối đa 10. Case ID lạ hoặc holdout, kể cả truyền tường minh, bị từ chối. Chế độ này còn yêu cầu có kết quả smoke thành công cùng cấu hình trong cùng output directory; response case-001 hợp lệ được tái sử dụng.
4. **Request:** dùng đúng file request của case, xác thực lại bằng `ExtractionRequest`, gửi tới local loopback endpoint với bearer token từ settings. Không gọi OpenRouter trực tiếp.
5. **Lưu kết quả:** response chỉ lưu khi JSON và Contract v1/request relationship hợp lệ, provider là `openrouter`, model ID đúng candidate. Các lỗi HTTP, timeout, JSON, contract hoặc model được ghi riêng bằng category đã làm sạch; không lưu body lỗi hay credential.
6. **Chấm và báo cáo:** các response thành công được chuyển sang evaluator offline để tạo report. Review template để trống; Summary và semantic grounding vẫn chờ reviewer.

Runner ghi metadata cho HTTP status, latency, model/provider, prompt versions, token usage khi service trả về, attempt/retry count và trạng thái cost. Route thực tế, estimated cost và billed cost để `null` khi không có dữ liệu. Không có retry và concurrency là 1. `evaluation.runner` không nhận được code gọi live và tiếp tục fail-closed.

## 6. Kiểm soát chi tiêu và an toàn

Runner không đặt sẵn mức chi tiêu. Mỗi chế độ live yêu cầu amount dương được truyền trực tiếp; `$0.25` trong đề xuất **chưa được duyệt và không phải mặc định**. Cờ `--confirm-account-spending-limit` là xác nhận của operator rằng đã cấu hình account/API-key limit. Runner không thể truy vấn hoặc xác thực độc lập giới hạn đó, và không kiểm soát billing phía provider. Trường `hard_cap_enforced_by_runner` luôn là `false`; giá trị limit và số lượng case không được quảng bá thành hard spending cap.

Để thực hiện bất kỳ request trả phí nào sau này, cần có phê duyệt riêng cho đúng model, số case, mức chi tiêu, giá/route đã kiểm tra và giới hạn chi tiêu ở cấp account/API key đã được thiết lập. Nếu không có giới hạn account phù hợp hoặc không thể xác định rủi ro chi phí do hai provider generations, không chạy. Đây là báo cáo về hạ tầng runner; lần thực hiện hiện tại đã dừng trước mọi live request theo yêu cầu.

## 7. Kiểm thử và xác thực offline

Các lệnh sau đã chạy từ `apps/llm-service`:

| Lệnh | Kết quả quan sát |
|---|---|
| `env UV_CACHE_DIR=/tmp/llm037-uv-cache uv run --locked --extra test pytest -q tests/evaluation` | **123 passed** |
| `env UV_CACHE_DIR=/tmp/llm037-uv-cache uv run --locked --extra test python -m evaluation.runner validate-dataset` | Dataset `1.0.0` hợp lệ: **16 case (10 development, 6 holdout)** |
| `env UV_CACHE_DIR=/tmp/llm037-uv-cache uv run --locked --extra test python -m evaluation.runner run --split development --output-dir /tmp/llm03.7.2-offline-dry-run` | Thành công, sinh `report.json` và `report.md` |
| `env UV_CACHE_DIR=/tmp/llm037-uv-cache uv run --locked --extra test --env-file .env python -m evaluation.deepseek_runner` | `READY`; **không có network request** |
| `env UV_CACHE_DIR=/tmp/llm037-uv-cache uv run --locked --extra test pytest -q` | **713 passed** |

Dry-run development có 10 case, `evaluated_count=0`, `skipped_count=10`; contract, extraction success, Action Item, owner, deadline, priority, grounding và Summary metrics có denominator bằng 0 và value `null`. Đây là kết quả không có response để chấm, không phải điểm chất lượng bằng 0. Test mới bao gồm no-network default, auth riêng biệt, thiếu credential không lộ secret, model cấu hình sai, dataset sai, chặn holdout, body request nguyên vẹn, Contract v1 response thành công/thất bại, các mã HTTP 401/403/429/5xx, timeout, không retry, timeout hữu hạn, giới hạn case, reuse smoke, ngăn overwrite, cost unknown không thành hard cap và bảo toàn evaluator offline. Các HTTP response trong test đều đến từ mock.

Không chạy lint riêng. Không có live-mode smoke test, model extraction, phát sinh benchmark cost hoặc test nào cần provider availability.

## 8. Kết quả chất lượng và operational benchmark

| Nhóm kết quả | Trạng thái milestone này |
|---|---|
| Smoke extraction case-001 | Chưa chạy; cần paid execution approval riêng |
| Contract compliance của response thật | Chưa có response để đánh giá |
| Action TP/FP/FN, precision/recall/F1 | `not_evaluated`; không có prediction |
| Owner/deadline/priority và hallucination | Chưa đánh giá |
| Structural source grounding | Chưa có response thật để xác minh |
| Summary scores và semantic claim review | Chưa có response; không tạo điểm hoặc verdict giả |
| Latency và HTTP status inference | Chưa có |
| Token usage | Chưa có; preflight không sinh token |
| Estimated / actual billed cost | `null` / chưa có dữ liệu |
| Provider route thực tế | Chưa quan sát; public response hiện không cung cấp trường route |
| Holdout | Không chạy, theo phạm vi |

Hạ tầng đã được test bằng fixture/mocks để chứng minh cách lưu và chấm kết quả; các kết quả đó không phải model output hay benchmark. Không có số điểm mô hình nào được suy ra từ preflight hoặc dry-run.

## 9. Giới hạn còn lại

- Bộ dữ liệu chỉ có 16 cuộc họp synthetic ngắn; 10 development case là chẩn đoán ban đầu, chưa đại diện họp dài hay transcript thực.
- Matching paraphrase tiếng Việt, Summary faithfulness, hallucinations và semantic evidence cần reviewer/adjudicator; chưa có đánh giá người trong milestone này.
- Trang model có giá headline và nhiều provider-specific rates. Runtime hiện không pin hay ghi nhận provider endpoint; không thể dùng mức headline để tính chắc chắn chi phí từng extraction.
- Runner chỉ ghi usage nếu service trả về; usage thiếu là `null`, không phải 0. Actual billed cost không được suy ra từ token count.
- Một extraction có thể có generation extraction và evidence verification. Runner ghi nhận hai stage dự kiến nhưng số provider generations thực tế chưa được quan sát.
- Timeout/giới hạn request không giới hạn billable cost. Cờ xác nhận account cap là operator assertion, không phải xác thực trực tiếp.
- LLM-03 có temporal safeguards và giữ các ngày tương đối ở trạng thái chưa resolve; giải quyết ngày tương đối đầy đủ thuộc LLM-04.
- Chưa xác minh JSON mode qua provider route thực tế, dù model page hiện mô tả hỗ trợ structured output; hỗ trợ có thể khác theo endpoint.

## 10. Còn cần làm trước khi đóng LLM-03.7.2

1. Repository owner xác minh model ID và provider/routing phù hợp ngay trước chạy, xem giá provider-specific hiện thời.
2. Cấu hình, xác minh account/API-key spending restriction đủ thấp cho lần chạy; mức `$0.25` chỉ dùng nếu được phê duyệt rõ ràng.
3. Owner phê duyệt riêng smoke request `case-001` theo model, mức chi và cap đã kiểm tra.
4. Chạy smoke qua local FastAPI endpoint; kiểm tra response Contract v1, source/timestamp, owner/deadline fabrication, review flags, provider/model, prompt versions, usage, latency và billing metadata.
5. Chỉ sau khi smoke đạt, owner phê duyệt riêng development run, tối đa 10 case, không holdout. Response case-001 cùng cấu hình được tái sử dụng.
6. Chạy evaluator offline trên responses, hoàn thiện matching và human Summary/semantic review, rồi ghi báo cáo benchmark với metrics/denominators và chi phí có nguồn.
7. Sau khi development được review mới lên kế hoạch holdout ở milestone/authorization riêng; không dùng holdout để tuning.

Trong lần làm việc này, các bước trên chưa thực hiện; không gửi request thật.

## 11. Trạng thái nghiệm thu

| Tiêu chí | Trạng thái |
|---|---|
| Dataset validation | Đạt: 16 / 10 development / 6 holdout |
| Runner manual với default offline | Đạt qua preflight và mocked tests |
| Authorization smoke/development độc lập | Đạt qua mocked regression tests |
| Development-only, holdout bị chặn | Đạt qua mocked regression tests |
| Sequential, finite timeout, no retry, no overwrite | Đạt qua mocked regression tests |
| Response validation và offline report plumbing | Đạt với synthetic Contract v1 fixture trong mock test |
| DeepSeek configuration / public model metadata | Đã kiểm tra tài liệu và preflight; route/cost/account cap chưa xác minh end-to-end |
| Real DeepSeek smoke extraction | Chưa thực hiện; chờ phê duyệt trả phí |
| Development model evaluation và human review | Chưa thực hiện |
| LLM-03.7.2 hoàn tất | **Chưa đạt** |

**Kết luận:** Hạ tầng runner và validation offline của LLM-03.7.2 đã triển khai và pass test. Benchmark DeepSeek thật vẫn pending. Không thể kết luận chất lượng extraction hoặc đánh dấu milestone hoàn tất cho tới khi có paid smoke được duyệt, đánh giá development và review kết quả.

## 12. Lệnh sử dụng sau khi có phê duyệt

Preflight chỉ đọc config và không gọi endpoint:

```bash
cd apps/llm-service
uv run --locked --extra test --env-file .env \
  python -m evaluation.deepseek_runner
```

Lệnh smoke dưới đây **chỉ là cú pháp cho lần chạy tương lai**, không được thực thi nếu chưa có phê duyệt riêng. Đặt biến amount thành giới hạn được duyệt; `$0.25` không được mặc định hay tự coi là đã duyệt. Trước khi chạy, account/API-key cap và giá/route phải được owner xác minh:

```bash
cd apps/llm-service
uv run --locked --extra test --env-file .env \
  python -m evaluation.deepseek_runner smoke \
  --authorize-smoke \
  --max-cases 1 \
  --spend-limit-usd "$APPROVED_SMOKE_LIMIT_USD" \
  --confirm-account-spending-limit \
  --output-dir /tmp/llm03.7.2
```

Development cần phê duyệt riêng, sau khi smoke thành công cùng cấu hình và cùng output directory:

```bash
cd apps/llm-service
uv run --locked --extra test --env-file .env \
  python -m evaluation.deepseek_runner development \
  --authorize-development \
  --max-cases 10 \
  --spend-limit-usd "$APPROVED_DEVELOPMENT_LIMIT_USD" \
  --confirm-account-spending-limit \
  --output-dir /tmp/llm03.7.2
```

Chấm response đã lưu hoàn toàn offline:

```bash
cd apps/llm-service
uv run --locked --extra test python -m evaluation.runner run \
  --responses-dir /tmp/llm03.7.2/responses \
  --split development \
  --output-dir /tmp/llm03.7.2/reports/offline-development
```

## 13. Tài liệu liên quan

- [Runner và hướng dẫn đánh giá](../../../../apps/llm-service/evaluation/README.md)
- [Runner DeepSeek](../../../../apps/llm-service/evaluation/deepseek_runner.py)
- [Regression tests](../../../../apps/llm-service/tests/evaluation/test_deepseek_runner.py)
- [Dataset manifest](../../../../apps/llm-service/evaluation/datasets/llm-03.7-evaluation/dataset-manifest.json)
- [LLM Contract v1](../../llm-service-contract.md)
- [Tổng quan LLM-03](llm-03-overview.md)
- [Báo cáo LLM-03.7 offline](llm-03.7-offline-evaluation-report.md)

## 14. Remediation P1-01 và P1-02

Phần này ghi nhận các sửa đổi sau review cho LLM-03.7.2. Kết quả dưới đây là xác minh bằng test offline/dataset/preflight; các fixture thành công dùng HTTP mock, không phải output DeepSeek.

### P1-01 — Tách success rate live khỏi response-based evaluation

**Nguyên nhân:** `evaluation.runner.evaluate_offline()` được thiết kế để đánh giá response JSON đã lưu. Các lỗi HTTP được ghi trong `failures/`, không có response JSON để chấm. Vì vậy success rate tính trên response files có thể là 2/2 = 100% dù live runner đã thử ba case và một request trả HTTP 503.

**Sửa đổi:** `evaluation.deepseek_runner` nay tạo một nhóm `live_execution` riêng trong operational record và report JSON/Markdown. Hàm `_send_one()` phân biệt request chưa được gửi với một HTTP attempt thực tế; `_execute()` ghi lại response thành công, lỗi đã xảy ra và các case còn lại sau khi dừng; `_live_execution_metrics()` tổng hợp counters. Các định nghĩa được áp dụng:

| Counter | Định nghĩa |
|---|---|
| `selected_case_count` | Tổng số case được chọn cho run |
| `attempted_count` | Case đã khởi tạo một HTTP extraction request |
| `successful_count` | Attempt nhận HTTP 200 và response đạt Contract v1/request validation |
| `failed_count` | Attempt thất bại bởi HTTP status, timeout/kết nối, JSON, Contract v1 hoặc model mismatch |
| `reused_count` | Response đã lưu, cùng cấu hình và hợp lệ được dùng lại mà không tạo request mới |
| `not_attempted_count` | Case được chọn nhưng không attempt hoặc reuse; gồm case còn lại khi run dừng sớm |
| `live_execution_success_rate` | `successful_count / attempted_count`, hoặc `null` khi không có attempt |
| `live_execution_success_rate_denominator` | Chính là `attempted_count` |

Failure categories và HTTP status distribution chỉ tổng hợp các HTTP attempt; lỗi trước request được báo riêng. Với một success, một HTTP 503 và một case còn lại, fixture test ghi nhận `attempted=2`, `successful=1`, `failed=1`, `not_attempted=1`, rate `0.5` với denominator `2`. Reuse-only fixture ghi `attempted=0`, `reused=1`, rate `null`. Đây là ví dụ kiểm thử giả lập. Các file lỗi vẫn không được chuyển thành response giả; offline evaluator tiếp tục giữ case không có response là `not_evaluated`. Không sửa semantics hay code của `evaluation.runner`.

### P1-02 — Human semantic quality gate sau technical smoke

**Nguyên nhân:** HTTP/JSON/Contract v1 hợp lệ và đúng model chỉ chứng minh kỹ thuật; trường `semantic_evaluation_available` không phải kết quả semantic review. Trước remediation, dev run chỉ cần smoke kỹ thuật cùng cấu hình, nên có thể bắt đầu trước khi con người đối chiếu nội dung với transcript/gold.

**Luồng và trạng thái:** Smoke thành công được lưu là `technical_smoke_passed`, trong khi `semantic_review_status` vẫn là `semantic_review_pending`. Runner tạo response public và review template rỗng, cùng `reviews/smoke-approval.json` ở trạng thái `pending_review`. Tạo response hợp lệ không tự sinh điểm, claim verdict hay approval. Lệnh offline `verify-smoke-review` kiểm tra review; chỉ trạng thái `semantic_review_passed` mới thỏa quality gate.

Reviewer dùng schema review hiện có của `evaluation.runner`/`evaluation.scoring.py`: Summary scores và hallucination annotations, semantic verdict cho mọi claim ID đang tồn tại trên public response, cùng `action_matches` khi paraphrase/matching cần phán định. Action index lấy từ response đã lưu, sau production filtering; không suy ra từ candidate index. Các claim ID không hợp lệ, review thiếu, review một phần, decision sai, identity thiếu, digest mismatch, matching unresolved hoặc schema review lỗi đều không mở dev gate. `evaluation.runner` vẫn offline; runner gọi trực tiếp evaluator offline với review data và không gửi review/gold đến service.

Approval được bind bằng SHA-256 của chính bytes response đã lưu và review file. Approval JSON phải khớp `case-001`, hash response, tên/hash review, decision `approved`, reviewer và rationale. Thay response hoặc review sau khi ký làm digest không khớp. Đây là liên kết xác định với file được review, không phải chữ ký mật mã hay bằng chứng độc lập về danh tính/review. Review local và sign-off vẫn là assertion của operator.

Để pass, review phải hoàn chỉnh; tất cả semantic claims được đánh dấu supported; matching Action Item hoàn tất một-một và không có FP/FN; owner khớp, được transcript hỗ trợ, không có owner không hỗ trợ; raw deadline và temporal status khớp gold, không fabricated, và ngày tương đối của case smoke vẫn `unresolved`/không có resolved date theo rubric LLM-03; priority đúng, không fabricated; Summary không có hallucination, required-fact coverage và semantic source grounding đều bằng 1. Review phải có quyết định người dùng rõ ràng là `approved`. Faithfulness/actionability scores được validate, lưu và reviewer xem xét; rubric không định nghĩa numeric pass threshold nên runner không tự đặt ngưỡng.

Development gọi quality gate trước `_execute()` và cần thêm cờ `--authorize-development`, nên có ba điều kiện tách biệt: smoke kỹ thuật đạt, semantic review đạt và operator cấp quyền development riêng. Review pending trả exit `3` và không tạo HTTP request; quality review hợp lệ nhưng không đạt trả exit `1`; review input sai/malformed trả exit `3`. Case-001 test fixture nay tham chiếu đúng commitment ở `SEG-0002`, với source timestamp `00:00:08.832`, raw expression “trước thứ Sáu này” và temporal state `unresolved`.

### File thay đổi

- `apps/llm-service/evaluation/deepseek_runner.py`: live execution accounting, smoke approval template/fingerprint, offline review gate và reporting.
- `apps/llm-service/tests/evaluation/test_deepseek_runner.py`: mock regressions cho successes/failures/429/timeout/invalid contract/reuse/unattempted/null denominator, smoke review statuses, malformed/stale review, owner/deadline failures, approval và fixture source/timestamp.
- `apps/llm-service/evaluation/README.md`: semantics live-vs-offline, human review/approval steps và lệnh xác minh gate.
- Báo cáo này: remediation P1 và kết quả xác minh mới.

Không sửa production extraction code, prompts, Contract v1 schemas, dataset/gold labels hay `.env`. Các số test được ghi ở đầu báo cáo (`123` evaluation và `713` service tests) là kết quả lịch sử trước remediation, không thay thế cho kiểm thử mới bên dưới.

### Xác minh sau remediation

Các lệnh đã chạy từ `apps/llm-service` sau thay đổi:

| Lệnh | Kết quả quan sát |
|---|---|
| `UV_CACHE_DIR=/tmp/uv-cache uv run --locked --extra test pytest -q tests/evaluation/test_deepseek_runner.py` | **51 passed** |
| `UV_CACHE_DIR=/tmp/uv-cache uv run --locked --extra test pytest -q tests/evaluation` | **145 passed** |
| `UV_CACHE_DIR=/tmp/uv-cache uv run --locked --extra test python -m evaluation.runner validate-dataset` | Dataset `1.0.0` hợp lệ: **16 case (10 development, 6 holdout)** |
| `test -f .env` | `.env` hiện diện; không đọc hay in giá trị secret |
| `UV_CACHE_DIR=/tmp/uv-cache uv run --locked --extra test --env-file .env python -m evaluation.deepseek_runner preflight` | `READY`, đúng candidate model và timeout cấu hình; runner in rõ **no network request made** |
| `UV_CACHE_DIR=/tmp/uv-cache uv run --locked --extra test python -m evaluation.runner run --mode live` | Từ chối fail-closed, exit **3**, yêu cầu `--ack-live`; không có request |
| `UV_CACHE_DIR=/tmp/uv-cache uv run --locked --extra test pytest -q` | **735 passed** |

Focused mocked tests chứng minh live denominator có HTTP failures, reused response không tính attempt, early-stop cases là `not_attempted`, zero attempts trả `null`, và offline report vẫn đánh dấu case không có response là `not_evaluated`. Tests cho gate xác nhận smoke ban đầu pending, review thiếu/partial/malformed/stale/unsupported/rejected bị chặn trước HTTP, owner/deadline fabricated thất bại, valid explicit review cho phép quality gate, nhưng cờ development vẫn bắt buộc. Fixture test xác nhận source ID/time mới. Các kết quả này chứng minh hành vi runner/evaluator offline, **không phải benchmark result**.

### Trạng thái sau remediation và rủi ro còn lại

P1-01 và P1-02 đã được sửa và offline validation đạt. Dataset vẫn nguyên vẹn. Không có OpenRouter/local extraction request, paid inference hay holdout execution; vì vậy chưa có kết quả DeepSeek, latency/token/cost thực tế hoặc semantic review thật. `$0.25` chưa được duyệt, runner không thi hành hard monetary cap, upstream route/billing chưa được xác minh. Review gate dựa trên reviewer local và rubric của case smoke; tính độc lập, nhất quán giữa nhiều reviewer và chất lượng gold vẫn cần con người kiểm chứng. Faithfulness/actionability chưa có cutoff số do rubric không chỉ rõ pass point. Các vấn đề P2 về resume/recovery và health checks vẫn ngoài phạm vi.

**Kết luận milestone:** Hai lỗi P1 đã được remediate và kiểm chứng offline; `LLM-03.7.2` vẫn chưa hoàn tất. Real DeepSeek smoke phải được cấp quyền riêng, semantic review của smoke phải được phê duyệt trước development, và benchmark development vẫn đang chờ paid execution authorization.
