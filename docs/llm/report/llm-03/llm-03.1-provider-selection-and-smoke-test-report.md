# BÁO CÁO LLM-03.1 — LỰA CHỌN VÀ KIỂM CHỨNG LLM PROVIDER

**Dự án:** SE2026-T15 — Meeting Minutes Assistant  
**Module:** LLM Service  
**Task:** LLM-03.1 — Provider Selection & Configuration  
**Ngày lập báo cáo:** 07/11/2026  
**Trạng thái:** Đã hoàn thành kiểm chứng provider và JSON Mode; sẵn sàng chuyển sang thiết kế LLM-03.2  
**Repository:** `vietquang8071/se2026-t15`

---

## 1. Tổng quan

### 1.1. Mục tiêu

LLM-03.1 tập trung lựa chọn nhà cung cấp mô hình ngôn ngữ lớn (LLM Provider), xác định chiến lược Structured Output và kiểm chứng khả năng tích hợp API trước khi triển khai Provider Adapter trong LLM-03.2.

Các mục tiêu chính:

1. Lựa chọn LLM Gateway phù hợp với kiến trúc hệ thống.
2. Lựa chọn model miễn phí để thử nghiệm kết nối và Structured Output.
3. Xác định chiến lược tạo dữ liệu JSON và kiểm tra bằng Pydantic.
4. Đề xuất cấu hình provider độc lập với business logic.
5. Kiểm chứng API key, khả năng gọi model và JSON Mode thông qua manual smoke test.
6. Ghi nhận các rủi ro về rate limit, availability, latency và bảo mật.

LLM-03.1 không nhằm đánh giá toàn diện chất lượng trích xuất biên bản hoặc hoàn thiện chức năng Summary/Action Items.

### 1.2. Phạm vi

**Trong phạm vi:**

- Lựa chọn OpenRouter làm LLM Gateway.
- Lựa chọn model phục vụ smoke test.
- Kiểm tra kết nối API bằng request thật.
- Kiểm tra `response_format: {"type": "json_object"}`.
- Đề xuất chiến lược quản lý cấu hình và API key.
- Xác định các vấn đề cần chuyển tiếp sang LLM-03.2.

**Ngoài phạm vi:**

- Triển khai OpenRouter Provider Adapter.
- Tích hợp Provider vào `POST /v1/extractions`.
- Xây dựng Prompt Registry và Candidate Schemas.
- Kiểm thử toàn bộ API Contract v1.
- Đánh giá độ chính xác của Summary và Action Items.
- Lựa chọn model chính thức cho production.

---

## 2. Hiện trạng LLM Service

Theo mã nguồn trên nhánh `develop`, LLM Service hiện có:

| Thành phần | Trạng thái |
|---|---|
| Python 3.12+ và `uv` | Đã cấu hình |
| FastAPI HTTP runtime | Đã triển khai |
| Request/Response schemas bằng Pydantic v2 | Đã triển khai trong LLM-01 |
| API Contract v1 | Đã triển khai ở lớp schema và HTTP |
| `POST /v1/extractions` | Đã có endpoint |
| `ExtractionService` interface | Đã có |
| OpenRouter Provider Adapter | Chưa triển khai |
| Trích xuất bằng LLM thật trong service | Chưa triển khai |

Hiện tại, `apps/llm-service/app/services/extraction.py` có `ExtractionService` protocol và `UnconfiguredExtractionService`. Implementation mặc định chưa thực hiện trích xuất và trả lỗi khi backend chưa được cấu hình.

Do đó, việc kiểm chứng OpenRouter bằng một script độc lập là phù hợp để giảm rủi ro trước khi triển khai LLM-03.2.

**Tài liệu tham chiếu:**

- `docs/llm/llm-service-architecture.md`
- `docs/llm/llm-service-contract.md`
- `docs/implementation-roadmap.md`
- `apps/llm-service/app/services/extraction.py`
- `apps/llm-service/app/core/config.py`

---

## 3. Các quyết định kỹ thuật

### 3.1. Lựa chọn LLM Gateway

**Quyết định: OpenRouter.**

OpenRouter được chọn làm lớp trung gian để LLM Service gửi request đến các mô hình ngôn ngữ.

Lý do lựa chọn:

- Cung cấp API thống nhất cho nhiều model.
- Cho phép thay đổi model thông qua cấu hình.
- Hỗ trợ thử nghiệm các model miễn phí.
- Giảm mức độ phụ thuộc trực tiếp của business logic vào một nhà cung cấp model cụ thể.
- Phù hợp với mục tiêu xây dựng Provider Adapter có thể thay thế.

