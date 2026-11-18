# LLM-03.2 — Provider Interface và OpenRouter Adapter

## 1. Mục tiêu và phạm vi

LLM-03.2 bổ sung lớp sinh nội dung bất đồng bộ, độc lập với nghiệp vụ trích xuất và API của nhà cung cấp. OpenRouter là adapter thật đầu tiên; fake provider phục vụ kiểm thử không cần mạng. Đây là nền tảng hạ tầng, chưa phải pipeline tạo biên bản.

Không thay đổi API Contract v1, endpoint, `UnconfiguredExtractionService` hay script smoke test LLM-03.1. Không thêm prompt, candidate schema, extraction orchestration, evidence verification, temporal resolution, database hoặc queue.

## 2. Kiến trúc và interface

```text
ExtractionService tương lai
    -> LLMProvider.generate(ProviderRequest)
        -> OpenRouterAdapter -> Chat Completions
        -> FakeProvider      -> dữ liệu/lỗi định sẵn
    <- ProviderResult hoặc typed provider exception
```

`LLMProvider` là Python protocol với `async generate(request: ProviderRequest) -> ProviderResult`. `ProviderRequest` có messages với role `system`, `user`, `assistant`, mode `text` hoặc `json_object`, maximum output tokens và temperature. Ba tham số generation có thể để `None` để sử dụng defaults trong settings; giá trị request được ưu tiên khi có.

`ProviderResult` gồm content, model ID provider trả về, finish reason và `ProviderUsage | None`. Usage chứa `input_tokens` và `output_tokens`; khi provider không gửi usage, giá trị là `None`. Khi có usage, cả hai số phải là số nguyên không âm. Provider models không chứa trường nghiệp vụ meeting hay response công khai.

Adapter xác thực envelope và yêu cầu assistant content không rỗng, finish reason `stop`. `length` là truncation; các finish reason khác chưa được coi là thành công. Adapter không parse JSON trong content: JSON candidate sai cú pháp vẫn là dữ liệu cần lớp extraction sau kiểm tra. Điều này không có nghĩa candidate hợp lệ theo business schema.

## 3. Cấu hình và bảo mật

Settings đọc environment khi runtime, không tự đọc `.env`. Các biến mới:

| Biến | Giá trị mặc định | Ý nghĩa |
|---|---|---|
| `OPENROUTER_API_KEY` | Không có | `SecretStr`; bắt buộc, không rỗng và hợp lệ để đặt trong HTTP header khi gọi adapter thật. |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | HTTPS base URL; không chấp nhận userinfo, query, fragment hoặc whitespace. |
| `OPENROUTER_MODEL` | `nvidia/nemotron-3.5-super-vl:free` | Model smoke-test có thể thay bằng cấu hình; không mặc định chuyển model khác. |
| `OPENROUTER_STRUCTURED_OUTPUT_MODE` | `json_object` | `json_object` hoặc `text`. |
| `OPENROUTER_MAX_OUTPUT_TOKENS` | `2048` | Số nguyên dương. |
| `OPENROUTER_TEMPERATURE` | `0` | Số hữu hạn từ 0 đến 2. |
| `OPENROUTER_REQUIRE_PARAMETERS` | `true` | Yêu cầu provider hỗ trợ các tham số generation. |

`LLM_SERVICE_TOKEN` vẫn riêng biệt. Khóa OpenRouter thiếu hoặc không hợp lệ gây `ProviderConfigurationError` trước khi gửi HTTP; không cần khóa khi tạo FastAPI với extraction service mặc định. Giá trị khóa được Pydantic che trong biểu diễn settings. Exception của adapter không đưa raw body, transcript, key hoặc Authorization header vào thông điệp.

Adapter dùng `LLM_SERVICE_PROVIDER_TIMEOUT_SECONDS` cho cả HTTP timeout và deadline tổng của một generation. `LLM_SERVICE_REQUEST_TIMEOUT_SECONDS` vẫn thuộc HTTP extraction runtime. Client `httpx.AsyncClient` được tạo và đóng cho mỗi lần gọi, kể cả khi lỗi hoặc bị hủy; transport factory injectable tạo transport riêng cho mỗi lần gọi, kể cả khi chạy đồng thời. Adapter không retry, không theo redirect và không gửi danh sách model fallback. Lỗi HTTP client được chuyển đổi sau khi rời khối xử lý exception, tránh giữ exception gốc có thể chứa request nhạy cảm trong `__context__`.

