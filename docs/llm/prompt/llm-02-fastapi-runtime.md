# Task: LLM-02 — FastAPI Runtime, Health, Authentication & Configuration

Bạn là **Senior Python Backend Engineer, Software Architect và AI Backend Engineer**, chịu trách nhiệm triển khai LLM Service cho dự án **SE2026-T15 — Meeting Minutes Assistant**.

Repository: `vietquang8071/se2026-t15`

## 1. Mục tiêu

Triển khai **LLM-02 — FastAPI Runtime, Health, Auth & Configuration** dựa trên implementation LLM-01 đã được merge vào `develop`.

**Objective:** Xây dựng HTTP runtime cho LLM Service, có thể chạy và deploy độc lập với Web Backend và Audio Processing Service.

**Priority:** P0

**Complexity:** Medium

**Dependencies:** LLM-01 — Contract Models & Fixtures

**Roadmap mapping:** P01-01 và P11-04

Các deliverables bắt buộc:

1. FastAPI application.
2. `GET /health`.
3. `POST /v1/extractions` skeleton.
4. `GET /openapi.json`.
5. Bearer token authentication.
6. Application settings và environment configuration.
7. Dependency injection cho extraction service.
8. Standardized HTTP error handling.
9. Dockerfile.
10. Cập nhật `pyproject.toml` và `uv.lock`.
11. Automated API tests sử dụng FastAPI TestClient.
12. Lưu prompt vào `apps/llm-service/docs/prompt/`.
13. Tạo báo cáo Markdown trong `apps/llm-service/docs/report/`.

**Quan trọng:** Đây là task xây dựng HTTP runtime, chưa phải task triển khai extraction pipeline hoặc LLM provider integration.

---

# 2. Git Workflow — Bắt buộc thực hiện đầu tiên

Phải tuân thủ `CONTRIBUTING.md`.

## Step 1 — Inspect Repository

Trước khi thay đổi bất kỳ file nào, kiểm tra:

```bash
git status
git branch --show-current
git branch -a
git log -5 --oneline
```

Đảm bảo working tree không chứa các thay đổi có nguy cơ bị mất khi switch branch.

Đặc biệt chú ý thư mục có thể đang untracked:

`packages/database/prisma/migrations/`

Không tự ý xóa, reset, clean, stash hoặc commit các file không liên quan.

Nếu có thay đổi gây trở ngại cho việc chuyển branch an toàn, dừng và báo cáo.

## Step 2 — Switch to develop

Chuyển về branch `develop`:

```bash
git switch develop
```

Cập nhật từ remote:

```bash
git pull --ff-only origin develop
```

Không sử dụng `git reset --hard`, force pull hoặc tự động rebase.

Nếu xảy ra conflict hoặc không thể fast-forward, dừng và báo cáo.

## Step 3 — Create Feature Branch

Tạo branch mới từ `develop` đã được cập nhật:

```bash
git switch -c feature/llm-fastapi-runtime
```

Nếu branch đã tồn tại, không overwrite hoặc tự ý xóa branch.

Nếu đã có GitHub Issue tương ứng, tuân thủ convention về Issue ID trong `CONTRIBUTING.md`.

Xác nhận branch đang làm việc:

```bash
git branch --show-current
```

**Tuyệt đối không code trực tiếp trên `develop` hoặc `main`.**

Không commit, push, merge hoặc tạo Pull Request nếu chưa được yêu cầu.

---

# 3. Repository Analysis — Bắt buộc đọc trước khi code

Đọc đầy đủ các file sau.

## Primary Specifications

- `apps/llm-service/docs/llm-service-contract.md`
- `apps/llm-service/docs/llm-service-architecture.md`

Tập trung vào các phần:

**LLM Service Contract:**

- Section 2 — HTTP API.
- Section 3 — Request Schema.
- Section 4 — Response Schema.
- Section 8 — Error Contract.
- Section 10 — Contract Tests & Acceptance Criteria.

**LLM Service Architecture:**

- Section 2 — System Context & Deployment.
- Section 3 — Internal Processing Pipeline.
- Section 7 — Reliability & Security.
- Section 9 — Proposed Project Structure.
- Section 10 — LLM-02 Task Breakdown.

## Existing Source Code

Đọc implementation LLM-01 hiện tại:

