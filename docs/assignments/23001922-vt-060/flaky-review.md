# Phân tích flaky

Target pattern: starting a job rolls back | retry reuses a persisted | provider failure records | startup recovers | DELETE aborts. Node test runner; mỗi lượt là tiến trình mới với DB ngẫu nhiên, storage tạm và provider giả; before tạo database, after đóng app/xóa database, log và duration từ monotonic clock. [Metadata và command](evidence/repeated-runs.json).

| Lượt | Thời điểm | Giây | Exit | Pass |
|---|---|---:|---:|---|
| 1 | 2026-11-14T03:18:53.428268+07:00 | 11.201 | 0 | 5/5 |
| 2 | 2026-11-14T03:19:04.629942+07:00 | 11.344 | 0 | 5/5 |
| 3 | 2026-11-14T03:19:15.974513+07:00 | 11.418 | 0 | 5/5 |

[Log 1](evidence/flaky/1.log), [log 2](evidence/flaky/2.log), [log 3](evidence/flaky/3.log): không quan sát thấy flakiness trong 3 lần thử; không chứng minh rủi ro đã hết.

- Polling/timer: worker tick 1 giây, poll 100×100 ms và timeout trong một số test; lịch OS/FFmpeg/DB chậm có thể vượt thời gian. Chờ điều kiện giảm race nhưng còn phụ thuộc đồng hồ.
- Shared state: service.provider, env và fetch mock có thể ảnh hưởng test khác nếu chạy song song; HTTP test tạo DB và thư mục tạm riêng, fake provider phục hồi trong một số finally, song không phải mọi test đều phục hồi khi assertion lỗi. Chạy tuần tự theo runner giảm rủi ro, không chứng minh an toàn parallel.
- Lock và request đồng thời: cùng asset bị serialize; DB chậm hoặc contention làm latency thay đổi. Network provider thật không nằm trong test này. Không sửa test vì không quan sát lỗi.
