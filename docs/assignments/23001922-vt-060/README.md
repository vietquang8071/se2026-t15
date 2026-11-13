# BT3 — AI-05, VT-060

Nguyễn Huy Sơn, 23001922, SE2026-T15. Thay đổi nhỏ trong audio service bảo vệ transaction khi bắt đầu job; retry và checkpoint giữ nguyên. Nhánh [bt3/23001922-vt-060](https://github.com/vietquang8071/se2026-t15/tree/bt3/23001922-vt-060). Original baseline 34455552b6ebcef4ea155b2ba6dc86719a14220d; baseline lượt cải tiến db34fa50cf98730f4adf733dd4937585915acb71; plan 409fa7d1e7549bfd70895c2091466169991513c1; RED f55a0d10c36d8b01c28b6f0062e7530374507e14; GREEN 12e9cdc33dfd03536c957bb1820e93b4fe518569; snapshot evidence fab6f98da18e35df1ba106f8f2d786244776cea0.

- Code: apps/audio/src/audio/audio.service.ts; tests/harness: apps/audio/test/http/audio-http.test.mjs và test/audio/media-provider.test.mjs.
- [Báo cáo PDF](report/BT3_23001922_VT-060.pdf) · [Markdown](report/BT3_23001922_VT-060.md) · [Evidence](evidence/) · [Rubric](rubric-checklist.md).

## Môi trường test

Node >=22.18, pnpm 11, PostgreSQL, FFmpeg/FFprobe, Docker nếu dùng server test dưới đây. Test HTTP tạo và xóa database ngẫu nhiên; bắt buộc dùng PostgreSQL riêng, user có quyền CREATE DATABASE, không dùng production. Chỉ dùng audio tổng hợp và fake provider; không cần OpenAI key thật.

Tại root repository:

~~~sh
pnpm install --frozen-lockfile
docker run -d --name vt060-test-postgres -e POSTGRES_USER=bt3 -e POSTGRES_PASSWORD=bt3-test-only -e POSTGRES_DB=postgres -p 127.0.0.1:55433:5432 postgres:17-alpine
export AUDIO_DATABASE_URL='postgresql://bt3:bt3-test-only@127.0.0.1:55433/postgres?schema=public'
pnpm --filter @meeting-minutes/audio db:generate
pnpm --filter @meeting-minutes/audio test:audio
pnpm --filter @meeting-minutes/audio test:http
pnpm --filter @meeting-minutes/audio lint
pnpm --filter @meeting-minutes/audio typecheck
~~~

Chờ server sẵn sàng trước test. Mật khẩu trên là mật khẩu chỉ dùng cho test local; không đặt secret thật vào source hay log. Dừng server đã tạo bằng docker stop vt060-test-postgres khi kết thúc.

## Chạy riêng state transition và performance

Sau khi chạy db:generate và biên dịch bằng test:http:

~~~sh
cd apps/audio
node --test --test-name-pattern='starting a job rolls back|retry reuses a persisted|job retry cap|failed job with two attempts|startup recovers' test/http/audio-http.test.mjs
node --test --test-name-pattern='40 concurrent process|40 independent audio tasks' test/http/audio-http.test.mjs
~~~

Test in raw latencies; p95 nearest-rank chỉ đo acceptance. Chi tiết môi trường, 3 lượt và warm-up xem [performance](performance-report.md). Test tạo rồi xóa database test và thư mục tạm.

## Mutation trong worktree cô lập

Về root, sau khi cài dependency và tạo Prisma client:

~~~sh
bash docs/assignments/23001922-vt-060/scripts/reproduce-mutation.sh
~~~

Script tạo worktree detached tạm, chạy original, đảo rule trong worktree đó, kiểm tra hai assertion, restore và chạy lại; trap xóa worktree tạm. Log nằm tại thư mục tạm được in ra. Xem [mutation report](mutation-report.md) và diff/log của thí nghiệm trước.

## Giới hạn

Không có exactly-once ở provider: crash sau response trước checkpoint có thể gọi lại. Lượt tải không chứng minh thời gian hoàn tất phiên âm hoặc 40 worker; service dùng worker tuần tự. Chưa chạy real-provider E2E. AI đã hỗ trợ plan, code, test và báo cáo; reflection do sinh viên cung cấp; sinh viên đã xác nhận đã review; chưa ghi nhận xác nhận riêng về cam kết.

## Xuất lại báo cáo

Cần Pandoc, Google Chrome, Python và PyMuPDF. Chạy từ repository:

~~~sh
bash docs/assignments/23001922-vt-060/scripts/render-report.sh
~~~

PDF được phân trang bằng CSS và thêm số trang; sau khi xuất lại cần kiểm tra bố cục, số trang chính và nội dung. File evidence kiểm tra PDF được lưu từ phiên bản trước, không được sửa ở lượt này. PDF cập nhật hiện có 8 trang: 4 trang chính và phụ lục bắt đầu từ trang 5.