- `apps/llm-service/app/schemas/common.py`
- `apps/llm-service/app/schemas/request.py`
- `apps/llm-service/app/schemas/response.py`
- `apps/llm-service/app/schemas/temporal.py`
- `apps/llm-service/app/schemas/errors.py`
- `apps/llm-service/pyproject.toml`
- `apps/llm-service/uv.lock`
- `apps/llm-service/tests/contract/`
- `apps/llm-service/tests/fixtures/`

Đọc thêm:

- `CONTRIBUTING.md`
- `docs/implementation-roadmap.md`
- `docs/feature-overview.md`
- `AGENTS.md`, nếu có.
- Cấu hình Docker và workspace hiện tại.

## Analysis Requirements

Trước khi triển khai:

1. Xác nhận LLM-01 đã tồn tại trên `develop`.
2. Xác định các Pydantic models có thể tái sử dụng.
3. Xác định HTTP error mapping tương ứng với existing `ErrorEnvelope`.
4. Xác định cấu trúc FastAPI tối thiểu.
5. Xác định những dependencies cần bổ sung.
6. Lập implementation plan ngắn gọn.

Không viết lại Pydantic schemas đã tồn tại nếu không cần thiết.

Không tự sửa các lỗi ngoài phạm vi LLM-02.

---

# 4. Required Project Structure

Cấu trúc dự kiến sau khi hoàn thành:

```text
apps/llm-service/
├── app/
│   ├── main.py
│   ├── api/
│   │   ├── routes.py
│   │   └── dependencies.py
│   ├── core/
│   │   ├── config.py
│   │   └── errors.py
│   └── schemas/
│       ├── common.py
│       ├── request.py
│       ├── response.py
│       ├── temporal.py
│       └── errors.py
├── tests/
│   ├── contract/
│   ├── integration/
│   └── fixtures/
├── docs/
│   ├── prompt/
│   │   └── llm-02-fastapi-runtime.md
│   ├── report/
│   │   └── llm-02-implementation-report.md
│   ├── llm-service-contract.md
│   └── llm-service-architecture.md
├── pyproject.toml
├── uv.lock
└── Dockerfile
```

Chỉ tạo những file cần thiết cho LLM-02.

Có thể bổ sung module nhỏ nếu thực sự cần thiết để giữ separation of concerns.

Không tạo các directories hoặc files rỗng chỉ để khớp sơ đồ.

---

# 5. FastAPI Application

Implement `app/main.py`.

## Requirements

- Python 3.12+.
- FastAPI.
- Pydantic v2.
- ASGI application có thể chạy bằng Uvicorn.
- Application factory hoặc cấu trúc tương đương để hỗ trợ dependency injection và testing.
- Graceful startup/shutdown bằng lifespan khi cần.
- Không kết nối database.
- Không khởi tạo LLM provider thật.
- Không tạo background job hoặc message queue.
- Không thực hiện network request khi import app.

Route handlers phải mỏng, chỉ xử lý HTTP concerns và gọi service layer thông qua dependency injection.

Không viết extraction business logic trực tiếp trong FastAPI route.

Tránh global mutable state không cần thiết.

---

# 6. GET /health

Implement:

```http
GET /health
```

Expected response:

```json
{
  "status": "ok",
  "service": "llm-service",
  "contract_version": "1.0"
}
```

Requirements:

- HTTP 200 khi application runtime hoạt động bình thường.
- Không yêu cầu Bearer token nếu endpoint chỉ được expose trong trusted/internal environment.
- Không gọi LLM provider.
- Không truy cập PostgreSQL.
- Không gọi Web Backend hoặc Audio Processing Service.
- Không trả API key, configuration secrets hoặc environment variables.
- Không trả raw exception details.

Health check chỉ chứng minh service process hoạt động, không phải chứng minh extraction provider đã sẵn sàng.

Viết integration tests cho endpoint này.

---

# 7. POST /v1/extractions — Skeleton

Implement:

```http
POST /v1/extractions
```

Đây là endpoint chính của LLM Service theo API Contract v1.

## Request Model

Tái sử dụng:

`ExtractionRequest`

từ LLM-01.

## Response Model

Tái sử dụng:

`ExtractionResponse`

và error schemas đã triển khai.

## Requirements

