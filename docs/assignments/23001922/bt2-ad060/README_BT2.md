# BT2 — 23001922 — AD-060

File nộp duy nhất: [BT2_23001922_AD-060.pdf](BT2_23001922_AD-060.pdf).

PDF có **7 trang nội dung chính**, theo sau là **9 trang AI Usage Log**, trong đó có prompt đầu vào nguyên văn. Phụ lục dài vì giữ prompt để tái hiện; không chứa phần rubric bị chuyển ra ngoài 7 trang.

## File chỉnh sửa và bằng chứng

- `report/BT2_23001922_AD-060.md`: bản source đọc được, tự sinh từ script dựng PDF.
- `report/build_report.py`: source bố cục/nội dung chính để chỉnh và xuất lại PDF.
- `diagrams/module-view.svg`, `diagrams/runtime-view.svg`: sơ đồ vector thực sự, được nhúng vector vào PDF.
- `report/make_diagrams.py`: source tạo sơ đồ.
- `scenario/`: before/after, adapter, use case, canonical contract, SQL/test harness và test plan.
- `evidence/repository/`: clone tham chiếu nguyên trạng; không sửa/push.
- `evidence/snapshot.json`: branch/commit/thời gian và file hashes.
- `evidence/ai_initial.txt`, `evidence/ai_review.txt`: output AI thực trước và sau đối chiếu.
- `evidence/test-results.json`, `evidence/test-output.txt`: kết quả đã chạy.
- `evidence/test-output-initial-failure.txt`: lần chạy đầu vướng probe PostgreSQL init; không che lỗi này.
- `evidence/pdf-check.json`, `report/previews/`: kết quả kiểm tra PDF và ảnh xem trước.

## Chạy lại

```bash
python3 scenario/run-tests.py
.tools/bin/python report/make_diagrams.py
.tools/bin/python report/build_report.py
.tools/bin/python report/check_pdf.py
```

Test script hiện dùng Node `/home/sonnh/.codex/tools/nodejs/bin/node` (đã kiểm tra v25.8.2, chạy TypeScript trực tiếp). Node `/usr/bin/node` v18 không hỗ trợ cách chạy này. Nếu đổi máy, sửa biến `node` trong `scenario/run-tests.py` sang Node hỗ trợ native TypeScript.

PDF toolchain đã cài riêng trong `.tools/`, không đổi dependency của repo. Nếu tạo lại môi trường, cài ReportLab + svglib + PyMuPDF và có font DejaVu Sans, Noto Sans và Liberation Mono. Không cần cài package pnpm của repo để chạy minh họa này. PostgreSQL dùng image local `postgres:17-alpine`, container tạm không mount dữ liệu của người dùng.

## Những điều cần đọc trước khi nộp

- Repository gốc mới là skeleton. Hàm dài, adapter và import contract là phần mở rộng cá nhân; giảng viên vẫn cần chấp nhận cách áp dụng kịch bản theo rubric.
- 17 tests minh họa đạt không đồng nghĩa NestJS/provider/deploy thật đã đạt. Minutes là fixture; job sample dùng RAM. `scenario/TEST_PLAN.md` tách rõ planned tests.
- Chưa có Lecture 04/05: tự đối chiếu thuật ngữ và slide khi có tài liệu.
- Xác nhận chính sách quyền sở hữu meeting, nguồn mới, core-read SLO và retention cùng nhóm. ADR là đề xuất cá nhân, chưa phải quyết định nhóm.
- Tự giải thích invariant, refactoring, ACK/completion và rollback/data compatibility. Không có tuyên bố sinh viên đã kiểm tra thay cho bạn.

Không nộp README/source/clone thay PDF. Chưa tạo PR, push, email hoặc nộp Classroom.

## Bản lưu trên Git

Bộ bài được lưu riêng dưới `docs/assignments/23001922/bt2-ad060/`, dựa trên snapshot `main` đã dẫn trong PDF; không mô tả toàn bộ tính năng mới hơn trên `son_branch`.

Không commit môi trường `.tools/`, clone tham chiếu hoặc ảnh preview. Muốn tái xuất/kiểm tra PDF, chạy từ thư mục bài làm:

```bash
python3 -m venv .tools
.tools/bin/pip install reportlab svglib pymupdf
git clone https://github.com/vietquang8071/se2026-t15.git evidence/repository
git -C evidence/repository checkout --detach 1bcbfc156671888a83da57dece19c1ac18b498e8
.tools/bin/python report/make_diagrams.py
.tools/bin/python report/build_report.py
.tools/bin/python report/check_pdf.py
```

Nếu test trên máy khác, cập nhật đường dẫn Node trong `scenario/run-tests.py`. Test tạo container PostgreSQL riêng; không dùng DB của project.
