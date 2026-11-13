# VT-060 — kết quả đang hoàn thiện

Nhánh `bt3/23001922-vt-060`; baseline trước ba commit BT3 `34455552b6ebcef4ea155b2ba6dc86719a14220d`, baseline lượt này `db34fa50cf98730f4adf733dd4937585915acb71`. Plan trước code `409fa7d`; RED `f55a0d10c36d8b01c28b6f0062e7530374507e14`; GREEN `12e9cdc33dfd03536c957bb1820e93b4fe518569`. Đây chưa phải báo cáo nộp bài hoàn chỉnh.

## Kết quả kiểm chứng

Trên Node 25.8.2, pnpm 11.1.1, PostgreSQL 17 riêng trong Docker, FFmpeg và provider giả: baseline 44 audio + 20 HTTP pass, lint và typecheck pass. Test mới chặn hai lệnh ghi job bằng trigger trong database test: RED vì asset `processing` trong khi job còn `queued`; sau transaction cả hai cập nhật khởi đầu, test pass. Regression 44 audio + 21 HTTP pass; chạy lại toàn bộ HTTP sau thêm bài tải: 22/22 pass với coverage. Log tại [evidence](evidence/).

Mutation trong worktree tách biệt: đảo `job.attempts >= 3`; hai test biên đều bắt được (202 thay vì 409 và 409 thay vì 202). Khôi phục code, hai test lại pass. Diff và log được lưu; không có mutation trên nhánh nộp.

40 POST cùng asset trong regression: 40 thành công, một job, p95 289,44 ms. 40 asset độc lập: 40 thành công, 40 job ánh xạ đúng, p95 200,75 ms theo nearest-rank; chỉ một lượt, không có warm-up chính thức. Đây là thời gian tiếp nhận API local, không phải thời gian phiên âm hoặc benchmark production. Dữ liệu và cấu hình máy có thể ảnh hưởng kết quả. Không khẳng định external exactly-once: response provider có thể thành công trước khi checkpoint được commit.

Node coverage trên JS đã biên dịch, suite HTTP, bao gồm mã Prisma sinh: `audio.service.js` dòng 96,67%, nhánh 76,69%, hàm 94,44%; `audio-provider.js` dòng 15,15% vì provider giả. Không suy ra correctness từ coverage. Test đang dùng polling/timer và mutable `service.provider`; timeout, thứ tự chạy và shared state là rủi ro flaky chưa được lượng hóa bằng nhiều lượt lặp.

## Chạy lại

Yêu cầu Node >=22.18, pnpm 11, FFmpeg/FFprobe và PostgreSQL test riêng, tài khoản có quyền tạo/xóa database test. KHÔNG trỏ vào production. Thiết lập URL test qua biến môi trường trước các lệnh sau; test tạo database ngẫu nhiên, và xóa database đó sau khi chạy. Provider HTTP là giả.

```sh
export AUDIO_DATABASE_URL='postgresql://bt3:bt3-test-only@127.0.0.1:55433/postgres?schema=public'
pnpm --filter @meeting-minutes/audio test:audio
pnpm --filter @meeting-minutes/audio test:http
pnpm --filter @meeting-minutes/audio lint
pnpm --filter @meeting-minutes/audio typecheck
cd apps/audio
node --test --test-name-pattern='starting a job rolls back|40 independent audio tasks|40 concurrent process' test/http/audio-http.test.mjs
```

Chỉ chạy lệnh trên sau khi chuẩn bị server PostgreSQL test ở cổng 55433, không dùng thông tin kết nối thật. Harness nằm trong `apps/audio/test/http/audio-http.test.mjs`; output raw lưu thời gian từng request. Chưa có script tự động hóa mutation hoặc tài liệu báo cáo và PDF cuối; các phần chưa làm không được coi là đã nghiệm thu.