**Giới hạn:** OpenRouter không bảo đảm tất cả model đều hỗ trợ cùng tham số hoặc có availability tương đương.

### 3.2. Lựa chọn model phục vụ smoke test

Ban đầu, nhóm dự kiến sử dụng:

`google/gemma-4-26b-a4b-it:free`

Tuy nhiên, quá trình kiểm thử gặp giới hạn tài nguyên upstream. Sau khi thử một số model thay thế, model sau đã hoàn thành cả hai bài kiểm thử:

**Model được kiểm chứng thành công:**

`nvidia/nemotron-3.5-super-vl:free`

Model này được chọn làm **smoke-test model đã xác minh** cho LLM-03.1.

Việc lựa chọn model cho production vẫn chưa được quyết định.

### 3.3. Structured Output Strategy

**Quyết định:** Structured Output độc lập với provider, sử dụng Pydantic v2 làm lớp validation bắt buộc.

Chiến lược cụ thể:

- Sử dụng JSON Mode (`json_object`) với model đã kiểm chứng.
- Ưu tiên JSON Schema Mode khi model/endpoint production hỗ trợ và đã qua kiểm thử tương thích.
- LLM sinh Candidate JSON theo prompt và schema nội bộ.
- Python parse, validate và chuyển Candidate JSON thành dữ liệu phù hợp với API Contract v1.
- Không thay đổi public contract chỉ vì thay đổi model.
- Không tự động chuyển sang model trả phí khi model miễn phí gặp lỗi.

**Phân biệt trách nhiệm:**

| Thành phần | Trách nhiệm |
|---|---|
| LLM-01 | Định nghĩa và validate API Contract v1 |
| LLM-02 | Cung cấp HTTP runtime và response contract |
| LLM-03 | Tạo Candidate JSON, chuẩn hóa và kiểm tra dữ liệu trước khi trả response |
| Provider Adapter | Chuyển đổi lời gọi giữa LLM Service và API của provider |

JSON hợp lệ về cú pháp không đồng nghĩa dữ liệu đúng schema hoặc chính xác về nội dung.

### 3.4. Chiến lược Provider Adapter

Provider Adapter được đề xuất là ranh giới kỹ thuật giữa Extraction Service và nhà cung cấp LLM.

Thiết kế phải cho phép:

- Cấu hình model ID bên ngoài business logic.
- Cấu hình Structured Output Mode.
- Chuẩn hóa provider response.
- Chuẩn hóa lỗi authentication, rate limit, timeout và upstream failure.
- Trả metadata cần thiết để truy vết model và token usage.
- Sử dụng Fake Provider cho các bài kiểm thử offline.

Chi tiết interface và implementation sẽ được thực hiện trong LLM-03.2.

### 3.5. Quản lý cấu hình và bảo mật

Các cấu hình đề xuất cho giai đoạn tiếp theo:

| Cấu hình | Mục đích |
|---|---|
| `OPENROUTER_API_KEY` | Xác thực với OpenRouter |
| `OPENROUTER_BASE_URL` | Địa chỉ OpenRouter API |
| `OPENROUTER_MODEL` | Model ID có thể thay đổi |
| `OPENROUTER_STRUCTURED_OUTPUT_MODE` | Chọn JSON Mode hoặc JSON Schema Mode |
| `OPENROUTER_MAX_OUTPUT_TOKENS` | Giới hạn output tokens |
| `OPENROUTER_TEMPERATURE` | Điều chỉnh generation parameters |

Đây là **cấu hình đề xuất**, chưa phải các biến môi trường đã được triển khai trong source code.

Các nguyên tắc bảo mật:

- API key không được hardcode trong source.
- Không commit credentials vào Git.
- Tách `OPENROUTER_API_KEY` khỏi `LLM_SERVICE_TOKEN` dùng để bảo vệ API nội bộ.
- Không ghi raw transcript, API key hoặc Authorization header vào application logs.
- Smoke test chỉ sử dụng transcript giả lập, không chứa thông tin cuộc họp nhạy cảm.

---

## 4. Phương pháp kiểm thử

### 4.1. Môi trường

Smoke test được chạy bằng script Python độc lập:

`apps/llm-service/tests/manual/openrouter_smoke.py`

Lệnh thực hiện:

```bash
uv run --locked python tests/manual/openrouter_smoke.py
```

Script sử dụng Python standard library để gửi HTTP requests đến OpenRouter.

