# Báo cáo LLM-03.7.2 — DeepSeek Smoke, Development & Holdout Evaluation

**Dự án:** SE2026-T15 — Vietnamese Meeting Minutes Assistant

**Thành phần:** `apps/llm-service`

**Milestone:** LLM-03.7.2 — Real Provider Smoke Test & Development Evaluation

**Branch được kiểm tra:** `feature/llm-03-provider-integration`

**Ngày cập nhật báo cáo:** 2026-11-19

**Trạng thái milestone:** **Đã hoàn tất đánh giá — các vấn đề chất lượng đã biết được ghi nhận.** (Evaluation completed — known issues documented.)

**Kết luận:** Smoke DeepSeek, development 10/10 case và holdout 6/6 case đã được chạy qua pipeline LLM Service hiện có, sau đó được đánh giá offline và human review. Có các vấn đề đã biết về phân giải ngày ISO ở `case-008`, một Action Item dự đoán thừa ở `case-015`, và độ chính xác khi giữ nguyên cụm deadline. Đây là kết quả trên tập synthetic ngắn; không tự nó xác nhận production readiness hay độ chính xác trên cuộc họp thực tế.

## 1. Tóm tắt điều hành

LLM-03.7.2 bổ sung runner thủ công, độc lập với `evaluation.runner`, gọi endpoint FastAPI có xác thực để tái sử dụng pipeline extraction đang chạy. Runner hỗ trợ ba chế độ live với quyền riêng theo mode:

| Mode | Case được phép | Cờ ủy quyền |
|---|---|---|
| Smoke | `case-001` | `--authorize-smoke` |
| Development | `case-001`–`case-010` | `--authorize-development` |
| Holdout | `case-011`–`case-016` | `--authorize-holdout` |

Các response Contract v1 hợp lệ được lưu ngoài dataset, rồi chấm bằng evaluator offline và hoàn tất human review. Kết quả cuối cùng xác nhận smoke kỹ thuật và semantic gate đã qua; development đạt 10/10 case và holdout đạt 6/6 case. Báo cáo dưới đây tách metric theo split, và tách live HTTP execution metrics khỏi response-based offline metrics.

Các số test ở mục 7 có cả kết quả triển khai/remediation lịch sử và kết quả xác minh mới nhất được báo cáo trong môi trường phát triển cục bộ. Không có bằng chứng GitHub CI độc lập trong báo cáo này. Các hạn chế giá/billing và lỗi chất lượng đã biết được nêu tại mục 15. **LLM-03.7.2 đã hoàn tất đánh giá, với các vấn đề chất lượng đã biết được ghi nhận; production readiness và độ chính xác trên dữ liệu thực là các câu hỏi riêng.**

## 2. Mục tiêu và phạm vi

Phạm vi thực hiện gồm runner thủ công cho smoke/development/holdout, test giả lập HTTP, hướng dẫn vận hành và báo cáo kỹ thuật này. `evaluation.runner` tiếp tục offline và fail-closed; không có sửa đổi production extraction, prompt, provider adapter, contract, fixture, gold label hay `.env`.

Các giới hạn được áp dụng:

- Mỗi mode chỉ chấp nhận case thuộc split tương ứng; case ngoài split, bao gồm holdout trong mode development, bị từ chối trước request.
- Smoke, development và holdout đều yêu cầu cờ authorization riêng; smoke approval không cấp quyền chạy development hoặc holdout.
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

Kết quả preflight ban đầu ngày 2026-11-18:

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

