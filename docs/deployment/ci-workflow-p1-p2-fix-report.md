# Báo cáo sửa lỗi CI P1/P2

Ngày: 2026-11-23  
Branch: `feature/setup-github-actions-ci`  
Workflow: `.github/workflows/ci.yml`

## P1 — Context không hợp lệ trong môi trường Audio

Workflow run `45116007263` kết thúc `failure`, sự kiện `push`, tại commit
`2de94a8939a0d08cc3cb70836d1b263e1e067262`. GitHub ghi nhận không có job nào
được tạo. API run/jobs không trả thông báo parser cụ thể; vì vậy nguyên nhân
trực tiếp không thể xác nhận từ log. Tuy nhiên, cấu hình có
`${{ runner.temp }}` trong `jobs.ci-audio.env`, trong khi bảng context chính
thức không cho phép context `runner` tại `jobs.<job_id>.env`. Đây là nguyên nhân
phù hợp với việc workflow thất bại trước khi tạo job.

Đã xóa biểu thức đó khỏi job-level env. Step tạo `.env` tạm trên runner, tạo
thư mục trong `$RUNNER_TEMP`, rồi ghi `AUDIO_STORAGE_DIR` vào `$GITHUB_ENV` để
các step tiếp theo nhận được biến này. URL PostgreSQL và các giá trị kiểm thử
giả được giữ nguyên; không thêm credentials thật.

Tham khảo: [GitHub Actions contexts](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts),
[GitHub Actions variables](https://docs.github.com/en/actions/reference/workflows-and-actions/variables).

## P2-01 — Không lưu checkout credentials

Đã thêm `persist-credentials: false` vào cả bốn checkout step. SHA checkout
được giữ nguyên. Metadata `action.yml` tại SHA đang dùng xác nhận input này
được hỗ trợ; quyền workflow vẫn là `contents: read`.

Tham khảo: [metadata của actions/checkout tại SHA đã pin](https://github.com/actions/checkout/blob/3d3c42e5aac5ba805825da76410c181273ba90b1/action.yml).

## P2-02 — Pin phiên bản uv

Đã pin uv thành `0.11.32`. Đây là phiên bản uv cài trên môi trường làm việc và
là release chính thức (23-07-2026). Metadata của `astral-sh/setup-uv` tại SHA
đang pin hỗ trợ input `version`, cùng các input hiện có cho Python 3.12 và
cache. Cấu hình `pyproject.toml`, `uv.lock` và lệnh CI không đổi.

Tham khảo: [release uv 0.11.32](https://github.com/astral-sh/uv/releases/tag/0.11.32),
[metadata của setup-uv tại SHA đã pin](https://github.com/astral-sh/setup-uv/blob/1db35dd8eee11c5894872e0b383ae6c406cf738d/action.yml).

## Kiểm tra

**Đạt:**

- YAML được parse bằng PyYAML; xác nhận đủ bốn job, trigger PR/push cho
  `develop` và `main`, `workflow_dispatch`, không có dependency `needs`, đủ
  bốn checkout với `persist-credentials: false`, không còn `runner.temp` và
  có pin uv chính xác.
- `bash -n` chấp nhận cú pháp script tạo storage Audio.
- `uv lock --check --offline` thành công khi dùng cache tạm trong `/tmp`.
- `uv sync --locked --extra test --python 3.12 --offline` thành công.
- LLM pytest chạy offline: **746 passed**.
- Dataset evaluation offline hợp lệ: **16 cases** (10 development, 6 holdout).
- `git diff --check` thành công.

**Chưa chạy hoặc cần GitHub-hosted runner:**

- `actionlint` không có sẵn; Go không có sẵn và Docker daemon không truy cập
  được. Vì vậy chưa có kết quả từ actionlint. Các expression contexts và action
  inputs đã được đối chiếu với tài liệu/metadata chính thức, nhưng đây không
  thay thế hoàn toàn static validation bằng actionlint hoặc GitHub.
- Web/API/Audio lint, build và tests không chạy trong lượt này. pnpm không lấy
  được operation lock từ store read-only của môi trường; Docker socket bị từ
  chối nên không thể chạy PostgreSQL service hoặc Audio HTTP integration.
- Chưa có lần chạy mới trên GitHub. Chỉ workflow run sau khi cập nhật branch/PR
  mới xác nhận hành vi thực tế của runner và cấu hình service.

## Phạm vi và an toàn file

Thay đổi cấu hình chỉ ở `.github/workflows/ci.yml`. File báo cáo này được tạo
riêng theo yêu cầu ghi báo cáo trong `docs/deployment/`; báo cáo deployment có
sẵn và các untracked khác không bị sửa hoặc xóa. Không file nào được stage,
commit hay push.
