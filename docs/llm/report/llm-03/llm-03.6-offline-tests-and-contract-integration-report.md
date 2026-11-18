# LLM-03.6 — Báo cáo kiểm thử offline và tích hợp Contract

## 1. Tổng quan

- **Mục tiêu:** xác minh pipeline Summary/Action Items, provider adapter và HTTP Contract v1 bằng test offline; chỉ thêm test cho khoảng trống đã xác nhận.
- **Phạm vi:** unit, integration, contract và báo cáo nghiệm thu. Không đổi production code, Contract v1, prompt, provider interface hay dependencies.
- **Phụ thuộc:** LLM-03.2–03.5 (provider, prompt/candidate, orchestration, evidence và safeguards).
- **Trạng thái bắt đầu:** branch `feature/llm-03-provider-integration`, working tree sạch.
- **Commit SHA dùng để audit:** `a23b05f1a097e391573169162a35e3837ace6a2c`.
- **Kết quả audit:** phần lớn coverage đã có. Thêm test cho stage order, response Contract v1 có nhiều topic/Action Item và owner thiếu (có/không có speaker mapping).

## 2. Test Coverage Audit

| ID | Hành vi cần kiểm tra | Thành phần production | Test hiện có và bằng chứng | Trạng thái | Khoảng trống / hành động |
|---|---|---|---|---|---|
| T01 | Prompt extraction/evidence đúng version; module, ngôn ngữ, transcript, mapping, Unicode, template và prompt injection được xử lý đúng | `PromptRegistry`, `PromptRenderer`, `ExtractionPreflight`, `EvidenceVerifier` | `tests/unit/prompts/test_renderer.py`: `test_renders_supported_modules_and_output_language`, `test_preserves_transcript_segment_fields_order_unicode_and_unmapped_speaker`, `test_transcript_with_template_syntax_and_instructions_stays_literal_data`, `test_rejects_invalid_template_placeholders`; `tests/unit/prompts/test_registry.py`: `test_loads_approved_markdown_templates_and_versions`, `test_rejects_unsupported_prompt_versions`; `tests/unit/services/test_preflight.py`: `test_approved_prompt_version_is_resolved_without_fallback`, `test_only_existing_speaker_mappings_are_rendered`; `tests/unit/services/test_evidence_verification.py`: `test_supported_summary_and_action_claims_are_bound_to_verifier_metadata`, `test_evidence_v1_3_keeps_ordinary_claim_grounding_and_preserves_prior_versions` | Đầy đủ | Không thêm test. Có assertion `extract-v1.0`, `evidence-v1.3`, module selection, VI/EN, thứ tự/ID segment, mapping và injection literal. |
| T02 | OpenRouter request, model/config, structured output, response parsing, usage và lỗi an toàn | `OpenRouterAdapter`, provider error models | `tests/unit/providers/test_openrouter.py`: `test_success_request_normalization_and_configuration`, `test_request_values_override_defaults_and_text_mode`, `test_malformed_envelope_is_rejected`, `test_empty_or_unusable_content_is_rejected`, `test_truncated_content_is_rejected`, `test_http_errors_make_one_attempt_without_leaking_body`, `test_provider_timeout`, `test_total_timeout_cancels_slow_transport`, `test_network_failure_is_sanitized`, `test_provider_error_does_not_retain_sensitive_http_exception`, `test_settings_read_key_from_environment_and_mask_it`; `tests/unit/providers/test_provider_errors.py`: `test_error_classification`, `test_invalid_retry_delay_is_rejected` | Đầy đủ | Không thêm test. Adapter dùng `httpx.MockTransport`, không gửi request thật. |
| T03 | Extraction orchestration, metadata, lỗi candidate, isolation, stage order và chỉ publish sau verification | `CandidateExtractionOrchestrator`, `VerifiedExtractionService`, projector, source/evidence/temporal stages, response builder | `tests/unit/services/test_orchestration.py`: `test_summary_only_run_returns_parsed_unverified_candidate`, `test_summary_and_actions_run_once_and_preserve_both_modules`, `test_provider_errors_propagate_unchanged_without_retry`, `test_malformed_candidate_json_propagates_format_error_without_retry`, `test_success_populates_actual_processing_metadata_in_utc`; `tests/integration/test_verified_extraction_service.py`: `test_unknown_source_id_returns_unverified_evidence_error`, `test_candidate_schema_failure_returns_invalid_structured_output`, `test_full_pipeline_remains_request_isolated_under_concurrency` | Đầy đủ sau bổ sung | Trước đây chưa có assertion trực tiếp pin thứ tự sáu stage; thêm `test_verified_pipeline_runs_mandatory_stages_in_order`. Lỗi source bị chặn trước verifier và candidate lỗi không được publish cũng đã được kiểm tra. |
| T04 | FastAPI composition thật dùng fake provider; response HTTP tuân thủ Contract v1 | `create_app`, route, dependency injection, verified service | `tests/integration/test_verified_extraction_service.py`: `client_for`, `test_verified_pipeline_returns_contract_response_for_requested_modules`, `test_provider_errors_map_without_exposing_provider_details`; `tests/integration/test_runtime.py`: `test_extraction_validates_request_before_calling_service`, `test_malformed_json_uses_contract_error_envelope` | Đầy đủ sau bổ sung | Happy path cũ chưa xác nhận đồng thời metadata identity, timestamp nguồn, artifact ID và response model cho nhiều artifacts; thêm `test_contract_response_preserves_multiple_topics_and_independently_verified_actions`. |
| T05 | Summary + Actions hợp lệ; module null đúng; nhiều topics và tasks khác owner/deadline | `VerifiedExtractionService`, `ResponseBuilder`, Contract v1 | `tests/integration/test_verified_extraction_service.py`: `test_verified_pipeline_returns_contract_response_for_requested_modules`, `test_supported_owner_is_preserved_after_reassignment_across_segments`; `tests/unit/services/test_response_builder.py`: `test_response_preserves_requested_and_unrequested_module_states`, `test_action_items_sort_by_source_time_then_receive_response_local_ids` | Đầy đủ sau bổ sung | Thêm scenario end-to-end có hai topics và hai Action Items với owner, ngày, source segment và timestamp riêng. Validate trực tiếp `ExtractionResponse` và `validate_response_for_request`. |
| T06 | Action Items rỗng chỉ thành công khi absence được xác minh | `SourceValidator`, `EvidenceVerifier`, `TemporalReviewProcessor`, response builder | `tests/integration/test_verified_extraction_service.py`: `test_verified_empty_actions_returns_empty_list_for_discussion_without_commitment`, `test_uncertain_empty_action_absence_fails_closed`, `test_empty_actions_contradicted_by_transcript_commitment_fails_closed`; `tests/unit/services/test_temporal_safeguards.py`: `test_verified_empty_actions_is_distinguished_from_failed_items` | Đầy đủ | Không thêm test. Verdict scripted kiểm tra chính sách pipeline, không phải khả năng model phát hiện item bị bỏ sót. |
| T07 | Owner thiếu/không chắc/không được hỗ trợ không bị xác nhận; mapping/reassignment không bị Python suy đoán sai | `TemporalReviewProcessor`, evidence verifier | `tests/integration/test_verified_extraction_service.py`: `test_uncertain_owner_is_null_and_reviewable`, `test_unsupported_owner_is_cleared_while_supported_task_remains`, `test_multiple_supported_assignments_in_one_segment_keep_their_owners`, `test_supported_owner_is_preserved_after_reassignment_across_segments`; `tests/unit/services/test_temporal_safeguards.py`: `test_uncertain_first_person_owner_without_speaker_mapping_remains_unconfirmed`, `test_supported_owner_is_not_overridden_by_first_person_speaker_mapping` | Đầy đủ sau bổ sung | HTTP path chưa kiểm tra candidate owner vốn null. Thêm `test_missing_owner_is_null_and_reviewable_in_contract_response` cho mapping có/không; khi thiếu mapping vẫn trả null cùng `speaker_unmapped`. |
| T08 | JSON/schema candidate/verifier sai không được sửa tự động hoặc trả HTTP 200 | parser, schemas, `EvidenceVerifier`, error mapping | `tests/unit/parsing/test_candidate_parser.py`: `test_rejects_empty_malformed_or_non_json_content`, `test_rejects_candidate_schema_violations`; `tests/unit/services/test_evidence_verification.py`: `test_incomplete_or_unrecognized_verifier_output_fails_closed`, `test_malformed_json_is_not_repaired_or_approved`; `tests/integration/test_verified_extraction_service.py`: `test_candidate_schema_failure_returns_invalid_structured_output`, `test_verifier_schema_failure_returns_invalid_structured_output` | Đầy đủ | Missing/extra/duplicate claim IDs và status sai được kiểm tra ở verifier unit tests; public error mapping được kiểm tra integration. |
| T09 | Source ID không tồn tại hoặc trùng không tạo kết quả sai | `SourceValidator`, candidate/request schemas | `tests/unit/services/test_source_validation.py`: `test_unknown_summary_source_fails_without_repair`, `test_duplicate_source_ids_are_rejected_even_if_candidate_was_constructed_unsafely`; `tests/integration/test_verified_extraction_service.py`: `test_unknown_source_id_returns_unverified_evidence_error`; `tests/contract/test_request_models.py`: `test_duplicate_segment_ids_are_rejected` | Đầy đủ | Không thêm test. HTTP unknown source trả 502 `UNVERIFIED_EVIDENCE`; duplicate bị chặn ở unit/schema layer. |
| T10 | Auth, rate limit, provider timeout/failure, request timeout, malformed input và payload limit dùng đúng status/error, không lộ dữ liệu | adapter, service error mapping, FastAPI middleware | `tests/unit/providers/test_openrouter.py`: `test_http_errors_make_one_attempt_without_leaking_body`, `test_provider_timeout`, `test_network_failure_is_sanitized`; `tests/integration/test_verified_extraction_service.py`: `test_provider_errors_map_without_exposing_provider_details`, `test_provider_timeout_setting_bounds_each_call`, `test_request_timeout_maps_separately_from_provider_timeout`, `test_missing_or_invalid_bearer_token_returns_401_without_provider_call`; `tests/integration/test_runtime.py`: `test_malformed_json_uses_contract_error_envelope`, `test_unsupported_contract_version_maps_to_dedicated_error`, `test_n14_valid_json_one_byte_over_limit_is_rejected_without_dispatch` | Đầy đủ | Đã xác nhận `PROVIDER_TIMEOUT` → 504, `PROVIDER_RATE_LIMIT` → 503. Provider auth 401/403, network, request timeout và body size có test riêng. |
| T11 | LLM-01/02 contracts/runtime tiếp tục tương thích; suite chạy offline, không cần key/mạng | request/response/error schemas, FastAPI runtime, test harness | `tests/contract/test_request_models.py`, `test_response_models.py`, `test_error_models.py`, `test_schema_generation.py`; `tests/integration/test_runtime.py`: `test_openapi_exposes_contract_models_security_and_error_responses`, `test_application_lifecycle_runs_with_injected_settings`; `tests/conftest.py`: `isolate_provider_environment_and_network` | Đầy đủ | Không thêm test. Full suite bao gồm regression contract/runtime; fixture isolation gỡ `OPENROUTER_API_KEY` và chặn HTTP outbound. |

