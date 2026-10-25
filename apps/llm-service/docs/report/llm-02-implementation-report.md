# Báo cáo triển khai LLM-02

## 1. Task Information

- **Task ID:** LLM-02 — FastAPI Runtime, Health, Authentication & Configuration.
- **Branch:** `feature/llm-fastapi-runtime`.
- **Base branch:** `develop` tại `5126cc26` (fast-forward từ `origin/develop`).
- **Implementation status:** Hoàn tất trong phạm vi LLM-02; extraction thật được để lại cho LLM-03.

## 2. Implementation Summary

- Tạo FastAPI app factory, lifespan validation và các endpoint `GET /health`, `POST /v1/extractions`, `GET /openapi.json`.
- Extraction endpoint nhận `ExtractionRequest`, yêu cầu Bearer token so sánh bằng `hmac.compare_digest`, rồi gọi service qua dependency injection. Service mặc định luôn trả `503 PROVIDER_CONFIGURATION_ERROR`; không sinh kết quả giả.
- Thêm settings từ environment, error mapping theo `ErrorEnvelope`, xử lý request validation/JSON lỗi và giới hạn body theo byte kể cả khi `Content-Length` thiếu hoặc khai báo thấp.
- Unexpected HTTP exceptions được đổi thành lỗi nội bộ chung; không log exception text/traceback. Lỗi lifespan vẫn được truyền ra để cấu hình thiếu làm startup fail rõ ràng.
- OpenAPI sinh từ Pydantic models, công bố Bearer security scheme và các error responses.
- Thêm Dockerfile Python 3.12+, cài production dependencies từ `uv.lock`, chạy Uvicorn dưới non-root user và nhận cấu hình host/port từ environment.

## 3. Files Changed

- `app/main.py`, `app/api/`, `app/core/`, `app/services/`: application factory, routes, auth/config dependencies, HTTP errors/body boundary và extraction service abstraction.
- `tests/integration/test_runtime.py`: API, auth, body-limit, error, OpenAPI, dependency override và lifespan tests.
- `pyproject.toml`, `uv.lock`: FastAPI, Uvicorn, Pydantic Settings và TestClient dependencies.
- `Dockerfile`: image runtime độc lập.
- `docs/prompt/llm-02-fastapi-runtime.md`: prompt nhiệm vụ đã lưu.
- `docs/report/llm-02-implementation-report.md`: báo cáo này.

## 4. Test Results

Các lệnh Python được chạy từ `apps/llm-service/`:

```bash
PYTHONDONTWRITEBYTECODE=1 UV_PROJECT_ENVIRONMENT=/tmp/se-llm02-venv uv run --locked --extra test pytest -q -p no:cacheprovider
uv lock --check
```

- **Pytest:** 134 passed, 0 failed, 0 skipped (23 API tests và toàn bộ LLM-01 contract suite).
- **Lockfile:** `uv lock --check` thành công.
- **Whitespace:** `git diff --check` thành công.
- **OpenAPI:** kiểm tra bằng TestClient; request/response/error schemas, security scheme, paths và status responses có mặt.
- **Docker:** `docker build --tag se-llm-service:llm02 .` thành công. Container tạm khởi động với token giả, `/health` trả đúng JSON; container đã được dừng.
- Lần chạy pytest từ repository root không áp dụng `pythonpath` của project và dừng ở bước import. Chạy lại từ project root như lệnh trên cho kết quả đầy đủ.

## 5. Acceptance Criteria

| Tiêu chí | Trạng thái |
|---|---|
| Branch mới từ `develop` đã fast-forward | Passed |
| FastAPI chạy trên Python 3.12+ | Passed |
| `GET /health` đúng response, không cần auth và không lộ secrets | Passed |
| `POST /v1/extractions` dùng `ExtractionRequest` | Passed |
| Skeleton không trả fake `200 completed` | Passed |
| `/openapi.json` sinh từ models và mô tả các endpoint | Passed |
| Bearer auth bắt buộc, token rỗng/sai bị từ chối | Passed |
| Token không xuất hiện trong response hoặc startup logs đã kiểm tra | Passed |
| Environment settings và numeric constraints được kiểm tra | Passed |
| Error response dùng `ErrorEnvelope` | Passed |
| Validation, contract version, empty transcript và JSON lỗi được map đúng | Passed |
| Body limit kiểm tra header và streamed body | Passed |
| Extraction dependency có thể override bằng fake service | Passed |
| Dockerfile build được và container phục vụ health | Passed |
| `pyproject.toml` và `uv.lock` nhất quán | Passed |
| LLM-01 regression tests vẫn chạy | Passed |
| Lifecycle startup/shutdown được TestClient kiểm tra | Passed |
| Prompt và report được lưu trong repository | Passed |
| Thay đổi task nằm trong `apps/llm-service/` | Passed |
| Không commit, push hoặc merge | Passed |

## 6. Known Issues & Risks

- Chưa có provider hoặc extraction pipeline. Cho đến khi LLM-03 thay service abstraction bằng implementation thật, mọi request đã xác thực trả `503 PROVIDER_CONFIGURATION_ERROR`, `retryable: false`.
- `LLM_SERVICE_MAX_REQUEST_BYTES` có default 10 MiB để runtime có giới hạn an toàn; con số này chưa được nhóm benchmark/phê duyệt và nên được cấu hình theo deployment.
- Contract yêu cầu `application/json` nhưng chưa chốt status cho Content-Type sai/thiếu; runtime hiện ánh xạ nhất quán thành `400 VALIDATION_ERROR`.
- Contract chưa định nghĩa error code/status cho route hoặc HTTP method không tồn tại; các lỗi định tuyến `404/405` vẫn theo response mặc định của FastAPI cho đến khi nhóm chốt envelope tương ứng.
- `LLM_SERVICE_PROVIDER_TIMEOUT_SECONDS` đã có trong settings; việc áp dụng nó cho provider call chờ LLM-03. `LLM_SERVICE_REQUEST_TIMEOUT_SECONDS` đang giới hạn extraction use case.
- LLM-01 validation debt F1–F4 vẫn deferred, không được sửa trong task này.
- Repository đã có `packages/database/prisma/migrations/` untracked trước task; giữ nguyên và không sửa.

## 7. Next Steps

- Review implementation và mở PR vào `develop` khi được yêu cầu.
- Chốt provider/model, credential handling và transcript retention policy.
- Ưu tiên xử lý validation debt F1–F4 theo quyết định của nhóm.
- Tiếp tục LLM-03 — Provider Adapter & Summary/Actions Extraction.

Tài liệu liên quan: [API contract](../llm-service-contract.md), [architecture](../llm-service-architecture.md), [prompt LLM-02](../prompt/llm-02-fastapi-runtime.md).
