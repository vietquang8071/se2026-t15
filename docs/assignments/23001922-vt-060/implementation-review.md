# Review implementation và TDD

Original baseline trước BT3: 34455552b6ebcef4ea155b2ba6dc86719a14220d; baseline lượt cải tiến: db34fa50cf98730f4adf733dd4937585915acb71. Initial plan 409fa7d1e7549bfd70895c2091466169991513c1 trước test RED f55a0d10c36d8b01c28b6f0062e7530374507e14; GREEN 12e9cdc33dfd03536c957bb1820e93b4fe518569. Snapshot test và evidence fab6f98da18e35df1ba106f8f2d786244776cea0. Không nhầm ba commit BT3 cũ với test-first mới.

TC-07, starting a job rolls back asset status when both job writes fail, thực thi trực tiếp worker và trigger DB từ chối cả running và failed. [RED](evidence/red.log): actual processing, expected uploaded, job vẫn queued; đây là assertion nghiệp vụ, không phải import/setup error. [GREEN](evidence/green.log): cùng test 1/1 pass. Test chỉ chứng minh failure scenario chèn lỗi, không mô phỏng crash OS.

Diff RED→GREEN dùng transaction cho update asset và update job + increment attempts. Nếu lệnh sau lỗi, PostgreSQL rollback lệnh trước. Giữ thứ tự lock asset trước job và catch cũ; không thêm provider call, schema, dependency, endpoint hay exception swallowing mới. Review AI: không mở rộng transaction qua I/O/provider; đề xuất thay bằng startup reconciliation bị bỏ vì không ngăn partial commit. Transaction failure handler có thể thất bại và chỉ log, cần restart; asset bị deleted/expired trong các race khác chưa được chứng minh đầy đủ.

Kết quả cũ sau patch: [audio 44/44](evidence/regression-audio.log), [HTTP 21/21](evidence/regression-http.log), [HTTP với coverage 22/22](evidence/coverage-http.log), [lint](evidence/lint.log), [typecheck](evidence/typecheck.log). Chạy pnpm --filter @meeting-minutes/audio test:audio, test:http, lint, typecheck; HTTP là audio-service E2E có provider giả, không phải full-system E2E.