- Endpoint nhận JSON request đúng schema.
- Request được validate qua Pydantic.
- Yêu cầu Bearer authentication.
- OpenAPI khai báo đúng request/response models.
- Route chỉ gọi extraction service abstraction.
- Sử dụng dependency injection để có thể inject fake extraction service trong tests.
- Không phụ thuộc Web Backend hoặc Audio Processing Service đang chạy.

## Quan trọng — Chưa implement extraction

LLM-02 không triển khai provider hoặc business extraction.

Vì vậy:

- Không gọi OpenAI API.
- Không tạo fake summary.
- Không sinh Action Items giả.
- Không trả HTTP 200 `completed` với dữ liệu hardcoded.
- Không tự tạo logic TemporalResolver.
- Không tạo semantic EvidenceVerifier.
- Không biến endpoint thành mock API ở production.

Nếu chưa có extraction implementation, endpoint phải trả failure rõ ràng.

**Phương án cho LLM-02:** Khi provider/extraction implementation chưa được cấu hình, sử dụng error envelope hiện có với `503 PROVIDER_CONFIGURATION_ERROR`, `retryable: false`, và thông báo trung tính rằng extraction backend chưa sẵn sàng. Đây là trạng thái tạm thời của LLM-02, chỉ phù hợp khi chưa có functional provider configured.

Không tự phát minh error code mới, không sử dụng `INTERNAL_ERROR` để che giấu lỗi và không khai báo extraction thành công.

Ghi rõ temporary behavior này trong implementation report.

Thiết kế extraction service dependency sao cho LLM-03 có thể thay skeleton bằng implementation thật mà không phải rewrite API route.

Nếu nhận thấy phương án placeholder gây mâu thuẫn không thể giải quyết với contract, ghi nhận cụ thể và đề xuất lựa chọn thay thế; không tự sửa tài liệu contract.

---

# 8. Dependency Injection

Thiết kế dependency injection đơn giản, testable.

Mục tiêu:

- Route không phụ thuộc trực tiếp provider SDK.
- Có thể thay extraction implementation trong tests.
- Có thể bổ sung provider adapter ở LLM-03.
- Không tạo service registry hoặc framework phức tạp.

Có thể định nghĩa một interface/protocol tối thiểu cho extraction use case.

Expected behavior:

```text
HTTP Request
    ↓
Authentication
    ↓
Request Validation
    ↓
FastAPI Route
    ↓
Extraction Service Dependency
    ↓
Not-ready response (LLM-02)
```

Ở LLM-03:

```text
FastAPI Route
    ↓
Extraction Service
    ↓
LLM Provider Adapter
    ↓
Validated ExtractionResponse
```

Không implement phần LLM Provider Adapter ở task hiện tại.

---

# 9. Bearer Token Authentication

Implement service-to-service Bearer authentication.

Header:

```http
Authorization: Bearer <LLM_SERVICE_TOKEN>
```

## Requirements

- Token được lấy từ environment configuration.
- Không hardcode token.
- Không commit token thật.
- Token thiếu → HTTP 401.
- Token sai → HTTP 401.
- Authentication failure theo `ErrorEnvelope`.
- Không trả token trong response hoặc logs.
- Sử dụng constant-time comparison khi so sánh token.
- Không cho phép empty token bypass authentication.
- Không tắt authentication trong production.
- Tests sử dụng token giả lập.

Không yêu cầu OAuth2, JWT, RBAC hoặc hệ thống user management ở MVP.

Chỉ implement authentication tối thiểu cho service-to-service communication.

Đảm bảo `/health` không vô tình lộ secrets.

OpenAPI phải mô tả security scheme phù hợp cho extraction endpoint.

---

# 10. Application Configuration

Implement configuration trong:

`app/core/config.py`

Sử dụng Pydantic Settings hoặc phương án tương đương, ưu tiên giải pháp đơn giản và type-safe.

Configuration đề xuất:

- `LLM_SERVICE_TOKEN`
- `LLM_SERVICE_HOST`
- `LLM_SERVICE_PORT`
- `LLM_SERVICE_LOG_LEVEL`
- `LLM_SERVICE_MAX_REQUEST_BYTES`
- `LLM_SERVICE_REQUEST_TIMEOUT_SECONDS`
- `LLM_SERVICE_PROVIDER_TIMEOUT_SECONDS`

Kiểm tra và áp dụng constraints hợp lệ cho các giá trị số.

## Security Requirements