Các đặc điểm kiểm thử:

- Tối đa hai API calls cho một lần chạy.
- Không tự động retry.
- Không tự động chuyển sang model trả phí.
- Dừng nếu O-01 thất bại.
- Chỉ sử dụng dữ liệu synthetic.
- Không kiểm thử toàn bộ LLM-01 Contract v1.

### 4.2. O-01 — API Key & Model Connectivity

**Mục tiêu:** Xác minh API key hoạt động và model có thể xử lý một Chat Completions request.

**Điều kiện thành công:**

- HTTP status bằng 200.
- Response chứa `choices`.
- Model trả nội dung không rỗng.
- Model ID trong response phù hợp với model được yêu cầu.
- Generation kết thúc bình thường.

### 4.3. O-02 — JSON Object Mode

**Mục tiêu:** Xác minh endpoint chấp nhận yêu cầu JSON Mode và có thể tạo dữ liệu JSON phù hợp với cấu trúc tối thiểu.

Request sử dụng:

```json
{
  "response_format": {
    "type": "json_object"
  },
  "provider": {
    "require_parameters": true
  }
}
```

Prompt yêu cầu trích xuất Action Items từ một transcript tổng hợp bằng tiếng Việt.

**Điều kiện thành công:**

- HTTP status bằng 200.
- Response có nội dung.
- Nội dung parse được thành JSON object.
- Có field `action_items` dạng array.
- Có ít nhất một Action Item.
- Source segment IDs phù hợp với fixture kiểm thử.

---

## 5. Quá trình thử nghiệm và các vấn đề gặp phải

Trong quá trình kiểm thử, một số model Free không hoàn thành được smoke test.

| Model | Kết quả quan sát | Phân tích |
|---|---|---|
| `google/gemma-4-26b-a4b-it:free` | HTTP 429 | Google AI Studio giới hạn shared upstream pool |
| `google/gemma-4-31b-it:free` | Chưa có log kết quả xác nhận | Không kết luận thành công/thất bại |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | Request timeout | Không nhận được response hoàn chỉnh trong thời gian chờ |
| `qwen/qwen3.8-27b:free` | HTTP 404 | Không có endpoint khả dụng khi kiểm tra |
| `nvidia/nemotron-3.5-super-vl:free` | HTTP 200 cho O-01 và O-02 | Hoàn thành smoke test |

### 5.1. Lỗi HTTP 429

Thông báo OpenRouter ghi nhận:

```text
provider_name: Google AI Studio
limit_source: upstream_provider_shared_pool
provider_error_code: 429
```

Nguyên nhân được xác định là tài nguyên dùng chung ở upstream provider đã chạm giới hạn.

Đây không phải bằng chứng về lỗi API key hoặc cấu hình Python.

### 5.2. Request Timeout

Với Nemotron 3 Ultra Free, request không hoàn thành trong thời gian chờ của script.

Nguyên nhân cụ thể chưa được xác nhận. Các khả năng bao gồm thời gian xử lý dài, hàng đợi upstream hoặc sự cố kết nối.

### 5.3. HTTP 404

Qwen3.8 27B Free trả HTTP 404. Việc kiểm tra endpoint trước đó cho thấy model không có endpoint khả dụng tại thời điểm kiểm tra.

Kết quả cho thấy việc model xuất hiện trong catalog không bảo đảm model có thể phục vụ request thực tế.

### 5.4. Bài học rút ra

- Model Free có thể thay đổi availability theo thời điểm.
- API key hợp lệ không bảo đảm mọi model đều phục vụ được.
- Cần phân biệt lỗi xác thực, giới hạn tài nguyên và timeout.
- Không nên hardcode một model vào business logic.
- Provider Adapter cần chuẩn hóa các lỗi upstream.
- Kiểm thử provider thật phải tách khỏi CI mặc định.

---

## 6. Kết quả smoke test thành công

**Model:** `nvidia/nemotron-3.5-super-vl:free`

### 6.1. Kết quả O-01

| Tiêu chí | Kết quả |
|---|---|
| HTTP status | `200` |
| Requested model | `nvidia/nemotron-3.5-super-vl:free` |
| Returned model | `nvidia/nemotron-3.5-super-vl:free` |
| Finish reason | `stop` |
| Input tokens | 24 |
| Output tokens | 43 |
| Response không rỗng | Có |
| **Kết quả O-01** | **PASS** |

**Nhận xét:** API key và model đã hoạt động trong lần kiểm thử này. Request được xử lý thành công, trả về nội dung và kết thúc bình thường.