Các phần overlap kiểm tra ở những lớp khác nhau (adapter, service, HTTP, schema); không tìm thấy test trùng hoàn toàn cần xóa. Fake provider với verdict scripted chỉ chứng minh pipeline áp dụng policy/contract.

## 3. Gaps Identified

- **Đã đóng:** thiếu assertion trực tiếp về thứ tự `CandidateExtractionOrchestrator → ExtractionProjector → SourceValidator → EvidenceVerifier → TemporalReviewProcessor → ResponseBuilder`.
- **Đã đóng:** HTTP response cho nhiều topics, tasks, owners/deadlines chưa được parse và cross-validate trực tiếp theo Contract v1; bổ sung identity, null module, artifact ID, source timestamp và provider/prompt/model metadata.
- **Đã đóng:** owner thiếu chưa có assertion ở public verified pipeline; bổ sung trường hợp có/không speaker mapping.
- **Không tìm thấy gap khác cần thêm test** cho T01–T11. Các test overlap ở unit/integration/contract kiểm tra ranh giới khác nhau.
- **Giới hạn không thể giải quyết bằng offline fixture:** fake provider không kiểm chứng semantic accuracy; Action Item bị bỏ sót khi candidate không rỗng chưa có completeness engine; độ chính xác owner-task cần đánh giá model thật; model có thể không chuẩn hóa ngày tự nhiên; byte limit không chứng minh transcript vừa context window; latency/token cost thật chưa được đo.

