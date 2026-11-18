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

**Trạng thái LLM-03:** Đã hoàn tất triển khai và đánh giá; đang chờ review PR cuối và merge vào `develop`. `create_app()` mặc định lắp ghép `VerifiedExtractionService`; `POST /v1/extractions` gọi service này sau khi xác thực và kiểm tra request. Khi cấu hình hợp lệ và provider hoạt động, service có thể trả Summary và Action Items theo Contract v1. HTTP 503 không phải phản hồi mặc định; mã này và các lỗi có cấu trúc khác có thể xuất hiện khi backend/provider gặp sự cố.

### Pipeline trích xuất đã triển khai

```text
POST /v1/extractions
    -> Xác thực Bearer token
    -> Kiểm tra ExtractionRequest (Contract v1)
    -> Preflight và dựng prompt có phiên bản
    -> Gọi OpenRouter để tạo candidate
    -> Parse candidate có cấu trúc
    -> Chiếu candidate sang dữ liệu extraction nội bộ
    -> Kiểm tra source references
    -> Xác minh evidence bằng một lượt gọi provider riêng
    -> Áp dụng temporal/review safeguards
    -> Dựng ExtractionResponse (Contract v1)
```

Mọi `source_segment_id` được phát hành phải trỏ tới segment của transcript trong request hiện tại; thời điểm nguồn được dẫn xuất từ segment đó. Lượt xác minh evidence là một lần sinh riêng từ provider ngoài lần sinh candidate. Claim không được hỗ trợ có thể bị từ chối hoặc lọc bỏ theo từng safeguard: ví dụ Summary overview không được xác minh sẽ làm request thất bại, còn topic/action không được hỗ trợ có thể bị loại; owner, deadline, priority hoặc context không chắc chắn được giữ thận trọng, xóa giá trị không được hỗ trợ và/hoặc đánh dấu cần review. Deadline tương đối không được tự chuyển thành ngày chính xác nếu chưa có cơ sở. Lỗi request, provider, evidence, parse và timeout được trả bằng error response có cấu trúc.

### Phạm vi module

| Trạng thái | Module |
|---|---|
| Được hỗ trợ | `meeting_summary`, `action_items` |
| Chưa được hỗ trợ trong LLM-03 | `decision_log`, `open_issues`, `follow_up_items`, `timeline_events` |

Yêu cầu trích xuất một module chưa hỗ trợ sẽ bị từ chối; service không trả kết quả thành công giả chỉ vì schema của module đó tồn tại. Bộ phân giải thời gian đầy đủ cho ngày tương đối thuộc LLM-04.

## 2. Yêu cầu môi trường