- Không in secrets khi startup.
- Không đưa secrets vào exception messages.
- Không hardcode production credentials.
- Configuration invalid phải fail rõ ràng.
- Không tự fallback sang development token mặc định.
- Tests có thể inject test settings.
- Không bắt buộc LLM provider API key ở LLM-02 vì chưa tích hợp provider.

Không thêm các cấu hình chỉ phục vụ LLM-03 nếu chưa có nhu cầu thực tế.

---

# 11. HTTP Error Handling

Implement error handling phù hợp với `llm-service-contract.md`, Section 8.

Tái sử dụng `ErrorEnvelope` từ LLM-01.

Ví dụ:

```json
{
  "statusCode": 400,
  "code": "VALIDATION_ERROR",
  "message": "Yêu cầu trích xuất không hợp lệ.",
  "request_id": "req-001",
  "retryable": false,
  "retry_after_seconds": null,
  "errors": []
}
```

## Required mappings

| Scenario | HTTP | Contract code |
|---|---:|---|
| Invalid request field | 400 | `VALIDATION_ERROR` |
| Unsupported contract version | 400 | `UNSUPPORTED_CONTRACT_VERSION` |
| Missing/invalid bearer token | 401 | `AUTHENTICATION_REQUIRED` |
| Request payload too large | 413 | `PAYLOAD_TOO_LARGE` |
| Empty transcript | 422 | `EMPTY_TRANSCRIPT` |
| Extraction backend chưa cấu hình | 503 | `PROVIDER_CONFIGURATION_ERROR` |
| Unexpected internal failure | 500 | `INTERNAL_ERROR` |

FastAPI mặc định có thể trả 422 cho request validation. Phải custom handler để ánh xạ các validation errors thông thường thành HTTP 400 theo contract.

LLM-01 đã có dedicated validation codes như:

- `empty_transcript`
- `unsupported_contract_version`

Hãy tận dụng những mã này khi chuyển thành HTTP error envelope.

Yêu cầu:

- Không trả raw Pydantic error objects trực tiếp.
- Không làm lộ request body, transcript text hoặc stack trace.
- Không để malformed JSON trả error format khác contract.
- Sử dụng consistent error serialization.
- `request_id` có thể null nếu request không có ID hợp lệ.
- Không suy đoán `request_id` từ nội dung không hợp lệ.

Cần kiểm tra Content-Type theo API Contract. Nếu contract hiện tại chưa quy định HTTP status rõ cho trường hợp sai Content-Type, ghi nhận và xử lý nhất quán mà không tự sửa contract.

Đối với các lỗi bất thường mà Python hoặc Pydantic chưa bắt được, bảo đảm chúng không làm lộ thông tin nhạy cảm.

---

# 12. Request Body Limits

Implement request body size limit ở HTTP layer.

Requirements:

- Giá trị limit lấy từ settings.
- Vượt limit trả HTTP 413 `PAYLOAD_TOO_LARGE`.
- Không đọc toàn bộ payload vượt giới hạn vào bộ nhớ nếu có thể tránh.
- Không log raw request body.
- Không tự động truncate transcript.
- Không triển khai token budgeting hoặc transcript windowing thuộc LLM-07.

Kiểm thử cả trường hợp có `Content-Length` và trường hợp không thể tin cậy vào header này.

Nếu cần ASGI middleware, giữ implementation tối thiểu và không phá vỡ request streaming.

---

# 13. OpenAPI Documentation

FastAPI phải expose:

```http
GET /openapi.json
```

Requirements:

- OpenAPI sinh trực tiếp từ code và Pydantic models.
- Có schema `ExtractionRequest`.
- Có schema `ExtractionResponse`.
- Có schema `ErrorEnvelope`.
- Có Bearer security scheme.
- `POST /v1/extractions` có đúng HTTP method và path.
- `GET /health` được document đúng.
- Error responses được khai báo với status codes phù hợp.
- Không expose secrets hoặc internal configurations.

Chưa cần tạo OpenAPI YAML thủ công.

Sử dụng generated OpenAPI làm nguồn kiểm chứng giữa implementation và contract.

---

# 14. Docker & Runtime

Tạo:

`apps/llm-service/Dockerfile`

Requirements:

