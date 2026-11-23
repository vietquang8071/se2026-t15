# Báo cáo triển khai GitHub Actions CI — SE2026-T15

- **Ngày:** 2026-11-23
- **Nhánh:** `feature/setup-github-actions-ci`

## A. Trạng thái hiện tại

- Nhánh làm việc đúng với yêu cầu; không có thay đổi đã theo dõi trước khi bắt đầu.
- Repo chưa có thư mục `.github` hoặc workflow CI hiện hữu.
- Cấu hình gốc ghim `pnpm@11.1.1`; các app TypeScript nằm trong workspace pnpm/Turborepo. API dùng Prisma từ `packages/database`; Audio có Prisma schema, DB và API riêng.
- `apps/audio/test/http/audio-http.test.mjs` kết nối vào database `postgres`, tạo database riêng theo PID/ngẫu nhiên rồi xóa database đó. User PostgreSQL trong CI vì vậy cần quyền tạo/xóa database; PostgreSQL service dùng user riêng có quyền này.
- Script `test:http` gọi Node với `--env-file=../../.env`, nên job Audio sao chép `.env.example` thành `.env` chỉ trên runner. Các biến job, gồm `AUDIO_DATABASE_URL`, khóa giả và storage tạm, được đặt tường minh.
- API không có script hoặc bộ unit test hiện hữu. Audio unit/integration tests và HTTP tests có sẵn. Bộ pytest LLM chặn outbound HTTP; lệnh CI chỉ kiểm tra dữ liệu synthetic offline.
- Frontend đang ghim Next.js `16.4.3`. Bản phát hành bảo mật Next.js tháng 11/2026 đưa ra bản vá `16.4.5`; việc nâng phiên bản nằm ngoài phạm vi được phép. [Thông báo bảo mật Next.js](https://nextjs.org/blog/november-2026-security-release)

## B. Tệp được tạo

| Tệp                                  | Lý do                                                                                                     |
| ------------------------------------ | --------------------------------------------------------------------------------------------------------- |
| `.github/workflows/ci.yml`           | Tạo workflow `CI` với bốn job độc lập, trigger PR/push vào `develop` và `main`, cùng `workflow_dispatch`. |
| `docs/deployment/ci-setup-report.md` | Ghi lại cấu hình, kết quả kiểm tra, giới hạn và các bước tiếp theo bằng tiếng Việt.                       |

Không sửa source, test, manifest, lockfile, schema hoặc migration. Các đường dẫn untracked có sẵn trong `packages/database/` không bị đụng tới.

## C. Tóm tắt workflow

Workflow dùng runner `ubuntu-24.04`, `CI=true`, `permissions: contents: read`, hủy run cũ cùng PR/branch và ghim các action theo commit SHA. Cả bốn job chạy độc lập, không có `needs`.

| Job ID     | Runtime                                | Lệnh chính                                                                                                                | Phụ thuộc ngoài                                                              | Timeout |
| ---------- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- | ------: |
| `ci-web`   | Node.js 24, pnpm 11.1.1                | `pnpm install --frozen-lockfile`; lint, typecheck, test; `CI=true pnpm --filter @meeting-minutes/web build`               | npm registry, pnpm và cache GitHub Actions                                   | 15 phút |
| `ci-api`   | Node.js 24, pnpm 11.1.1                | Cài lockfile; validate Prisma shared; generate client; lint/build database; lint/typecheck/build API                      | npm registry, pnpm và cache GitHub Actions                                   | 15 phút |
| `ci-audio` | Node.js 24, pnpm 11.1.1, PostgreSQL 17 | Cài FFmpeg/font và lockfile; tạo `.env` runner; validate/generate Prisma; lint/typecheck/build; `test:audio`; `test:http` | npm registry, apt packages, Docker Hub/PostgreSQL 17 và cache GitHub Actions | 30 phút |
| `ci-llm`   | Python 3.12, uv                        | `uv sync --locked --extra test --python 3.12`; pytest; `evaluation.runner validate-dataset`                               | PyPI và cache uv của GitHub Actions; không gọi AI provider                   | 20 phút |

Cache Node dùng pnpm store với `pnpm-lock.yaml`; cache Python dùng uv và `apps/llm-service/uv.lock`. Không cache `node_modules`, credentials hay evaluation output.

Các action được đối chiếu theo repo/tài liệu chính thức: [actions/checkout v7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1), [pnpm/setup v2.1.0](https://github.com/pnpm/setup/tree/v2.1.0) và [astral-sh/setup-uv v10.4.0](https://github.com/astral-sh/setup-uv/tree/1db35dd8eee11c5894872e0b383ae6c406cf738d).

## D. Kết quả xác thực

### Đã đạt tại local

- Workflow parse được bằng PyYAML; kiểm tra cấu trúc xác nhận đúng trigger, quyền, bốn job, tính độc lập và PostgreSQL service.
- Prettier xác nhận `.github/workflows/ci.yml` đúng cú pháp và định dạng YAML.
- Web: lint, typecheck, unit test (1 test) và production build đều thành công. Build Next.js không chờ prompt tương tác.
- Shared database: Prisma schema hợp lệ; generate client, lint và build thành công.
- API: lint, typecheck và build thành công.
- Audio: Prisma schema hợp lệ; lint, typecheck, build và `test:audio` thành công (5 test file, không lỗi).
- LLM: `uv sync --locked` thành công với cache tạm trong `/tmp`; pytest thành công (746 tests); dataset synthetic hợp lệ (16 case: 10 development, 6 holdout).

### Không đạt / khác biệt môi trường local

- Máy local có pnpm `12.15.0`, khác bản repo ghim `11.1.1`. Cơ chế tự chuyển phiên bản không lấy được lock trong pnpm tool store chỉ đọc. Vì vậy không chạy được cài đặt frozen bằng đúng pnpm `11.1.1`; các lệnh script local đã chạy bằng dependencies sẵn có và pnpm `12.15.0`, với kiểm tra tự cài dependencies của pnpm 12 tắt riêng trong lệnh local. Điều này không thay đổi workflow.
- Lần `uv sync` đầu dùng cache mặc định trong thư mục chỉ đọc nên thất bại; chạy lại với `UV_CACHE_DIR=/tmp/se-ci-uv-cache` thì thành công.

### Chưa chạy tại local

- `test:http` không chạy vì Docker daemon không khả dụng và không có PostgreSQL test cô lập. Không kết nối hay thay đổi database developer. Root `.env` đã tồn tại từ trước; không xem nội dung trực tiếp, không tạo, sửa hoặc xóa file này.
- `actionlint` không có sẵn. PyYAML/Prettier kiểm tra YAML và cấu trúc; tên action, SHA và input đã được đối chiếu tài liệu repo chính thức, nhưng chưa có validator chuyên biệt kiểm tra toàn bộ schema GitHub Actions.
- Không có API unit test/script để chạy.

### Cần GitHub Actions xác nhận

- Chưa có run trên GitHub. Việc cài đúng Node.js 24/pnpm 11.1.1 trên runner, tải action theo SHA, cache, health check PostgreSQL service và chạy HTTP integration tests chỉ được xác nhận sau khi push nhánh và mở PR hoặc chạy workflow thủ công.
- Không ghi nhận workflow là “passed” trước khi GitHub hoàn thành run thực tế.

## E. Rủi ro và giới hạn

- **Next.js 16.4.3:** phiên bản hiện tại thấp hơn bản vá `16.4.5` trong thông báo bảo mật ngày 2026-11-03. Một số vấn đề nêu trong thông báo phụ thuộc cấu hình và runtime; cần đánh giá áp dụng và nâng cấp trong thay đổi riêng. Workflow không bỏ qua lỗi build và không thay đổi dependency.
- **API tests:** chưa có test API để CI chạy; job chỉ kiểm tra Prisma, lint, typecheck và build.
- **Audio HTTP:** test cần PostgreSQL 17 tạm thời và quyền tạo/xóa database. Workflow cấp quyền đó chỉ trong service container dùng riêng cho run; test dùng provider giả và khóa OpenAI giả.
- **E2E liên dịch vụ:** chưa có kiểm thử nối web, API, audio và LLM thành một luồng end-to-end.
- **AI đánh giá trực tiếp:** CI chỉ kiểm tra pytest và dataset offline; không chạy OpenRouter, DeepSeek hoặc provider thật.
- **Runner:** chưa kiểm chứng trên GitHub-hosted runner; kết quả local không thay thế run của workflow.

## F. Bước tiếp theo

### Xem lại và commit riêng workflow

Các lệnh sau chỉ stage và commit workflow; giữ báo cáo cùng các tệp untracked khác ngoài staging:

```bash
git status --short
cat .github/workflows/ci.yml
git diff --check
git add .github/workflows/ci.yml
git diff --cached --check
git diff --cached -- .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions CI workflow"
```

### Push và mở PR (chưa thực hiện)

```bash
git push -u origin feature/setup-github-actions-ci
```

Trên GitHub, chọn **Pull requests → New pull request**, đặt base là `develop`, compare là `feature/setup-github-actions-ci`. Có thể dùng tiêu đề `ci: add GitHub Actions CI workflow`; mô tả PR nên nêu bốn job, kiểm tra local, giới hạn pnpm/PostgreSQL local và liên kết báo cáo này.

Sau khi mở PR, vào **Actions → CI** hoặc mục **Checks** trên PR; xác nhận cả `ci-web`, `ci-api`, `ci-audio`, `ci-llm` đã hoàn tất. Xem log Audio để xác nhận PostgreSQL healthy và HTTP integration test thành công. Không coi các run bị hủy do concurrency là kết quả cuối.

Khi nhóm thiết lập branch protection trong tương lai, các required status check đề xuất là `ci-web`, `ci-api`, `ci-audio` và `ci-llm`.

## G. Điểm dừng

Đã tạo và kiểm tra workflow cùng báo cáo. Không stage, commit, push, mở PR, merge hoặc thay đổi cài đặt GitHub. Chờ người dùng xem lại và hướng dẫn tiếp.
