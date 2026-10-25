# Meeting API Contract — Create & Detail

- **Phiên bản:** 1.0 — 25/10/2026
- **Task liên quan:** P00-04, P02-01, P02-02 trong [Implementation Roadmap](implementation-roadmap.md).
- **Trạng thái:** contract cho bước triển khai tiếp theo; hai endpoint meeting bên dưới **chưa được implement**. Lần thay đổi này chỉ thêm tài liệu.

## 1. Phạm vi và quy ước

API đầu tiên chỉ tạo meeting và xem chi tiết. Chưa định nghĩa list/update/delete, upload, xử lý AI, speaker hay export trong contract này. MVP tổng thể vẫn giữ đủ sáu module; Markdown + copy summary là đầu ra export đã chốt, PDF/audit history là phần mở rộng.

| Method | Route | Thành công | Chức năng |
|---|---|---|---|
| POST | `/api/meetings` | `201 Created` | Tạo và lưu metadata meeting |
| GET | `/api/meetings/{id}` | `200 OK` | Đọc metadata đã lưu |

- API local mặc định: `http://localhost:3001`; web: `http://localhost:3000`. Port API có thể thay bằng `API_PORT` theo [README](../README.md).
- Request POST dùng `Content-Type: application/json` (có thể kèm `charset=utf-8`); request/response dùng UTF-8. Response trả trực tiếp object, không bọc thêm `data`.
- Field metadata JSON dùng `snake_case`. NestJS ánh xạ sang tên field Prisma ở mục 5; không trả nguyên object Prisma để tránh đổi tên field hoặc định dạng ngày ngoài ý muốn.
- `GET /health` hiện có nằm ngoài prefix `/api` và giữ nguyên response hiện tại. Khi thêm meeting, không tự đổi đường dẫn health.
- Chưa có tài khoản, email hoặc token trong request meeting của bản local. Phân quyền khi deploy là task riêng.

## 2. POST `/api/meetings`

### 2.1. Request và validation

Body phải là một JSON object. Chỉ chấp nhận ba field dưới đây; field không biết, kể cả `anchorDate`, `id` hoặc `created_at`, trả `400 VALIDATION_ERROR`. Không tự ép số/boolean/null thành chuỗi. Validation ở server là bắt buộc dù frontend đã kiểm tra.

| Field | Kiểu | Bắt buộc | Quy tắc |
|---|---|---|---|
| `title` | string | Có | Trim hai đầu; sau trim dài 1–200 ký tự |
| `anchor_date` | string | Có | Đúng `YYYY-MM-DD`, năm 0001–9999 và là ngày tồn tại trong lịch |
| `participants` | string[] | Không | Bỏ qua thì mặc định `[]`; tối đa 50 tên; mỗi tên trim hai đầu, dài 1–100 ký tự |

Độ dài chuỗi tính bằng Unicode code point sau trim. Giữ nguyên dấu tiếng Việt, chữ hoa/thường và khoảng trắng bên trong tên/title. Không tự gộp các tên trùng nhau; giữ thứ tự nhập vì hai người có thể cùng tên. Participants hiện chỉ là tên hiển thị, chưa phải danh tính người nói đã xác thực.

`participants: []` hợp lệ; `null`, chuỗi phân cách bằng dấu phẩy, phần tử không phải string hoặc tên chỉ có khoảng trắng đều không hợp lệ. Frontend bỏ dòng tên chưa nhập trước khi gửi; backend vẫn từ chối phần tử rỗng nếu nhận được.

`anchor_date` không được chứa giờ, timezone hay khoảng trắng và không được tự chuẩn hóa ngày không tồn tại. Ví dụ `2026-02-30`, `2026-2-03`, `25/10/2026` và `2026-10-25T00:00:00Z` đều bị từ chối. Chấp nhận ngày quá khứ/tương lai hợp lệ; thiếu ngày không được lấy mặc định ngày máy chạy.

Request đầy đủ, dùng tên giả cho ví dụ:

```json
{
  "title": "Họp demo MVP",
  "anchor_date": "2026-10-25",
  "participants": ["Thành viên A", "Thành viên B"]
}
```

Request tối thiểu:

```json
{
  "title": "Họp demo MVP",
  "anchor_date": "2026-10-25"
}
```

### 2.2. Response `201 Created`