- Python 3.12 trở lên.
- [uv](https://docs.astral.sh/uv/) để quản lý dependencies.
- OpenRouter API key (cần khi thực hiện extraction qua provider thật).
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

`LLM_SERVICE_TOKEN` là Bearer token nội bộ để xác thực caller của LLM Service và phải được cấu hình trước khi service khởi động. `OPENROUTER_API_KEY` là credential riêng dùng bởi adapter để gọi OpenRouter; không dùng key này làm token nội bộ. Cả hai giá trị đều là bí mật và không được đưa vào README, log hoặc Git.

Các tên và giá trị mặc định chính trong `Settings`/`.env.example`:

| Biến môi trường | Mặc định trong cấu hình | Mục đích |
|---|---|---|
| `LLM_SERVICE_TOKEN` | Không có; bắt buộc khi khởi động | Xác thực Bearer nội bộ |
| `OPENROUTER_API_KEY` | Không có; cần khi gọi provider | Xác thực OpenRouter |
| `OPENROUTER_MODEL` | `nvidia/nemotron-3.5-super-vl:free` | Model do service gửi cho gateway |
| `OPENROUTER_STRUCTURED_OUTPUT_MODE` | `json_object` (`text` cũng hợp lệ) | Chế độ output cấu trúc |
| `OPENROUTER_MAX_OUTPUT_TOKENS` | `2048` | Giới hạn token đầu ra mỗi lần sinh |
| `LLM_SERVICE_REQUEST_TIMEOUT_SECONDS` | `180` | Timeout tổng cho extraction HTTP request |
| `LLM_SERVICE_PROVIDER_TIMEOUT_SECONDS` | `60` | Timeout cho mỗi lần gọi provider |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Base URL của gateway |
| `OPENROUTER_TEMPERATURE` | `0` | Tham số sinh |
| `OPENROUTER_REQUIRE_PARAMETERS` | `true` | Yêu cầu route hỗ trợ các tham số gửi đi |

`.env.example` đặt `LLM_SERVICE_HOST=127.0.0.1`; nếu không đặt biến này, giá trị mặc định trong `Settings` là `0.0.0.0`. Giá model/config có thể khác giữa môi trường; model DeepSeek trong benchmark không thay đổi mặc định được khai báo trong repository.

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

`GET /health` chỉ xác nhận process đang phục vụ; endpoint này không kiểm tra kết nối provider. `GET /openapi.json` trả OpenAPI specification.

`POST /v1/extractions`:

- Yêu cầu `Authorization: Bearer ...` với token cấu hình qua `LLM_SERVICE_TOKEN`.
- Nhận JSON `ExtractionRequest`, Contract v1.
- Khi thành công, trả `ExtractionResponse`, Contract v1.
- Khi authentication, request validation, provider, evidence verification, timeout hoặc bước xử lý khác thất bại, trả error envelope có cấu trúc. HTTP 503 chỉ là một lỗi vận hành có thể xảy ra, không phải kết quả mặc định.

Ví dụ gửi request tổng hợp có sẵn của `case-001` (chạy từ `apps/llm-service`). Hãy nạp `LLM_SERVICE_TOKEN` vào môi trường shell bằng phương thức an toàn trước khi chạy; không ghi token trực tiếp vào lệnh hay shell history:

```bash
curl -sS http://127.0.0.1:8000/v1/extractions \
  -H "Authorization: Bearer ${LLM_SERVICE_TOKEN:?Set LLM_SERVICE_TOKEN first}" \
  -H "Content-Type: application/json" \
  --data-binary @evaluation/datasets/llm-03.7-evaluation/cases/case-001/llm-request.json
```

Request extraction thật có thể kích hoạt một hoặc nhiều lượt gọi OpenRouter và phát sinh chi phí. Không dùng request này nếu chưa chủ động chấp thuận việc gọi provider.

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

Script này gọi OpenRouter trực tiếp tối đa hai lần với model khai báo cố định trong script. Đây chỉ là kiểm tra kết nối/JSON tối thiểu của adapter; nó không đi qua FastAPI hay pipeline trích xuất. Request thật có thể phát sinh chi phí. Không chạy nếu chưa chủ động chấp thuận.

### Đánh giá LLM-03.7

Hướng dẫn đầy đủ về xác thực dataset, các chế độ Smoke/Development/Holdout, human review và chấm điểm offline nằm trong [Evaluation README](evaluation/README.md). Quy trình gồm:

1. Xác thực 16 case offline trước khi dùng dữ liệu:

   ```bash
   uv run --locked --extra test python -m evaluation.runner validate-dataset
   ```

2. Chạy Smoke, sau đó hoàn tất cổng semantic review thủ công.
3. Chạy Development và Holdout bằng runner riêng, với ủy quyền rõ ràng cho từng chế độ; không dùng review Smoke thay cho quyền Development/Holdout.
4. Review response đã lưu rồi chấm offline bằng `evaluation.runner`.

Không có live inference trong pytest. Kiểm thử tự động dùng fake provider hoặc HTTP mock; chất lượng model trong benchmark được chấm riêng từ DeepSeek response đã lưu và human review.

Kết quả benchmark cuối đã ghi nhận:

| Chỉ số | Development | Holdout |
|---|---:|---:|
| Số case được đánh giá | 10 | 6 |
| Tuân thủ Contract v1 | 100% | 100% |
| Action Item F1 | 100% | 94.12% |

Benchmark dùng model `deepseek/deepseek-v4.1-flash-1017`. Tổng chi phí USD 0.03 do chủ dự án báo cáo; metadata runner không có số tiền billing để xác minh độc lập. Kết quả test đầy đủ mới nhất được báo cáo cục bộ là **746 passed**; đây không phải xác nhận CI độc lập.

## 6. Giới hạn đã biết

- Chỉ `meeting_summary` và `action_items` được triển khai; bốn module còn lại chưa được hỗ trợ trong LLM-03.
- Bộ phân giải đầy đủ cho ngày tương đối thuộc LLM-04. Có lỗi phân giải ngày ISO trong `case-008`.
- `case-015` có một Action Item dự đoán thừa; một số cụm deadline chưa được giữ nguyên hoàn toàn so với transcript/gold.
- Benchmark gồm 16 transcript synthetic ngắn; chưa chứng minh độ chính xác trên dữ liệu cuộc họp thực hoặc mức sẵn sàng production.
- Audio Service, Backend và Frontend chưa được nối thành luồng end-to-end hoàn chỉnh.

## 7. Chạy bằng Docker

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

## 8. Tài liệu liên quan

- [Kiến trúc LLM Service](../../docs/llm/llm-service-architecture.md)
- [API Contract](../../docs/llm/llm-service-contract.md)
- [Tổng quan LLM-03](../../docs/llm/report/llm-03/llm-03-overview.md)
- [Báo cáo LLM-03.4](../../docs/llm/report/llm-03/llm-03.4-extraction-service-report.md)
- [Hướng dẫn evaluation](evaluation/README.md)
- [Báo cáo đánh giá LLM-03.7.2](../../docs/llm/report/llm-03/llm-03.7.2-deepseek-smoke-and-development-evaluation-report.md)