### 6.2. Kết quả O-02

| Tiêu chí | Kết quả |
|---|---|
| HTTP status | `200` |
| Requested model | `nvidia/nemotron-3.5-super-vl:free` |
| Returned model | `nvidia/nemotron-3.5-super-vl:free` |
| Finish reason | `stop` |
| Input tokens | 101 |
| Output tokens | 477 |
| JSON parsing | Thành công |
| Số Action Items | 1 |
| Source segment IDs | `['seg-001']` |
| **Kết quả O-02** | **PASS** |

**Nhận xét:** Endpoint chấp nhận request có cấu hình JSON Mode và trả về nội dung có thể parse thành JSON, đáp ứng cấu trúc tối thiểu được yêu cầu trong smoke test.

Kết quả này xác nhận khả năng tích hợp kỹ thuật ban đầu, nhưng chưa chứng minh model luôn tuân thủ JSON Mode ở mọi trường hợp.

### 6.3. Tổng hợp

| Test ID | Mục tiêu | Trạng thái |
|---|---|---|
| O-01 | Kiểm chứng API key và model | **PASS** |
| O-02 | Kiểm chứng JSON Object Mode | **PASS** |

**Kết luận kiểm thử:** Cả hai mục tiêu kiểm chứng bắt buộc đã đạt với model Nemotron 3.5 Super VL Free.

---

## 7. Đánh giá rủi ro và giới hạn

### 7.1. Availability

Các lỗi HTTP 429, HTTP 404 và timeout cho thấy việc sử dụng Free endpoint có rủi ro về khả năng phục vụ.

**Hướng xử lý:** Sử dụng Fake Provider trong CI, giới hạn số lần gọi API thật và lựa chọn model production dựa trên độ ổn định đã đo được.

### 7.2. Structured Output

O-02 chỉ kiểm chứng JSON parsing và cấu trúc tối thiểu.

Chưa kiểm chứng:

- Toàn bộ Pydantic Candidate Schema.
- `ExtractionResponse` theo Contract v1.
- Các validation invariants.
- Trường hợp JSON không hợp lệ hoặc bị cắt.
- Trường hợp thiếu hoặc sai evidence.

**Hướng xử lý:** Triển khai schema validation ở LLM-03.3–03.5 và bổ sung offline tests.

### 7.3. Chất lượng trích xuất

Smoke test chỉ sử dụng một transcript ngắn với một Action Item.

Chưa có bằng chứng để đánh giá:

- Độ chính xác của Meeting Summary.
- Độ đầy đủ của Action Items.
- Độ chính xác khi nhận diện owner.
- Khả năng xử lý deadline tương đối.
- Khả năng truy vết nội dung về transcript.
- Chất lượng tiếng Việt trên các cuộc họp dài.

**Hướng xử lý:** Đánh giá trên bộ transcript và gold artifacts có kiểm chứng ở các giai đoạn tiếp theo.

### 7.4. Hiệu năng và chi phí

O-02 sử dụng 101 input tokens và 477 output tokens.

Số liệu của một request chưa đủ để đánh giá hiệu suất tổng thể.

**Hướng xử lý:** Theo dõi latency, token usage, tỷ lệ lỗi và chi phí trên nhiều trường hợp kiểm thử có kiểm soát trước khi lựa chọn production model.

### 7.5. Quyền riêng tư

Transcript có thể chứa dữ liệu nội bộ và thông tin cá nhân của người tham gia cuộc họp.

**Hướng xử lý:** Kiểm tra chính sách xử lý/lưu giữ dữ liệu của provider trước khi sử dụng transcript thật; không log nội dung nhạy cảm hoặc gửi dữ liệu chưa được phép sử dụng.

---

## 8. Đánh giá mức độ hoàn thành LLM-03.1

| Hạng mục | Trạng thái | Ghi chú |
|---|---|---|
| Lựa chọn LLM Gateway | Hoàn thành | OpenRouter |
| Xác định model smoke test | Hoàn thành | Nemotron 3.5 Super VL Free |
| Thống nhất Structured Output Strategy | Hoàn thành ở mức thiết kế | JSON Mode + Pydantic validation |
| Kiểm thử O-01 | PASS | HTTP 200 |
| Kiểm thử O-02 | PASS | JSON parse thành công |
| Đề xuất cấu hình provider | Đã đề xuất | Chưa triển khai |
| Đề xuất bảo mật credentials | Đã xác định nguyên tắc | Cần áp dụng khi triển khai |
| Provider Adapter | Chưa triển khai | Thuộc LLM-03.2 |
| Production model | Chưa chốt | Không thuộc điều kiện hoàn thành smoke test |
| Full Contract v1 extraction | Chưa triển khai | Thuộc các task tiếp theo |