Response chỉ trả sau khi lưu database thành công. Header `Location` trỏ tới `/api/meetings/{id}` của meeting mới. Request tối thiểu nhận cùng cấu trúc, với `participants: []`.

```json
{
  "id": "cmh00000000000000000000001",
  "title": "Họp demo MVP",
  "anchor_date": "2026-10-25",
  "participants": ["Thành viên A", "Thành viên B"],
  "created_at": "2026-10-25T09:00:00.000Z",
  "updated_at": "2026-10-25T09:00:00.000Z"
}
```

| Field | Ý nghĩa |
|---|---|
| `id` | String do server tạo bằng cơ chế CUID hiện có; client coi là opaque ID, không tự tạo hoặc phân tích |
| `title` | Tiêu đề đã trim |
| `anchor_date` | Ngày họp dạng date-only, giữ đúng ngày người dùng nhập |
| `participants` | Luôn là mảng string đã trim, kể cả khi không nhập tên |
| `created_at` | Thời điểm tạo dạng ISO 8601 UTC có hậu tố `Z` |
| `updated_at` | Thời điểm cập nhật dạng ISO 8601 UTC; bằng `created_at` khi mới tạo |

Tạo meeting chưa upload audio và chưa gọi ASR/LLM. Hai request POST hợp lệ độc lập tạo hai meeting, kể cả trùng title/ngày; chưa có deduplication hoặc idempotency key. Frontend chặn submit lặp khi request đang chạy và không tự retry POST sau timeout vì có thể tạo bản ghi thứ hai.

## 3. GET `/api/meetings/{id}`

Dùng ID nhận từ POST; không có request body. Server tra cứu đúng ID, không trim hoặc tự sửa ID client gửi. Chuỗi ID không tìm thấy trả `404 MEETING_NOT_FOUND`; contract chưa yêu cầu regex CUID ở client.

Response `200 OK` có đúng cấu trúc metadata ở mục 2.2. GET không tạo meeting, không thay `updated_at` và không trả transcript/artifacts chưa thuộc contract. Reload trang phải đọc dữ liệu từ API/database, không chỉ từ state của form.

Ví dụ meeting tồn tại nhưng chưa có participants:

```json
{
  "id": "cmh00000000000000000000002",
  "title": "Họp kiểm tra tiến độ",
  "anchor_date": "2026-10-25",
  "participants": [],
  "created_at": "2026-10-25T09:05:00.000Z",
  "updated_at": "2026-10-25T09:05:00.000Z"
}
```

## 4. Lỗi cho hai endpoint meeting

Envelope lỗi gồm `statusCode` (number), `code` (string ổn định), `message` (string cho người đọc) và `errors` (array các object `field`, `message`; rỗng khi không có lỗi theo field). Frontend dựa vào status/code/field, không so khớp nguyên văn message.

| HTTP | Code | Khi nào |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Thiếu/sai field, sai kiểu, ngày không tồn tại, JSON body không phải object |
| 400 | `INVALID_JSON` | Body khai báo JSON nhưng không parse được |
| 404 | `MEETING_NOT_FOUND` | GET detail với ID không có trong database |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | POST thiếu/sai Content-Type JSON |
| 500 | `INTERNAL_ERROR` | Lỗi nội bộ hoặc database; không lộ SQL, connection string hay stack trace |

Ví dụ POST thiếu title và sai ngày:

```json
{
  "statusCode": 400,
  "code": "VALIDATION_ERROR",
  "message": "Thông tin meeting không hợp lệ.",
  "errors": [
    {
      "field": "title",
      "message": "Tiêu đề là bắt buộc, dài tối đa 200 ký tự sau trim."
    },
    {
      "field": "anchor_date",
      "message": "Ngày họp phải có dạng YYYY-MM-DD và tồn tại trong lịch."
    }
  ]
}
```

Field lỗi tên thứ nhất dùng `participants[0]`; lỗi chung cả mảng dùng `participants`. Field lạ dùng đúng tên key nhận được; lỗi toàn body dùng `body`. Không bắt buộc thứ tự các phần tử trong `errors`.

Ví dụ GET không tìm thấy:

```json
{
  "statusCode": 404,
  "code": "MEETING_NOT_FOUND",
  "message": "Không tìm thấy meeting.",
  "errors": []
}
```

