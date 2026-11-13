# Đối chiếu rubric

| Yêu cầu | Trạng thái | Evidence / hành động còn lại |
|---|---|---|
| Problem, 5 AC, 2 NFR, invariant | PASS | [Specification](specification.md) |
| Plan trước code, assumptions, 2 chỉnh sửa, 1 giả định sai | PASS | [Initial plan](initial-plan.md), commit plan trước RED/GREEN |
| Unit, integration, E2E audio, test không chọn | PASS | [Strategy](test-strategy.md) |
| State transition, ≥10 case, negative/failure | PASS | [Transition](state-transitions.md), [17 cases](test-cases.md) |
| Baseline, RED, GREEN, patch review, regression | PASS | [Review](implementation-review.md), raw logs |
| Business rule mutation detected | PASS | [Mutation](mutation-report.md) |
| Coverage, risk coverage, ≥2 flaky risks và lặp | PASS | [Coverage](coverage-report.md), [flaky](flaky-review.md) |
| 40 request, raw p95, threshold và giới hạn | PASS | [Performance](performance-report.md) |
| Traceability và AI usage, hai output cần kiểm tra | PASS | [Traceability](traceability.md), [AI log](ai-usage-log.md) |
| Reflection 250–350 từ | PASS | [Nội dung do sinh viên cung cấp](reflection.md) |
| Report MD/PDF, ≤8 trang chính | PASS | [Report](report/BT3_23001922_VT-060.pdf); bản hiện tại 4 trang chính; evidence kiểm tra PDF cũ được giữ nguyên |
| Xác nhận của sinh viên/cam kết | PASS | Sinh viên xác nhận đã review và xác nhận cam kết trong hội thoại. |
| Real provider E2E/external exactly-once | NOT RUN | Không thuộc phạm vi bằng chứng fake provider; còn rủi ro crash window |