- Python 3.12+.
- Image phù hợp chạy FastAPI/Uvicorn.
- Build được từ service directory.
- Cài dependencies theo `pyproject.toml` và `uv.lock`.
- Không cài test dependencies trong production image nếu không cần.
- Không copy `.env` hoặc credentials vào image.
- Chạy bằng non-root user khi khả thi.
- Cấu hình host/port rõ ràng.
- Có thể khởi động HTTP server bằng Uvicorn.
- Process nhận SIGTERM và shutdown graceful.
- Không kết nối PostgreSQL.
- Không khởi động Redis, Celery hoặc queue.

Nếu Docker runtime không khả dụng trong môi trường hiện tại, không tuyên bố Docker build thành công; ghi rõ việc kiểm thử chưa thể thực hiện.

Không sửa root `docker-compose.yml` trong task này.

---

# 15. Dependencies

Cập nhật:

- `apps/llm-service/pyproject.toml`
- `apps/llm-service/uv.lock`

Chỉ thêm dependencies cần cho LLM-02, ví dụ:

- FastAPI.
- Uvicorn.
- Pydantic Settings nếu được sử dụng.
- HTTPX/TestClient dependencies phục vụ testing.

Giữ Pydantic v2 và các dependencies của LLM-01.

Không thêm:

- OpenAI SDK.
- LangChain.
- LangGraph.
- Redis.
- Celery.
- SQLAlchemy.
- Prisma client.
- Audio processing libraries.

Không nâng cấp dependencies không liên quan nếu không cần thiết.

Bảo đảm chạy được với lockfile.

---

# 16. Automated Testing

Sử dụng `pytest` và `FastAPI TestClient`.

Đặt các tests mới trong:

`apps/llm-service/tests/integration/`

Không sửa hoặc xóa các tests đã có của LLM-01.

## Required test cases

### Health Check

- `/health` trả HTTP 200.
- Response đúng `status`, `service`, `contract_version`.
- Không yêu cầu provider.
- Không yêu cầu database.
- Không để lộ secrets.

### Authentication

- Missing Bearer token → 401.
- Invalid Bearer token → 401.
- Valid Bearer token → authentication thành công.
- Empty token không được chấp nhận.
- Secret không xuất hiện trong error response.
- `/health` hoạt động theo auth policy đã quy định.

### Extraction Endpoint

- Endpoint tồn tại.
- HTTP method đúng.
- Valid request được validate.
- Invalid request trả 400.
- Unsupported contract version trả 400.
- Empty transcript trả 422.
- Oversized payload trả 413.
- Khi extraction implementation chưa có, không trả fake `200 completed`.
- Skeleton trả structured failure phù hợp.
- Có thể override extraction dependency bằng fake service trong tests.
- Fake service trong tests có thể tạo response hợp lệ theo LLM-01 schemas.

### Error Handling

- Error envelope đúng schema.
- Error codes và HTTP statuses tương ứng.
- Invalid JSON được xử lý.
- Không trả stack trace hoặc secret.
- Internal exception được xử lý an toàn.
- Request validation errors không dùng FastAPI default response format.

### OpenAPI

- `/openapi.json` trả HTTP 200.
- Có đúng endpoint paths.
- Có Pydantic request/response schemas.
- Có error schemas.
- Có Bearer security scheme.
- Không mô tả sai các chức năng chưa triển khai.

### Application Lifecycle

- Application khởi tạo và shutdown trong TestClient.
- Settings có thể được inject/override cho tests.
- Không cần external API credentials.
- Không gọi provider hoặc database ở startup.

---

# 17. Regression Tests & Known Issues

LLM-01 đã được merge với một số vấn đề đang được theo dõi:

- F1: Owner null chưa bắt buộc đánh dấu review.
- F2: Temporal uncertainty chưa được truyền đầy đủ lên artifact cha.
- F3: Cross-request validator chưa kiểm tra chính xác source timestamp.
- F4: Numeric overflow trong parsing có thể dẫn đến exception không mong muốn.

**Không tự sửa F1–F4 trong LLM-02.**

Nếu các vấn đề này ảnh hưởng tới HTTP boundary, hãy:

1. Bảo đảm runtime không làm lộ stack trace hoặc dữ liệu nhạy cảm.
2. Thêm HTTP-level tests phù hợp nếu cần.
3. Ghi nhận deferred risks trong implementation report.
4. Không sửa business validation của LLM-01 nếu chưa được phê duyệt.