Envelope này là yêu cầu khi triển khai module meeting, chưa phải hành vi của NestJS hiện tại. Không cần sửa response health hoặc các route khác để hoàn thành contract.

## 5. Ánh xạ Prisma và dữ liệu

Nguồn hiện tại: [Prisma schema](../packages/database/prisma/schema.prisma). Model `Meeting` đã có ID, title, anchorDate, createdAt và updatedAt; chưa có participants. Bảng dưới là hướng triển khai P02-01, chưa thay đổi schema trong task tài liệu này.

| API JSON | Prisma | Xử lý |
|---|---|---|
| `id` | `id` | Giữ `@default(cuid())`; server sinh ID |
| `title` | `title` | Lưu giá trị đã trim |
| `anchor_date` | `anchorDate` (`DateTime @db.Date`) | Parse ngày đã validate và serialize về `YYYY-MM-DD`, không trả cả datetime |
| `participants` | `participants` (dự kiến `String[] @default([])`) | Thêm migration; bản ghi cũ nhận `[]`; chưa cần bảng User/Participant |
| `created_at` | `createdAt` | Serialize UTC; client không được ghi |
| `updated_at` | `updatedAt` | Serialize UTC; client không được ghi |

Ngày họp là ngày lịch, không phải một thời điểm. Khi chuyển qua kiểu Date của Prisma, dùng quy ước UTC nhất quán để bảo toàn date-only; không dùng timezone trình duyệt/server để làm lệch ngày. Ví dụ nhập `2026-10-25` phải nhận lại đúng ngày đó cả ở UTC và Asia/Ho_Chi_Minh. `created_at`/`updated_at` là thời điểm nên mới dùng timestamp UTC.

Khi thêm participants, cần migration có thể áp dụng cho database đã có meeting. Lưu title, anchor_date và participants trong cùng một thao tác tạo; validation lỗi phải được xử lý trước khi ghi. Lỗi database không được trả `201` hoặc dữ liệu giả thành công.

## 6. Acceptance cho bước triển khai

Các case dưới đây là **kiểm tra cần chạy khi làm P02-01/P02-02**, chưa phải kết quả runtime của đợt tài liệu này.

| Case | Kết quả mong đợi |
|---|---|
| POST đầy đủ field hợp lệ | 201, có Location/ID; title/tên đã trim |
| Bỏ participants hoặc gửi `[]` | 201; response và database lưu `[]` |
| Title hoặc tên chỉ có khoảng trắng; sai kiểu/null | 400, đúng code và field; không tạo meeting |
| Title 200/201 ký tự; tên 100/101 ký tự; mảng 50/51 tên | Chấp nhận giới hạn đầu, từ chối vượt giới hạn |
| Ngày có thật/không có thật, năm nhuận | `2028-02-29` hợp lệ; `2026-02-29` và `2026-02-30` trả 400 |
| Sai định dạng ngày, có giờ/timezone, thiếu ngày | 400; không tự điền ngày hiện tại |
| Body là array/null, field lạ hoặc camelCase `anchorDate` | 400 VALIDATION_ERROR |
| JSON hỏng hoặc Content-Type sai | 400 INVALID_JSON hoặc 415 tương ứng |
| Hai tên giống nhau trong mảng | Giữ nguyên số lượng/thứ tự; không tự gộp |
| POST → GET bằng ID trả về → reload | 200, đúng metadata; timestamp không đổi do GET |
| GET ID không tồn tại | 404 MEETING_NOT_FOUND; không tạo bản ghi |
| Round trip ngày ở UTC và Asia/Ho_Chi_Minh | `anchor_date` không lệch ngày; timestamp có `Z` |
| Migration trên dữ liệu cũ | Meeting cũ đọc được, participants mặc định `[]` |
| Database lỗi trong POST/GET | 500 INTERNAL_ERROR; không lộ thông tin kết nối |
| Form gửi từ Next.js tới NestJS | Kết nối qua CORS/proxy đã cấu hình; hiển thị lỗi theo field, chặn submit lặp |

Hoàn thành P02-01 khi migration, hai endpoint, validation/error mapping và tests liên quan chạy được. P02-02 hoàn thành khi form tạo và trang chi tiết dùng API thật theo contract. List/update/delete sẽ được thiết kế bằng task riêng sau đó.
