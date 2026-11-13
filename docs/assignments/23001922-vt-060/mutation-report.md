# Mutation testing

Original test 2/2 pass; rule thực là điều kiện job.attempts >= 3 từ chối retry. [Mutation diff](evidence/mutation-diff.patch) phủ định điều kiện. [Mutation run](evidence/mutation-run.log) exit 1: TC-04 nhận 202 thay vì 409 tại attempts 3; TC-12 nhận 409 thay vì 202 tại attempts 2. Hai assertion trực tiếp bảo vệ hai phía ranh giới, mutant KILLED. Sau restore, [hai test pass](evidence/mutation-restored.log). Mutation tiến hành tại worktree tách biệt; source nhánh nộp giữ điều kiện gốc. [Original log](evidence/mutation-original.log). Không suy ra các rule khác đều được bảo vệ.

Script cô lập đã chạy lại thành công với PostgreSQL test: [original](evidence/mutation-reproduction/original.log), [mutant](evidence/mutation-reproduction/mutation.log), [restored](evidence/mutation-reproduction/restored.log), [diff](evidence/mutation-reproduction/mutation.patch). Xem lệnh trong README; trap dọn worktree tạm.