Tại thời điểm preflight, trang model OpenRouter công bố mức giá headline `$0.036/M` input, `$0.50/M` output và các mức provider-specific/cache khác nhau. Các mức này không xác nhận giá của route cho request đã chạy và không được dùng để ước tính chi phí benchmark. [Trang model và giá OpenRouter](https://openrouter.ai/deepseek/deepseek-v4.1-flash-1017)

Trang model tại thời điểm kiểm tra cũng mô tả structured output qua JSON Schema. Runtime dùng `json_object`, không pin upstream provider. Smoke extraction thật đã hoàn tất thành công với cấu hình runtime này, nhưng public response không ghi route upstream; điều đó không xác định provider nào xử lý request hoặc giá nào được áp dụng. [Hướng dẫn structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs), [hướng dẫn provider routing](https://openrouter.ai/docs/guides/routing/provider-selection)

Thông tin pricing và model trên là ảnh chụp tài liệu công khai tại thời điểm kiểm tra; cần xác minh lại ngay trước lần chạy trả phí. Không truy cập account dashboard hoặc API quản lý để xác minh giới hạn chi tiêu. Preflight `READY` chỉ có nghĩa cấu hình cục bộ đạt các kiểm tra tĩnh, không có nghĩa được phép tiêu tiền.

## 5. Thay đổi triển khai

`evaluation.deepseek_runner` được tách khỏi `evaluation.runner`:

| Mode | Case được phép | Ủy quyền riêng |
|---|---|---|
| Smoke | `case-001` | `--authorize-smoke` |
| Development | `case-001`–`case-010` | `--authorize-development` |
| Holdout | `case-011`–`case-016` | `--authorize-holdout` |

1. **Preflight mặc định:** xác thực dataset, split, biến cấu hình, model ID cố định, output token limit, JSON mode, timeout và loopback endpoint. Không tạo HTTP client.
2. **Smoke:** yêu cầu `--authorize-smoke`, `--max-cases 1`, mức chi tiêu dương và `--confirm-account-spending-limit`; chọn cố định `case-001`.
3. **Development:** yêu cầu `--authorize-development` riêng; chỉ chọn case development, tối đa 10. Case ID lạ hoặc holdout, kể cả truyền tường minh, bị từ chối. Chế độ này còn yêu cầu có kết quả smoke thành công cùng cấu hình trong cùng output directory; response case-001 hợp lệ được tái sử dụng.
4. **Request:** dùng đúng file request của case, xác thực lại bằng `ExtractionRequest`, gửi tới local loopback endpoint với bearer token từ settings. Không gọi OpenRouter trực tiếp.
5. **Lưu kết quả:** response chỉ lưu khi JSON và Contract v1/request relationship hợp lệ, provider là `openrouter`, model ID đúng candidate. Các lỗi HTTP, timeout, JSON, contract hoặc model được ghi riêng bằng category đã làm sạch; không lưu body lỗi hay credential. Output không bị ghi đè.
6. **Chấm và báo cáo:** các response thành công được chuyển sang evaluator offline để tạo report. Review template ban đầu để trống; Summary và semantic grounding vẫn chờ reviewer cho đến khi review được hoàn tất. Development và holdout lưu record/report riêng.

Runner chỉ gửi `llm-request.json` của case; không gửi `gold.json` hoặc human review. Thực thi tuần tự, không retry tự động, dừng sau request thất bại đầu tiên. HTTP live execution counters được ghi riêng, không đổi semantics của evaluator offline.

Runner ghi metadata cho HTTP status, latency, model/provider, prompt versions, token usage khi service trả về, attempt/retry count và trạng thái cost. Route thực tế, estimated cost và billed cost để `null` khi không có dữ liệu. Không có retry và concurrency là 1. `evaluation.runner` không nhận được code gọi live và tiếp tục fail-closed.

## 6. Kiểm soát chi tiêu và an toàn

Runner không đặt sẵn mức chi tiêu. Mỗi chế độ live yêu cầu người vận hành truyền một mức chi tiêu dương; `$0.25` là đề xuất trong giai đoạn lập kế hoạch, không phải giới hạn cứng. Cờ `--confirm-account-spending-limit` xác nhận rằng người vận hành đã cấu hình giới hạn ở cấp tài khoản/API key. Runner không thể truy vấn hoặc xác thực độc lập giới hạn đó, cũng không kiểm soát billing phía provider. Trường `hard_cap_enforced_by_runner` luôn là `false`; không được xem mức chi hoặc số lượng case là giới hạn cứng. Chủ dự án báo cáo tổng chi phí thực tế cho Smoke, Development và Holdout là **USD 0.03**; runner không tự đo được khoản này.

Các lần chạy live ở mục 15 đã có xác nhận riêng của người vận hành. Tổng chi phí **USD 0.03** do chủ dự án xác nhận; metadata đã lưu không có số tiền billing thực tế hoặc route upstream để đối chiếu độc lập. `$0.25` từng là mức phân bổ đề xuất ở giai đoạn xây dựng runner, còn `$2` trong lệnh holdout là mức chi được ủy quyền; không số nào trong hai giá trị đó là khoản chi thực tế hay giới hạn cứng do runner bảo đảm.

## 7. Kiểm thử và xác thực offline

Các kết quả dưới đây được ghi theo giai đoạn; test runner dùng mock HTTP transport, còn chất lượng model thật được đánh giá riêng trên các DeepSeek response đã lưu.

Các lệnh sau đã chạy từ `apps/llm-service`:

| Lệnh | Kết quả quan sát |
|---|---|
| `env UV_CACHE_DIR=/tmp/llm037-uv-cache uv run --locked --extra test pytest -q tests/evaluation` | **123 passed** |
| `env UV_CACHE_DIR=/tmp/llm037-uv-cache uv run --locked --extra test python -m evaluation.runner validate-dataset` | Dataset `1.0.0` hợp lệ: **16 case (10 development, 6 holdout)** |
| `env UV_CACHE_DIR=/tmp/llm037-uv-cache uv run --locked --extra test python -m evaluation.runner run --split development --output-dir /tmp/llm03.7.2-offline-dry-run` | Thành công, sinh `report.json` và `report.md` |
| `env UV_CACHE_DIR=/tmp/llm037-uv-cache uv run --locked --extra test --env-file .env python -m evaluation.deepseek_runner` | `READY`; **không có network request** |
| `env UV_CACHE_DIR=/tmp/llm037-uv-cache uv run --locked --extra test pytest -q` | **713 passed** |

Kết quả validation mới nhất được báo cáo từ môi trường phát triển cục bộ sau khi hoàn tất hỗ trợ holdout:

| Phạm vi | Kết quả mới nhất được ghi nhận |
|---|---:|
| DeepSeek runner tests | **62 passed** |
| Evaluation test suite | **156 passed** |
| Full LLM Service test suite | **746 passed** |
| Dataset validation | **16 case hợp lệ (10 development, 6 holdout)** |
| `git diff --check` | **Passed** |

Đây là kết quả local được báo cáo cho lần xác minh cuối, không phải xác nhận độc lập từ GitHub CI. Test mocked không gọi model.

Dry-run development có 10 case, `evaluated_count=0`, `skipped_count=10`; contract, extraction success, Action Item, owner, deadline, priority, grounding và Summary metrics có denominator bằng 0 và value `null`. Đây là kết quả không có response để chấm, không phải điểm chất lượng bằng 0. Test mới bao gồm no-network default, auth riêng biệt, thiếu credential không lộ secret, model cấu hình sai, dataset sai, chặn holdout, body request nguyên vẹn, Contract v1 response thành công/thất bại, các mã HTTP 401/403/429/5xx, timeout, không retry, timeout hữu hạn, giới hạn case, reuse smoke, ngăn overwrite, cost unknown không thành hard cap và bảo toàn evaluator offline. Các HTTP response trong test đều đến từ mock.

Không chạy lint riêng. Không có pytest nào gọi endpoint live hoặc model; inference Smoke/Development/Holdout thật là các lượt benchmark riêng, được ghi ở mục 15. Artifacts của runner không tự xác minh số tiền đã thanh toán; tổng USD 0.03 là khoản do chủ dự án báo cáo.

## 8. Kết quả benchmark cuối

Smoke, development và holdout đã được thực hiện; số liệu cuối theo split được tổng hợp tại mục 15 từ các `report.json` đã review và live metadata tương ứng. Không gộp Action F1 của development và holdout thành một metric benchmark duy nhất.

## 9. Giới hạn và rủi ro còn lại

- Dataset có 16 cuộc họp synthetic ngắn; 10 development và 6 holdout case không đại diện đầy đủ cho cuộc họp dài hoặc transcript đời thực. Holdout kiểm tra cấu hình đã đóng băng trên các case chưa dùng trong development, nhưng mẫu nhỏ không đủ để kết luận khác biệt có ý nghĩa thống kê.
- Human review đã hoàn tất cho hai split, nhưng metric vẫn phụ thuộc độ tin cậy của gold labels, rubric và phán đoán reviewer. Semantic review không thay thế đánh giá production hay review độc lập nhiều reviewer.
- Raw deadline accuracy bị ảnh hưởng bởi khác biệt khi giữ nguyên cụm văn bản; `case-008` còn lỗi phân giải ISO date rõ ràng. Full relative-date resolution thuộc LLM-04, ngoài phạm vi sửa hành vi của milestone này.
- Actual upstream OpenRouter provider route không được public response/report cung cấp. Runner không độc lập xác thực giới hạn chi tiêu ở cấp account/API key.
- `--spend-limit-usd` ghi lại mức chi người vận hành cho phép; runner không thực thi đây như giới hạn cứng. Chủ dự án báo cáo tổng chi phí là USD 0.03, nhưng runner không tính tiền billing và artifacts được cung cấp không có hóa đơn/giao dịch để xác minh độc lập. Không chia tổng này theo split/case hoặc suy ra đơn giá từ số token.
- Một extraction có thể tạo nhiều provider generations, bao gồm evidence verification. Token usage có trong metadata, nhưng không đủ để xác nhận tổng số billable generations hoặc số tiền thực tế đã charge.
- Runtime đã xử lý request thật với cấu hình được dùng trong benchmark, nhưng điều đó không chứng minh mọi provider route hoặc model option đều tương thích.

## 10. Cải tiến tiếp theo sau benchmark

Các mục sau là hướng cải thiện/chứng minh bổ sung, không phải điều kiện làm mất hiệu lực completion của benchmark LLM-03.7.2:

1. Xem xét xử lý ISO deadline như `case-008` trong temporal milestone phù hợp; task báo cáo này không thay đổi `TemporalReviewProcessor`.
2. Giảm over-segmentation Action Item để tránh tách phần báo cáo kết quả khỏi commitment chính, như false positive ở `case-015`.
3. Cải thiện việc giữ nguyên raw deadline expression so với span transcript.
4. Mở rộng đánh giá trên cuộc họp dài, đa dạng và dữ liệu thực được phép sử dụng.
5. Xác minh độc lập provider route và actual billing record nếu cần cost benchmark chính xác.

## 11. Trạng thái nghiệm thu cuối

| Tiêu chí | Trạng thái |
|---|---|
| Kiểm tra dataset | Đạt: 16 case / 10 development / 6 holdout |
| Smoke extraction kỹ thuật | Hoàn tất; HTTP 200 và Contract v1 hợp lệ |
| Cổng đánh giá ngữ nghĩa thủ công cho Smoke | Hoàn tất; review đầy đủ và quyết định `approved` |
| Đánh giá live Development | Hoàn tất: đánh giá 10/10 response; 9 request mới và 1 response Smoke dùng lại |
| Human review Development | Hoàn tất; không còn lượt review chờ |
| Đánh giá live Holdout | Hoàn tất: 6/6 case trong split Holdout riêng |
| Human review Holdout | Hoàn tất; không còn lượt review chờ |
| Báo cáo đánh giá offline | Hoàn tất; báo cáo JSON/Markdown đã review theo từng split |
| So sánh Development và Holdout | Hoàn tất; không gộp Action F1 thành một chỉ số benchmark chính thức |
| Test evaluation và kiểm tra dataset | Đạt theo kết quả cục bộ mới nhất tại mục 7 |
| Mức sẵn sàng/độ chính xác trên dữ liệu thực | Chưa được xác lập bởi bộ dữ liệu synthetic ngắn |
| Chi phí đánh giá | USD 0.03 theo báo cáo của chủ dự án; runner và chứng từ billing độc lập chưa xác minh |
| Benchmark LLM-03.7.2 | **Đã hoàn tất đánh giá — các vấn đề chất lượng đã biết được ghi nhận** |

**Kết luận:** Đánh giá LLM-03.7.2 đã hoàn tất, các vấn đề chất lượng đã biết được ghi nhận. Mức sẵn sàng production và độ chính xác trên dữ liệu thực cần được xem xét riêng.

## 12. Lệnh runner để tái lập trong lần chạy được ủy quyền

Các lệnh sau chỉ mô tả giao diện runner; chúng không được thực thi trong lần cập nhật tài liệu này. Mỗi live mode cần xác nhận operator riêng, xác minh model/giá hiện thời và xác nhận account-level spending restriction. `--spend-limit-usd` không phải hard cap.

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

Holdout là mode riêng, chỉ chọn `case-011`–`case-016` và yêu cầu `--authorize-holdout`:

```bash
cd apps/llm-service
uv run --locked --extra test --env-file .env \
  python -m evaluation.deepseek_runner holdout \
  --authorize-holdout \
  --max-cases 6 \
  --spend-limit-usd "$APPROVED_HOLDOUT_LIMIT_USD" \
  --confirm-account-spending-limit \
  --output-dir /tmp/llm03.7.2-holdout
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

**Ghi chú lịch sử:** Phần này ghi lại trạng thái ngay sau remediation P1, trước khi chạy benchmark DeepSeek. Các câu kết luận pending smoke/development ở cuối phần này đã được thay thế bởi kết quả cuối tại mục 15; chúng không mô tả trạng thái milestone hiện tại.

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

### Trạng thái tại thời điểm remediation

P1-01 và P1-02 đã được sửa và offline validation đạt. Các kết luận ở giai đoạn này cho biết lúc đó chưa có OpenRouter/local extraction request, paid inference hay holdout execution, nên chưa có kết quả DeepSeek hoặc human review thật. Mức `$0.25` là đề xuất chưa được duyệt trong giai đoạn lập kế hoạch; runner không thi hành hard monetary cap, còn upstream route/billing chưa được xác minh. Review gate dựa trên reviewer local và rubric smoke; tính độc lập, nhất quán giữa reviewer và chất lượng gold cần được diễn giải thận trọng. Các vấn đề P2 về resume/recovery và health checks nằm ngoài phạm vi remediation.

Kết luận pending của giai đoạn remediation đã **được supersede** bởi kết quả smoke, development và holdout đã review tại mục 15. Nội dung P1 được giữ lại để bảo toàn nguyên nhân, cách sửa và bằng chứng regression testing.

## 15. Kết quả đánh giá cuối và chốt milestone

### Nguồn kết quả

Các số liệu dưới đây được đối chiếu với report JSON đã review và metadata live ở ngoài repository:

- Development: `~/Study_Space/SE-Evaluation-Results/llm03.7.2/reports/development-reviewed/report.json` và `metadata/development.json`.
- Holdout: `~/Study_Space/SE-Evaluation-Results/llm03.7.2-holdout/reports/holdout/reviewed/report.json` và `metadata/holdout.json`.
- Smoke: `~/Study_Space/SE-Evaluation-Results/llm03.7.2/metadata/smoke.json`, `metadata/development.json` (smoke quality gate) và review artifacts cùng thư mục.

Ba mode ghi nhận model ID `deepseek/deepseek-v4.1-flash-1017`, provider `openrouter`, prompt versions `extract-v1.0` và `evidence-v1.3`. Public metadata không chỉ ra upstream OpenRouter endpoint đã xử lý request.

### Smoke test và cổng đánh giá ngữ nghĩa

| Chỉ số | Kết quả |
|---|---:|
| Case | `case-001` |
| HTTP / smoke kỹ thuật | 200 / `technical_smoke_passed` |
| Thực thi live | 1 lần thử, 1 thành công, 0 thất bại; tỷ lệ 1/1 |
| Review ngữ nghĩa | `semantic_review_passed`; đã review 7/7 claim; quyết định `approved` |
| Độ trễ | 17.9132 giây |
| Token đầu vào / đầu ra | 7,037 / 2,830 |

Response Smoke được lưu và review trước khi chạy Development. Development tái sử dụng response cùng cấu hình đó, không gửi request mới cho `case-001`.

### Kết quả Development

| Chỉ số | Development |
|---|---:|
| Số case được đánh giá | 10/10 |
| Action Item kỳ vọng / dự đoán | 10 / 10 |
| Tuân thủ Contract v1 | 100% (10/10) |
| Tỷ lệ trích xuất thành công (response đã lưu) | 100% (10/10) |
| Action Item TP / FP / FN | 10 / 0 / 0 |
| Precision / Recall / F1 của Action Item | 100% / 100% / 100% |
| Case không có Action Item được xử lý đúng | 2 |
| Độ chính xác owner | 100% (10 action đã khớp) |
| Độ chính xác deadline gốc | 80% (8/10) |
| Độ chính xác ngày đã phân giải | 0/1 (0%) |
| Độ chính xác trạng thái thời gian của deadline | 90% (9/10) |
| Độ chính xác priority | 100% (10 action đã khớp) |
| Grounding nguồn theo cấu trúc | 100% (10/10 case) |
| Faithfulness của Summary | 5.0/5 (trung bình, 10 lượt review) |
| Mức bao phủ dữ kiện bắt buộc trong Summary | 97.5% (trung bình, 10 lượt review) |
| Tính cô đọng/khả năng hành động của Summary | 4.2/5 (trung bình, 10 lượt review) |
| Grounding nguồn ngữ nghĩa của Summary | 100% (trung bình, 10 lượt review) |
| Claim ngữ nghĩa được xác nhận hỗ trợ | 68/68; độ bao phủ 100% |
| Số hallucination Summary được ghi nhận | 0 |
| Lượt review con người còn chờ | 0 |
| Độ trễ trung bình | 15.7163 giây (10 response) |
| Token đầu vào / đầu ra | 70,430 / 23,799 |

### Kết quả Holdout

Holdout là cấu hình đã đóng băng được đánh giá trên sáu synthetic case chưa dùng trong development. Kết quả giữ split riêng và không được dùng để tuning.

| Chỉ số | Holdout |
|---|---:|
| Số case được đánh giá | 6/6 |
| Action Item kỳ vọng / dự đoán | 8 / 9 |
| Tuân thủ Contract v1 | 100% (6/6) |
| Tỷ lệ trích xuất thành công (response đã lưu) | 100% (6/6) |
| Action Item TP / FP / FN | 8 / 1 / 0 |
| Precision / Recall / F1 của Action Item | 88.89% / 100% / 94.12% |
| Case không có Action Item được xử lý đúng | 1 |
| Độ chính xác owner | 100% (8 action đã khớp) |
| Độ chính xác deadline gốc | 87.5% (7/8) |
| Độ chính xác ngày đã phân giải | N/A (mẫu số 0) |
| Độ chính xác trạng thái thời gian của deadline | 100% (8/8) |
| Độ chính xác priority | 100% (8 action đã khớp) |
| Grounding nguồn theo cấu trúc | 100% (6/6 case) |
| Faithfulness của Summary | 5.0/5 (trung bình, 6 lượt review) |
| Mức bao phủ dữ kiện bắt buộc trong Summary | 100% (trung bình, 6 lượt review) |
| Tính cô đọng/khả năng hành động của Summary | 4.33/5 (trung bình, 6 lượt review) |
| Grounding nguồn ngữ nghĩa của Summary | 100% (trung bình, 6 lượt review) |
| Claim ngữ nghĩa được xác nhận hỗ trợ | 50/50; độ bao phủ 100% |
| Số hallucination Summary được ghi nhận | 0 |
| Lượt review con người còn chờ | 0 |
| Độ trễ trung bình | 19.1320 giây (6 response) |
| Token đầu vào / đầu ra | 44,372 / 22,081 |

### So sánh Development và Holdout

| Chỉ số | Development (n=10) | Holdout (n=6) |
|---|---:|---:|
| Tuân thủ Contract v1 | 100% (10/10) | 100% (6/6) |
| Trích xuất thành công (response đã lưu) | 100% (10/10) | 100% (6/6) |
| Precision của Action Item | 100% | 88.89% |
| Recall của Action Item | 100% | 100% |
| F1 của Action Item | 100% | 94.12% |
| Độ chính xác owner | 100% (10) | 100% (8) |
| Độ chính xác deadline gốc | 80% (8/10) | 87.5% (7/8) |
| Độ chính xác ngày đã phân giải | 0/1 | N/A (mẫu số 0) |
| Độ chính xác trạng thái deadline | 90% (9/10) | 100% (8/8) |
| Độ chính xác priority | 100% (10) | 100% (8) |
| Faithfulness của Summary | 5.0/5 | 5.0/5 |
| Mức bao phủ dữ kiện trong Summary | 97.5% | 100% |
| Tính khả thi của Summary | 4.2/5 | 4.33/5 |
| Grounding nguồn của Summary (human review) | 100% | 100% |
| Claim ngữ nghĩa được xác nhận hỗ trợ | 68/68 | 50/50 |
| Độ trễ trung bình | 15.7163 giây | 19.1320 giây |
| Token đầu vào / đầu ra | 70,430 / 23,799 | 44,372 / 22,081 |

Holdout Action F1 thấp hơn do một false-positive Action Item ở `case-015`: model tách việc báo cáo kết quả latency thành action riêng, trong khi gold xem đó là phần của cam kết kiểm tra độ trễ. Hai split nhỏ, khác số lượng và phân bố case; chênh lệch không chứng minh khác biệt có ý nghĩa thống kê. Không gộp hai Action F1 thành một benchmark score chính thức.

### Số liệu thực thi live và vận hành

Các số dưới đây lấy từ `metadata/smoke.json`, `metadata/development.json` và `metadata/holdout.json`. Đây là số request thực tế, khác với tỷ lệ trích xuất thành công tính từ các response đã lưu trong báo cáo offline.

| Chế độ | Case đã chọn | Request đã thử | Thành công | Thất bại | Dùng lại | Chưa thử | Tỷ lệ thành công live (mẫu số) | Mã HTTP |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Smoke | 1 | 1 | 1 | 0 | 0 | 0 | 100% (1) | 200: 1 |
| Development | 10 | 9 | 9 | 0 | 1 | 0 | 100% (9) | 200: 9 |
| Holdout | 6 | 6 | 6 | 0 | 0 | 0 | 100% (6) | 200: 6 |

Metadata của các lượt chạy không ghi nhận request HTTP thất bại hay nhóm lỗi nào. Development có 10 response được chấm, nhưng chỉ có 9 lượt thử HTTP mới vì `case-001` được dùng lại từ Smoke; do đó tỷ lệ thành công live là 9/9, không phải 10/10 lượt thử. Holdout có 6/6 lượt thử HTTP. Độ trễ và mức sử dụng token được tổng hợp ở các bảng theo split phía trên.

Các trường chi phí ước tính và chi phí thanh toán thực tế do runner ghi nhận đều là `null` trong metadata đã lưu. Chủ dự án xác nhận **tổng chi phí thực tế là USD 0.03** cho cả ba chế độ; đây là thông tin chi phí hiện có, không phải số đo thanh toán tự động. Kết quả được cung cấp không có hóa đơn hoặc giao dịch để xác minh độc lập. Không phân bổ USD 0.03 theo split/case và không suy ra đơn giá từ số token. Metadata response công khai không cho biết tuyến provider upstream; giới hạn chi tiêu cấp tài khoản do người vận hành xác nhận và runner không tự xác minh. Mỗi lần trích xuất có thể tạo nhiều lượt sinh từ provider, nên số request HTTP không đồng nghĩa với số lượt sinh hoặc số giao dịch thanh toán.

| Hạng mục chi phí | Giá trị |
|---|---|
| Gateway nhà cung cấp | OpenRouter |
| Model | `deepseek/deepseek-v4.1-flash-1017` |
| Số lần thử HTTP ở Smoke | 1 |
| Số lần thử HTTP mới ở Development | 9 |
| Response Smoke được dùng lại ở Development | 1 (không phải request mới) |
| Số lần thử HTTP ở Holdout | 6 |
| Tổng số lần thử HTTP live duy nhất | 16 |
| Tổng chi phí đánh giá | **USD 0.03** |
| Nguồn xác nhận chi phí | Chủ dự án xác nhận |
| Chứng từ billing được xác minh độc lập | Không có trong các báo cáo được cung cấp |

### Phân tích lỗi đã xác nhận

**LỖI-01 — Phân giải deadline ISO, `case-008`.** Prediction có `raw_due_expression = "vào 2026-12-15"`, `due_date = null` và trạng thái `unresolved`. Gold có `raw_due_expression = "2026-12-15"`, `due_date = "2026-12-15"` và `due_date_resolution_status = "exact_date"`. Ngày ISO không được phân giải đúng; cụm deadline gốc còn thêm từ “vào” so với gold. Không sửa `TemporalReviewProcessor` trong lần cập nhật báo cáo này.

**LỖI-02 — Action Item thừa, `case-015`.** Prediction có action chính “Kiểm tra độ trễ endpoint tìm kiếm” và thêm “Báo lại kết quả khi hoàn thành”. Gold xem việc báo kết quả là một phần của cam kết kiểm tra độ trễ, không phải Action Item độc lập. Đây là một false positive ở Holdout, không phải hallucination Summary được ghi nhận.

**LỖI-03 — Bảo toàn cụm deadline gốc.** Ở `case-006`, prediction giữ cụm `"thứ Ba tuần tới"`, còn gold là `"vào thứ Ba tuần tới"`; transcript có câu “Tôi đồng ý nhận việc và gửi báo cáo vào thứ Ba tuần tới.” Ở `case-011`, prediction ghi `"thứ Tư tuần sau"`, còn gold là `"vào thứ Tư tuần sau"`; transcript nói “Tôi sẽ tổng hợp các lỗi đã biết vào thứ Tư tuần sau.” Ý nghĩa thời gian có thể đúng, nhưng thiếu từ dẫn đầu làm giảm độ chính xác so khớp nguyên văn cụm deadline theo rubric.

### Chốt acceptance và kết luận

| Tiêu chí | Trạng thái cuối |
|---|---|
| Kiểm tra dataset: 16 case, 10 development / 6 holdout | Hoàn tất |
| Smoke kỹ thuật và kiểm tra Contract v1 | Hoàn tất |
| Cổng đánh giá ngữ nghĩa thủ công cho Smoke | Hoàn tất; có phê duyệt tường minh và review đầy đủ |
| Đánh giá live và human review Development | Hoàn tất: 10/10, không còn review chờ |
| Đánh giá live và human review Holdout | Hoàn tất: 6/6, không còn review chờ |
| Báo cáo JSON/Markdown offline và so sánh hai split | Hoàn tất |
| Phân giải deadline ISO, tách Action Item, giữ nguyên deadline gốc | Cải tiến còn lại; đã ghi nhận trong phân tích lỗi |
| Đánh giá cuộc họp dài/trên dữ liệu thực | Chưa thực hiện; ngoài dataset synthetic hiện tại |
| Xác minh billing độc lập | Chưa có chứng từ chi thực tế hoặc route upstream được xác minh |

**Đánh giá LLM-03.7.2 đã hoàn tất, các vấn đề chất lượng đã biết được ghi nhận. Mức sẵn sàng production và độ chính xác trên dữ liệu thực cần được xem xét riêng.**
