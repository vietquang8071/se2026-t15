# Truy vết

Tên đầy đủ và điều kiện từng test xem [test cases](test-cases.md). H = apps/audio/test/http/audio-http.test.mjs; P = apps/audio/test/audio/media-provider.test.mjs. Snapshot code chứa test trước thay đổi mới là db34fa5; không gán test cũ cho commit mới. Các pass dưới đây trích log thực tế ở snapshot đã nêu.

| AC/Risk | Test ID | Test file | Commit chứa test | Result | Evidence |
|---|---|---|---|---|---|
| AC-01 | TC-01 | P | db34fa50cf98730f4adf733dd4937585915acb71 | PASS | [audio](evidence/regression-audio.log) |
| AC-01 | TC-02,17 | P | db34fa50cf98730f4adf733dd4937585915acb71 | PASS | [audio](evidence/regression-audio.log) |
| AC-02 | TC-03 | P | db34fa50cf98730f4adf733dd4937585915acb71 | PASS | [audio](evidence/regression-audio.log) |
| AC-02 | TC-04,12 | H | db34fa50cf98730f4adf733dd4937585915acb71 | PASS; mutant killed | [mutation](evidence/mutation-run.log), [restored](evidence/mutation-restored.log) |
| AC-03 | TC-05,06 | H | db34fa50cf98730f4adf733dd4937585915acb71 | PASS | [HTTP](evidence/regression-http.log) |
| AC-04 | TC-07 | H | f55a0d10c36d8b01c28b6f0062e7530374507e14; fix 12e9cdc33dfd03536c957bb1820e93b4fe518569 | RED → GREEN | [red](evidence/red.log), [green](evidence/green.log) |
| AC-04 | TC-08,11 | H | db34fa50cf98730f4adf733dd4937585915acb71 | PASS | [HTTP](evidence/regression-http.log) |
| AC-05 | TC-09,10,15 | H | db34fa50cf98730f4adf733dd4937585915acb71 | PASS | [HTTP](evidence/regression-http.log) |
| Expiry/delete | TC-13,14 | H | db34fa50cf98730f4adf733dd4937585915acb71 | PASS | [HTTP](evidence/regression-http.log) |
| NFR-01 | TC-16 | H | fab6f98da18e35df1ba106f8f2d786244776cea0 | PASS local | [run1](evidence/performance/run1.log), [run2](evidence/performance/run2.log), [run3](evidence/performance/run3.log) |

Commit db34fa5 ở đây là snapshot có chứa test, không khẳng định đây là commit tạo từng test. Chưa chứng minh crash sau provider response trước checkpoint, provider thật và mọi interleaving.