## 4. Tests Added or Updated

| File | Thay đổi và lý do | Tình huống / hành vi mong đợi | Kết quả thực tế |
|---|---|---|---|
| `apps/llm-service/tests/integration/test_verified_extraction_service.py` | Thêm 3 test function; synthetic data nằm inline, không thêm fixture file. | `test_verified_pipeline_runs_mandatory_stages_in_order` pin stage order và đúng 2 provider generations. `test_contract_response_preserves_multiple_topics_and_independently_verified_actions` kiểm tra 2 topics, 2 owners/deadlines, source refs/timestamps, IDs ACT-001/002, provider/model/prompt/token metadata và Contract v1. `test_missing_owner_is_null_and_reviewable_in_contract_response` chạy khi mapping có/thiếu; owner luôn null và cần review. | File integration tập trung: **48 passed**. Regression: unit **335**, integration **144**, contract **111**, full **590 passed**. |

Trong lượt test đầu, test mới dùng duration 30 giây cho segment kết thúc ở 41 giây nên schema trả đúng 400. Sau khi tăng duration synthetic, assertion tiếp theo phát hiện Pydantic parse ngày thành `date`; assertion chuyển sang so sánh ISO date. Đây là lỗi dữ liệu/assertion của test, không phải lỗi production. Không sửa kỳ vọng để che lỗi ứng dụng.