JSON Object Mode gửi `response_format.type = json_object`. Payload luôn đặt `provider.allow_fallbacks = false` và gửi `provider.require_parameters` theo cấu hình. OpenRouter vẫn chọn provider ban đầu theo routing của gateway. Tham khảo [Chat Completions](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request?explorer=true) và [provider routing](https://openrouter.ai/docs/guides/routing/provider-selection).

## 4. Phân loại lỗi

Các mã sau là ánh xạ dự kiến cho giai đoạn tích hợp sau; LLM-03.2 chưa thay FastAPI exception handlers.

| Điều kiện | Exception | Ánh xạ Contract v1 dự kiến |
|---|---|---|
| Credential/cấu hình không hợp lệ; HTTP 401/403 | `ProviderConfigurationError` | 503 `PROVIDER_CONFIGURATION_ERROR` |
| HTTP 404 | `ProviderUnavailableError` | 502 `PROVIDER_FAILURE` |
| HTTP 429 | `ProviderRateLimitError` | 503 `PROVIDER_RATE_LIMIT` |
| HTTP client hoặc deadline timeout | `ProviderTimeoutError` | 504 `PROVIDER_TIMEOUT` |
| HTTP khác không thành công, lỗi kết nối, envelope HTTP 200 chứa `error` | `ProviderFailureError` | 502 `PROVIDER_FAILURE` |
| JSON envelope, choices, model hoặc usage sai | `ProviderMalformedResponseError` | 502 `PROVIDER_FAILURE` |
| Assistant content rỗng/không dùng được | `ProviderEmptyContentError` | 502 `PROVIDER_FAILURE` |
| Finish reason `length` | `ProviderTruncatedResponseError` | 502 `PROVIDER_FAILURE` |

`Retry-After` được chuyển thành số giây dương hữu hạn khi có thể đọc dạng số hoặc HTTP-date và không quá 24 giờ; giá trị khác bị bỏ qua. Thông tin này chỉ là gợi ý cho caller, adapter không tự retry. Lỗi `ProviderFailureError` mặc định không khẳng định có thể retry.

## 5. Fake Provider

`tests/fakes/provider.py` triển khai cùng chữ ký `generate`, trả một `ProviderResult` định sẵn hoặc ném một typed error định sẵn và ghi lại request. Fake không cần credential hay network. Có thể cấu hình content rỗng hoặc JSON sai cú pháp để kiểm thử lớp gọi; fake không xác nhận chúng hợp lệ về nghiệp vụ. Envelope sai được kiểm tra tại OpenRouter adapter, không phải giả vờ là `ProviderResult` thành công.

## 6. Tệp thêm và thay đổi

**Thêm:**

- `apps/llm-service/app/providers/__init__.py`
- `apps/llm-service/app/providers/protocol.py`
- `apps/llm-service/app/providers/models.py`
- `apps/llm-service/app/providers/errors.py`
- `apps/llm-service/app/providers/openrouter.py`
- `apps/llm-service/tests/fakes/__init__.py`
- `apps/llm-service/tests/fakes/provider.py`
- `apps/llm-service/tests/unit/providers/test_provider_models.py`
- `apps/llm-service/tests/unit/providers/test_provider_errors.py`
- `apps/llm-service/tests/unit/providers/test_fake_provider.py`
- `apps/llm-service/tests/unit/providers/test_openrouter.py`
- Báo cáo này.

**Thay đổi:** `apps/llm-service/app/core/config.py`, `apps/llm-service/pyproject.toml`, `apps/llm-service/uv.lock`. `httpx` là dependency runtime trực tiếp; `httpx2` test dependency hiện có vẫn phục vụ FastAPI test client. Pytest pythonpath được bổ sung `tests` để import fake.

## 7. Kết quả kiểm thử

Chạy từ `apps/llm-service/`:

```bash
uv sync --locked --extra test
uv run --locked --extra test pytest -q
```

Kết quả thực tế: sync thành công; **230 passed, 0 failed**. Bộ test gồm regression Contract v1 và FastAPI, cùng các test provider dùng `httpx.MockTransport`. Các trường hợp gồm cấu hình/model, mode, metadata/usage, HTTP 401/403/404/429/5xx, timeout, lỗi kết nối, response lỗi/rỗng/bị cắt, thiếu key, masking, redirect, số lần gọi và đóng transport. Kiểm thử cũng kiểm tra exception không giữ HTTP exception nhạy cảm trong context và adapter có thể gọi nhiều lần hoặc đồng thời với transport riêng.

Kiểm tra bổ sung chạy cùng pytest qua Python với `socket.socket.connect` và `socket.create_connection` bị thay bằng hàm từ chối kết nối: **230 passed, 0 failed**. Đây là kiểm tra chặn kết nối socket trong process test, không phải cấu hình firewall hệ điều hành.

Sandbox của môi trường thực thi không khởi tạo được loopback; các lệnh `uv` được chạy ngoài sandbox qua cơ chế quyền của môi trường. Không gọi OpenRouter thật trong các lần chạy này. Smoke test LLM-03.1 vẫn chỉ chạy thủ công và kết quả của nó không phải kết quả kiểm thử mới cho adapter.

## 8. Giới hạn và bước tiếp theo

- Adapter chưa được kiểm tra live với OpenRouter trong milestone này; availability model, enforcement phía gateway và chất lượng output chưa được xác nhận lại.
- Chỉ `text` và `json_object` được triển khai; JSON Schema Mode chưa được triển khai. Một generation có content hợp lệ không bảo đảm đúng JSON, schema hoặc facts.
- Chưa có HTTP mapping cho các exception provider, chưa nối adapter vào endpoint và chưa tạo `ExtractionResponse` thật. Chỉ `stop` được chấp nhận là finish reason thành công; usage có một trong hai trường token nhưng thiếu trường còn lại bị coi là envelope sai.
- LLM-03.3 cần xây dựng prompt versioning và candidate schemas, sau đó parse/validate candidate một cách độc lập với provider. LLM-03.4 cần xây dựng concrete ExtractionService và dependency injection; LLM-03.5 cần xử lý error mapping, output validation và evidence theo Contract v1.
- Client được tạo cho mỗi generation, ưu tiên vòng đời rõ ràng; connection pooling xuyên nhiều lần gọi có thể được đánh giá ở milestone vận hành sau.
