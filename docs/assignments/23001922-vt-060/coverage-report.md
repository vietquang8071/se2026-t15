# Coverage và risk coverage

Node --experimental-test-coverage, suite HTTP, trên dist JavaScript đã biên dịch, không phải TypeScript source. [Raw report](evidence/coverage-http.log): audio.service.js line 96,67%, branch 76,69%, function 94,44%; audio-provider.js line 15,15%, branch 66,67%, function 50% vì provider được thay fake trong suite HTTP. Tổng 87,28% line, 74,37% branch, 94,83% functions gồm generated Prisma; không đại diện toàn suite và không phải thước đo correctness.

| AC/risk | Evidence | Khoảng trống |
|---|---|---|
| AC-01/02 | TC-01–04,12,17; mutation retry | Không có full provider + DB exactly-once |
| AC-03 | TC-05/06 | Chưa chứng minh mọi lịch đồng thời |
| AC-04 | TC-07/08/11; RED/GREEN | Các lỗi OS/DB khác chưa exhaustively thử |
| AC-05 | TC-09/10/15 | Crash sau response trước checkpoint chưa tiêm lỗi |
| NFR-01 | TC-16 | Chỉ acceptance local; một worker tuần tự |

Chưa có assertion riêng attempts=1 và >3; coverage cao không chứng minh crash window, tính chính xác provider hay tất cả interleaving.