## 5. Offline Regression Results

| Test suite | Tests passed | Tests failed | Result |
|---|---:|---:|---|
| Unit | 335 | 0 | PASS |
| Integration | 144 | 0 | PASS |
| Contract | 111 | 0 | PASS |
| Full suite | 590 | 0 | PASS |

Chạy tại `apps/llm-service/`:

```bash
uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/unit
uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/integration
uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q tests/contract
uv --cache-dir /tmp/se-llm-uv-cache run --locked --extra test pytest -q
```

Kết quả lần chạy cuối: Full suite `590 passed in 5.97s`; targeted `tests/integration/test_verified_extraction_service.py` `48 passed in 2.00s`. Unit `335 passed in 1.84s`, integration `144 passed in 3.61s`, contract `111 passed in 0.75s`. Các số baseline 550 trong báo cáo LLM-03.5 là lịch sử, không dùng thay kết quả hiện tại. Không chạy script trong `tests/manual/`.

`tests/conftest.py` gỡ `OPENROUTER_API_KEY`, thay HTTP sync/async transport bằng hàm ném lỗi khi có outbound. Adapter test dùng `httpx.MockTransport`; pipeline dùng `ScriptedProvider`. Pytest không cần API key, không gửi OpenRouter request và không phát sinh billing.

## 6. Known Limitations

- **Fake provider và semantic accuracy:** verdict `supported`/`uncertain` được lập trình sẵn để kiểm tra policy; không chứng minh model thật hiểu transcript.
- **Action Item recall:** candidate không rỗng chỉ kiểm tra các claim hiện có, chưa xác nhận danh sách đầy đủ. Candidate rỗng tạo `actions.absence` claim để verifier đánh giá transcript; omission vẫn là rủi ro đã biết.
- **Owner attribution:** test reassignment, nhiều owner, owner thiếu/uncertain chứng minh cách xử lý verdict. Độ chính xác gán task cho người trong hội thoại thật cần đánh giá model.
- **Natural-language dates:** prompt yêu cầu giữ `raw_due_expression` nguyên văn. Test transcript có ngày tự nhiên nhưng fake candidate đưa ISO chỉ chứng minh pipeline chấp nhận ISO theo verdict. Expression tự nhiên không canonical được giữ raw và trả unresolved; không chứng minh model tự chuẩn hóa ngày. Relative-date resolution đầy đủ thuộc LLM-04.
- **Context window:** test large input tạo request hợp lệ gần byte limit 1 MiB, xác nhận request tới extractor rồi bị request timeout và cancel. Đây không phải kiểm chứng model context window; byte cap không đảm bảo vừa context.
- **Provider vận hành:** latency, token cost và độ ổn định OpenRouter thật chưa được đo trong milestone offline.
- **Completion notification:** `test_notifier_exception_preserves_response_and_safe_diagnostics`, `test_task_scheduling_failure_preserves_response_and_safe_diagnostics` và `test_notifier_timeout_is_bounded_and_cancels_dispatch` xác nhận lỗi notification không đổi response thành công; không tạo transport mới.

## 7. Acceptance Criteria

- [x] Fake provider và adapter tests chạy offline.
- [x] Pytest mặc định không cần API key; outbound HTTP bị chặn.
- [x] LLM-01/02 contract/runtime regression tiếp tục pass trong full suite.
- [x] JSON/schema/source/provider/auth/request/body-size errors được kiểm tra theo HTTP/error contract.
- [x] Test dùng fixture tổng hợp, deterministic; không gọi provider thật.
- [x] Không thay production code, Contract v1, prompt, provider interface hay dependencies.
- [x] Unit, integration, contract và full regression đều pass.

## 8. Kết luận cuối

**PASS — LLM-03.6 accepted.** T01–T11 có coverage phù hợp; ba test function bổ sung lấp các gap về stage order, public Contract v1 với nhiều artifacts và owner null. Unit **335**, integration **144**, contract **111**, full suite **590 passed**. Tests chạy offline với network isolation, không gọi provider thật. Bước kế tiếp: **LLM-03.7 — Real Provider Evaluation**; giới hạn semantic accuracy và context window cần đo ở milestone đó.