**Đánh giá:** LLM-03.1 đã hoàn thành phần lựa chọn gateway, chiến lược structured generation và kiểm chứng kỹ thuật bắt buộc. Các cấu hình cụ thể của runtime và chính sách xử lý lỗi sẽ được hoàn thiện khi triển khai Provider Adapter.

---

## 9. Định hướng triển khai LLM-03.2

### 9.1. Mục tiêu

Triển khai OpenRouter Adapter để LLM Service có thể gọi model thông qua một interface thống nhất, độc lập với logic của API và các business modules.

### 9.2. Các công việc đề xuất

1. Định nghĩa `LLMProvider` protocol.
2. Xây dựng `OpenRouterAdapter`.
3. Tích hợp các cấu hình OpenRouter vào `Settings`.
4. Hỗ trợ JSON Mode và thiết kế khả năng bổ sung JSON Schema Mode.
5. Chuẩn hóa response metadata và token usage.
6. Xử lý lỗi HTTP, rate limit, timeout và provider failure.
7. Xây dựng `FakeProvider` phục vụ offline testing.
8. Viết unit tests và integration tests cho adapter, sử dụng mocked responses.
9. Bảo đảm không gọi provider thật trong CI mặc định.

### 9.3. Nguyên tắc triển khai

- Không hardcode model ID trong Extraction Service.
- Không thay đổi Contract v1 của LLM-01 nếu không có yêu cầu versioning riêng.
- Không làm lộ API key hoặc raw transcript trong log.
- Không coi JSON hợp lệ là kết quả trích xuất đã được kiểm chứng ngữ nghĩa.
- Không tự động fallback sang model trả phí.
- Phân biệt provider error với lỗi validation và lỗi business logic.

### 9.4. Các file dự kiến bị ảnh hưởng

- `apps/llm-service/app/providers/` — Provider interface và OpenRouter Adapter.
- `apps/llm-service/app/core/config.py` — Provider configuration.
- `apps/llm-service/app/services/extraction.py` — Tích hợp provider vào service ở giai đoạn phù hợp.
- `apps/llm-service/tests/` — Fake Provider và adapter tests.

Danh sách trên là kế hoạch, không phải các thay đổi đã thực hiện.

---

## 10. Kết luận

LLM-03.1 đã đạt mục tiêu kiểm chứng khả năng tích hợp OpenRouter với một model miễn phí hỗ trợ JSON Mode.

Kết quả quan trọng nhất:

1. **OpenRouter được lựa chọn** làm LLM Gateway của dự án.
2. **`nvidia/nemotron-3.5-super-vl:free` đã PASS O-01 và O-02.**
3. **JSON Mode kết hợp Pydantic Validation** được lựa chọn làm chiến lược Structured Output ban đầu.
4. **API Contract v1 của LLM-01 được giữ nguyên**, không phụ thuộc vào model.
5. Các rủi ro về rate limit, timeout, model availability và bảo mật đã được nhận diện.
6. Đã có đủ bằng chứng kỹ thuật ban đầu để chuyển sang **LLM-03.2 — Provider Interface & OpenRouter Adapter**.

Kết quả LLM-03.1 chứng minh **tính khả thi của việc kết nối và nhận JSON**, chưa chứng minh chất lượng trích xuất hoặc mức độ sẵn sàng của sản phẩm trong production.

**Trạng thái đề xuất:** Hoàn thành LLM-03.1 ở phạm vi provider selection và smoke test; tiếp tục LLM-03.2 theo kế hoạch phát triển.

---

## 11. Tài liệu tham khảo nội bộ

1. `docs/product-description.md`
2. `docs/feature-overview.md`
3. `docs/implementation-roadmap.md`
4. `docs/llm/llm-service-architecture.md`
5. `docs/llm/llm-service-contract.md`
6. `apps/llm-service/app/core/config.py`
7. `apps/llm-service/app/services/extraction.py`
8. Log thực nghiệm O-01 và O-02 do người thực hiện cung cấp.

**Ghi chú:** Báo cáo được xây dựng từ tài liệu, mã nguồn đã đối chiếu và kết quả manual smoke test được cung cấp. Chưa có kiểm thử end-to-end của LLM Service với OpenRouter Adapter.