Đặc biệt, không che giấu lỗi bằng cách trả một successful extraction response.

---

# 18. Save This Prompt — Mandatory

Bắt buộc lưu prompt nhiệm vụ vào:

`apps/llm-service/docs/prompt/llm-02-fastapi-runtime.md`

Requirements:

- Lưu nội dung prompt đầu vào đầy đủ, bằng tiếng Việt.
- Giữ nguyên objectives, scope, requirements và restrictions.
- Có thể bổ sung metadata như task ID, branch và ngày thực hiện.
- Không ghi secrets hoặc dữ liệu nhạy cảm.
- Không thay thế hoặc overwrite prompt của LLM-01.

File prompt phải được tạo trên feature branch và xuất hiện trong danh sách changed files.

---

# 19. Implementation Report — Mandatory

Sau khi hoàn thành implementation và testing, tạo:

`apps/llm-service/docs/report/llm-02-implementation-report.md`

**Báo cáo phải ngắn gọn, bằng tiếng Việt, phản ánh kết quả thực tế.**

Cấu trúc bắt buộc:

## 1. Task Information

- Task ID: LLM-02.
- Task name.
- Branch name.
- Base branch.
- Implementation status.

## 2. Implementation Summary

Tóm tắt ngắn gọn:

- FastAPI runtime.
- Health endpoint.
- Extraction endpoint skeleton.
- Authentication.
- Settings.
- Error handling.
- OpenAPI.
- Docker support.

## 3. Files Changed

Liệt kê các file đã tạo hoặc sửa cùng mục đích.

## 4. Test Results

Ghi rõ:

- Commands executed.
- Number of tests passed/failed/skipped.
- FastAPI TestClient results.
- OpenAPI validation results.
- Docker build status.
- Các bước chưa thể kiểm thử.

Không tự bịa test results.

## 5. Acceptance Criteria

Đối chiếu từng acceptance criterion với trạng thái:

- Passed.
- Failed.
- Not tested.
- Deferred.

## 6. Known Issues & Risks

Bao gồm:

- Các phần chưa có provider thật.
- Temporary behavior của extraction skeleton.
- Những hạn chế còn tồn tại từ LLM-01.
- Mọi contract discrepancy nếu có.

## 7. Next Steps

Nêu các việc còn lại trước LLM-03:

- Review LLM-02 PR.
- Chốt provider/model.
- Xử lý contract validation debt theo ưu tiên.
- Chuẩn bị LLM-03 — Provider Adapter & Summary/Actions Extraction.

Không triển khai LLM-03.

Báo cáo phải được lưu vào repository, không chỉ in trong terminal.

---

# 20. Execution Workflow

Thực hiện theo thứ tự:

### Phase A — Git Preparation

1. Inspect working tree.
2. Switch to `develop`.
3. Fast-forward pull.
4. Create feature branch.
5. Confirm branch.

### Phase B — Analysis

1. Read contract và architecture.
2. Inspect LLM-01 code/tests.
3. Identify reusable schemas.
4. Identify necessary dependencies.
5. Present a concise implementation plan.

### Phase C — Save Prompt

1. Tạo `docs/prompt/` nếu cần.
2. Lưu prompt vào `llm-02-fastapi-runtime.md`.
3. Không sửa prompt LLM-01.

### Phase D — Implementation

1. Implement settings.
2. Implement FastAPI application.
3. Implement health route.
4. Implement authentication dependency.
5. Implement error handling.
6. Implement extraction service abstraction và route skeleton.
7. Implement request body limit.
8. Configure OpenAPI.
9. Create Dockerfile.
10. Update dependencies và lockfile.

### Phase E — Testing

1. Run existing LLM-01 contract tests.
2. Run new FastAPI integration tests.
3. Check generated OpenAPI.
4. Verify error serialization.
5. Run syntax/import checks.
6. Run dependency-lock checks.
7. Test Docker build/startup nếu môi trường hỗ trợ.
8. Review any failing tests và chỉ sửa trong phạm vi LLM-02.

### Phase F — Report

1. Tạo `docs/report/`.
2. Viết `llm-02-implementation-report.md`.
3. Ghi đúng kết quả tests thực tế.
4. Liệt kê deferred issues.
5. Liệt kê implementation limitations.

### Phase G — Final Review

Kiểm tra:

