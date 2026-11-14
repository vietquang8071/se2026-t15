# LLM Service — Meeting Minutes Assistant

LLM Service là dịch vụ Python/FastAPI trong dự án **SE2026-T15 — Meeting Minutes Assistant**, chịu trách nhiệm sử dụng mô hình ngôn ngữ lớn (LLM) để trích xuất thông tin có cấu trúc từ transcript cuộc họp.

## 1. Chức năng

LLM Service hiện đã triển khai:

- **Tích hợp OpenRouter:** Gọi mô hình LLM thông qua OpenRouter API.
- **Quản lý Prompt:** Sử dụng các prompt có phiên bản để trích xuất thông tin.
- **Meeting Summary:** Tạo dữ liệu tóm tắt nội dung cuộc họp.
- **Action Items:** Trích xuất công việc, người phụ trách và thông tin thời hạn khi có căn cứ.
- **Structured Output:** Parse và kiểm tra cấu trúc dữ liệu do LLM trả về.
- **API Authentication:** Bảo vệ API bằng Bearer Token.
- **Error Handling:** Xử lý lỗi request, provider và timeout.
- **Offline Testing:** Kiểm thử bằng Fake Provider, không cần API key thật.

**Trạng thái hiện tại:** Đã hoàn thành pipeline trích xuất nội bộ cho Meeting Summary và Action Items. Chức năng xác minh bằng chứng và xuất kết quả qua public API chưa hoàn thành. Endpoint extraction mặc định vẫn trả HTTP 503 cho đến khi tích hợp verification.

## 2. Yêu cầu môi trường

- Python 3.12 trở lên.
- [uv](https://docs.astral.sh/uv/) để quản lý dependencies.
- OpenRouter API key (chỉ cần khi gọi provider thật).
- Docker (tùy chọn).

## 3. Cài đặt và chạy local

### Bước 1: Di chuyển vào thư mục service

Từ thư mục gốc repository:

```bash
cd apps/llm-service
```

### Bước 2: Cài đặt dependencies

```bash
uv sync --locked --extra test
```

### Bước 3: Cấu hình môi trường

Sao chép file cấu hình mẫu:

```bash
cp .env.example .env
```

Tạo token để xác thực API nội bộ:

```bash
openssl rand -hex 32
```

Cập nhật trong `.env`:

```dotenv
LLM_SERVICE_TOKEN=<token-vua-tao>
OPENROUTER_API_KEY=<openrouter-api-key>
```

`LLM_SERVICE_TOKEN` dùng để xác thực request gửi đến LLM Service.

`OPENROUTER_API_KEY` dùng để gọi OpenRouter. Có thể để trống nếu chỉ chạy server hoặc kiểm thử offline.

Không commit file `.env` chứa thông tin bí mật lên GitHub.

### Bước 4: Khởi động service

```bash
uv run --locked --env-file .env \
  uvicorn app.main:app \
  --host 127.0.0.1 \
  --port 8000
```

Service chạy tại:

`http://127.0.0.1:8000`

### Bước 5: Kiểm tra hoạt động

```bash
curl http://127.0.0.1:8000/health
```

Kết quả mong đợi:

```json
{
  "status": "ok",
  "service": "llm-service",
  "contract_version": "1.0"
}
```

## 4. API hiện có

| Method | Endpoint | Mô tả |
|---|---|---|
| GET | `/health` | Kiểm tra trạng thái HTTP service |
| POST | `/v1/extractions` | API trích xuất thông tin cuộc họp |
| GET | `/openapi.json` | Xem OpenAPI specification |

`POST /v1/extractions` yêu cầu Bearer Token. Trong phiên bản hiện tại, endpoint mặc định trả HTTP 503 vì verified extraction chưa được kích hoạt.

## 5. Chạy kiểm thử

Chạy toàn bộ bộ kiểm thử:

```bash
uv run --locked --extra test pytest -q
```

Chạy riêng từng nhóm:

```bash
# Unit tests
uv run --locked --extra test pytest -q tests/unit

# Integration tests
uv run --locked --extra test pytest -q tests/integration

# Contract tests
uv run --locked --extra test pytest -q tests/contract
```

Các bài kiểm thử tự động không yêu cầu kết nối OpenRouter thật.

### Kiểm thử OpenRouter thủ công

Sau khi cấu hình `OPENROUTER_API_KEY`:

```bash
uv run --locked --env-file .env \
  python tests/manual/openrouter_smoke.py
```

Script này thực hiện tối đa hai API calls tới OpenRouter và có thể sử dụng quota của tài khoản. Model trong script hiện được khai báo cố định.

## 6. Chạy bằng Docker

Từ thư mục gốc repository:

### Build image

```bash
docker build \
  -f apps/llm-service/Dockerfile \
  -t se2026-llm-service \
  apps/llm-service
```

### Chạy container

```bash
docker run --rm \
  --env-file apps/llm-service/.env \
  -e LLM_SERVICE_HOST=0.0.0.0 \
  -p 127.0.0.1:8000:8000 \
  se2026-llm-service
```

Kiểm tra:

```bash
curl http://127.0.0.1:8000/health
```

## 7. Tài liệu liên quan

- [Kiến trúc LLM Service](../../docs/llm/llm-service-architecture.md)
- [API Contract](../../docs/llm/llm-service-contract.md)
- [Tổng quan LLM-03](../../docs/llm/report/llm-03/llm-03-overview.md)
- [Báo cáo LLM-03.4](../../docs/llm/report/llm-03/llm-03.4-extraction-service-report.md)