- Current branch đúng.
- Không có thay đổi ngoài `apps/llm-service/`.
- Không có secrets.
- Không có generated cache hoặc virtual environment bị đưa vào Git.
- LLM-01 tests không bị xóa hoặc vô hiệu hóa.
- Không có provider integration ngoài phạm vi.
- Không có database hoặc queue.
- Prompt và report đều tồn tại.
- Không commit/push.

---

# 21. Acceptance Criteria

Task LLM-02 chỉ được coi là hoàn thành khi:

- [ ] Branch mới được tạo từ `develop` đã cập nhật.
- [ ] FastAPI application chạy trên Python 3.12+.
- [ ] `GET /health` trả đúng response.
- [ ] `POST /v1/extractions` tồn tại và sử dụng `ExtractionRequest`.
- [ ] Endpoint không trả fake extraction success.
- [ ] `/openapi.json` phản ánh Pydantic Contract v1.
- [ ] Bearer authentication hoạt động đúng.
- [ ] Secrets không xuất hiện trong response/logs.
- [ ] Settings được validate.
- [ ] FastAPI errors được serialize theo `ErrorEnvelope`.
- [ ] Request validation errors được map đúng.
- [ ] Body size limit được kiểm tra.
- [ ] Dependency injection có thể được override trong tests.
- [ ] Dockerfile tồn tại và phù hợp Python runtime.
- [ ] `pyproject.toml` và `uv.lock` được cập nhật nhất quán.
- [ ] Integration tests được viết và chạy.
- [ ] Regression tests LLM-01 vẫn pass.
- [ ] Application khởi động và shutdown an toàn.
- [ ] Prompt được lưu trong `docs/prompt/`.
- [ ] Báo cáo Markdown được lưu trong `docs/report/`.
- [ ] Không thay đổi source code hoặc configurations ngoài phạm vi.
- [ ] Không commit, push hoặc merge.

Nếu tiêu chí chưa đạt, phải ghi rõ trạng thái và lý do trong báo cáo.

---

# 22. Strict Scope Restrictions

Bạn chỉ được chỉnh sửa các file cần thiết thuộc LLM-02 trong:

`apps/llm-service/`

Không được:

- Sửa `apps/web/`.
- Sửa `apps/api/`.
- Sửa Audio Processing Service.
- Sửa Prisma schema/migrations.
- Sửa root Docker Compose.
- Sửa tài liệu architecture/contract đã được merge.
- Tự sửa F1–F4.
- Implement LLM provider thật.
- Implement Summary/Action Items extraction.
- Implement TemporalResolver.
- Implement EvidenceVerifier.
- Implement transcript windowing.
- Commit hoặc push.
- Tạo Pull Request hoặc merge.

Nếu có yêu cầu nằm ngoài phạm vi, ghi lại trong report hoặc báo cáo blocker thay vì tự thực hiện.

---

# 23. Final Response Format

Sau khi hoàn thành, trả lời bằng tiếng Việt với các mục:

### 1. Git Status
- Initial branch.
- Base branch.
- Current feature branch.
- Commit/push status.

### 2. Implementation Summary
- Những thành phần đã triển khai.
- Các endpoint.
- Authentication và configuration.

### 3. Files Changed
- Liệt kê đường dẫn.

### 4. Test Results
- Commands.
- Passed/failed/skipped.
- Docker/OpenAPI status.

### 5. Contract Compliance
- Những phần đã đáp ứng.
- Những điểm chưa hoàn thành.

### 6. Known Issues
- Các vấn đề còn tồn tại.
- Deferred work.

### 7. Documentation
Xác nhận đã tạo:

- `apps/llm-service/docs/prompt/llm-02-fastapi-runtime.md`
- `apps/llm-service/docs/report/llm-02-implementation-report.md`

### 8. Next Steps
- Review code.
- Tạo PR sau khi được yêu cầu.
- Chuẩn bị LLM-03.

---

# Final Instruction

Hãy triển khai **LLM-02 — FastAPI Runtime, Health, Authentication & Configuration** trên feature branch mới từ `develop`.

Ưu tiên:

**Contract correctness → Security → Runtime reliability → Testability → Simplicity.**

Bắt buộc lưu prompt trước khi triển khai và tạo implementation report sau khi thực hiện.

Không overengineer, không triển khai task tiếp theo và không tự động commit/push/merge.
