"""Conservative temporal, owner, priority, and review-state tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.schemas.candidates import SummaryActionsCandidate
from app.schemas.request import ExtractionRequest
from app.services.models import PreparedExtraction
from app.services.projection import ExtractionProjector
from app.services.source_validation import SourceValidator
from app.services.temporal_safeguards import TemporalReviewProcessor
from app.services.validation_models import (
    EvidenceVerificationFailure,
    EvidenceVerifiedExtraction,
    VerificationMetadata,
    VerificationStatus,
    VerificationVerdict,
)


REQUEST_FIXTURE = Path(__file__).parents[2] / "fixtures/requests/summary_actions_request.json"


def make_verified(
    *,
    due: str | None = None,
    owner: str | None = "Alex",
    priority: str | None = None,
    action_task: str = "Gửi bản ghi chú",
    actions: list[dict[str, object]] | None = None,
    status_overrides: dict[str, str] | None = None,
    mapped_speaker: bool = True,
    transcript_segments: list[dict[str, object]] | None = None,
    participants: list[dict[str, object]] | None = None,
    action_source_ids: list[str] | None = None,
    summary_topics: list[dict[str, object]] | None = None,
    summary_overview: str = "Nhóm rà soát tiến độ.",
) -> EvidenceVerifiedExtraction:
    payload = json.loads(REQUEST_FIXTURE.read_text(encoding="utf-8"))
    if transcript_segments is not None:
        payload["transcript"]["segments"] = transcript_segments
    if not mapped_speaker:
        payload["transcript"]["segments"][0]["speaker_id"] = "speaker-unmapped"
        payload["meeting"]["participants"][0]["speaker_ids"] = []
    if participants is not None:
        payload["meeting"]["participants"] = participants
    request = ExtractionRequest.model_validate(payload)
    action_data = actions
    if action_data is None:
        action_data = [
            {
                "task": action_task,
                "owner": owner,
                "raw_due_expression": due,
                "priority": priority,
                "context": None,
                "source_segment_ids": action_source_ids or ["seg-a1"],
            }
        ]
    candidate = SummaryActionsCandidate.model_validate(
        {
            "meeting_summary": {
                "overview": summary_overview,
                "key_topics": summary_topics or [],
                "source_segment_ids": ["seg-a2"],
            },
            "action_items": action_data,
        }
    )
    prepared = PreparedExtraction(
        request=request,
        candidate=candidate,
        prompt_version="extract-v1.0",
        candidate_schema_version="candidate-v1",
        model_id="safeguard-model",
        provider="safeguard-provider",
    )
    source = SourceValidator().validate(ExtractionProjector().project(prepared))
    overrides = status_overrides or {}
    verdicts = tuple(
        VerificationVerdict(
            request_id=claim.request_id,
            transcript_revision_id=claim.transcript_revision_id,
            claim_id=claim.claim_id,
            status=VerificationStatus(overrides.get(claim.claim_id, "supported")),
        )
        for claim in source.claims
    )
    return EvidenceVerifiedExtraction(
        source_validated=source,
        verdicts=verdicts,
        metadata=VerificationMetadata(
            provider="safeguard-provider",
            model_id="safeguard-model",
            prompt_version="evidence-v1.1",
            token_usage=None,
            started_at=None,
            completed_at=None,
        ),
    )


@pytest.mark.parametrize("due", ["2026-12-15"], ids=["exact-iso"])
def test_unambiguous_iso_deadline_resolves_deterministically(due: str) -> None:
    result = TemporalReviewProcessor().process(
        make_verified(
            due=due,
            transcript_segments=[
                {
                    "id": "seg-a1",
                    "start": 12.5,
                    "end": 18.2,
                    "speaker_id": "speaker_1",
                    "text": f"Hạn chót là {due}.",
                },
                {
                    "id": "seg-a2",
                    "start": 18.3,
                    "end": 22.0,
                    "speaker_id": "speaker_1",
                    "text": "Hôm nay chủ yếu rà lại tiến độ.",
                },
            ],
        )
    )

    assert result.action_due_dates == ("2026-12-15",)
    resolution = result.action_due_resolutions[0]
    assert resolution.status == "exact_date"
    assert resolution.resolved_date.isoformat() == due
    assert resolution.source_segment_ids == ["seg-a1"]


def test_unsupported_deadline_in_unrelated_cited_text_is_cleared():
    result = TemporalReviewProcessor().process(
        make_verified(
            due="2026-12-15",
            status_overrides={"actions[0].raw_due_expression": "unsupported"},
            transcript_segments=[
                {
                    "id": "seg-a1",
                    "start": 12.5,
                    "end": 18.2,
                    "speaker_id": "speaker_1",
                    "text": "Nhóm rà soát tiến độ.",
                },
                {
                    "id": "seg-a2",
                    "start": 18.3,
                    "end": 22.0,
                    "speaker_id": "speaker_1",
                    "text": "Hạn chót là 2026-12-15.",
                },
            ],
            action_source_ids=["seg-a1"],
        )
    )

    assert result.action_items[0].raw_due_expression is None
    assert result.action_due_dates == (None,)
    assert result.action_due_resolutions == (None,)
    assert "evidence_unverified" in result.action_review_reasons[0]


def test_verifier_rejects_canonical_date_contradicted_by_cited_text():
    result = TemporalReviewProcessor().process(
        make_verified(
            due="2026-12-15",
            status_overrides={"actions[0].raw_due_expression": "unsupported"},
            transcript_segments=[
                {
                    "id": "seg-a1",
                    "start": 12.5,
                    "end": 18.2,
                    "speaker_id": "speaker_1",
                    "text": "Hạn chót là 2026-12-18.",
                },
                {
                    "id": "seg-a2",
                    "start": 18.3,
                    "end": 22.0,
                    "speaker_id": "speaker_1",
                    "text": "Hôm nay chủ yếu rà lại tiến độ.",
                },
            ],
        )
    )

    assert result.action_items[0].raw_due_expression is None
    assert result.action_due_dates == (None,)
    assert result.action_due_resolutions == (None,)
    assert "evidence_unverified" in result.action_review_reasons[0]


def test_leap_day_is_valid_when_canonical_iso_appears_in_cited_source():
    result = TemporalReviewProcessor().process(
        make_verified(
            due="2024-02-29",
            transcript_segments=[
                {
                    "id": "seg-a1",
                    "start": 12.5,
                    "end": 18.2,
                    "speaker_id": "speaker_1",
                    "text": "Hạn chót là 2024-02-29.",
                },
                {
                    "id": "seg-a2",
                    "start": 18.3,
                    "end": 22.0,
                    "speaker_id": "speaker_1",
                    "text": "Hôm nay chủ yếu rà lại tiến độ.",
                },
            ],
        )
    )

    assert result.action_due_dates == ("2024-02-29",)


def test_temporal_resolution_preserves_claim_level_source_ids():
    result = TemporalReviewProcessor().process(
        make_verified(
            due="2026-12-15",
            action_source_ids=["seg-a1", "seg-a2"],
            transcript_segments=[
                {
                    "id": "seg-a1",
                    "start": 12.5,
                    "end": 18.2,
                    "speaker_id": "speaker_1",
                    "text": "Nhóm rà soát giao diện.",
                },
                {
                    "id": "seg-a2",
                    "start": 18.3,
                    "end": 22.0,
                    "speaker_id": "speaker_1",
                    "text": "Hạn chót là 2026-12-15.",
                },
            ],
        )
    )

    resolution = result.action_due_resolutions[0]
    assert resolution.status == "exact_date"
    assert resolution.source_segment_ids == ["seg-a1", "seg-a2"]


def test_supported_vietnamese_natural_date_resolves_canonical_candidate():
    result = TemporalReviewProcessor().process(
        make_verified(
            due="2026-12-15",
            transcript_segments=[
                {
                    "id": "seg-a1",
                    "start": 12.5,
                    "end": 18.2,
                    "speaker_id": "speaker_1",
                    "text": "Hạn chót là ngày 15 tháng 12 năm 2026.",
                },
                {
                    "id": "seg-a2",
                    "start": 18.3,
                    "end": 22.0,
                    "speaker_id": "speaker_1",
                    "text": "Hôm nay chủ yếu rà lại tiến độ.",
                },
            ],
        )
    )

    assert result.action_due_dates == ("2026-12-15",)
    assert result.action_due_resolutions[0].status == "exact_date"
    assert result.action_due_resolutions[0].source_segment_ids == ["seg-a1"]
    assert result.action_review_reasons[0] == ()


def test_supported_english_natural_date_resolves_canonical_candidate():
    result = TemporalReviewProcessor().process(
        make_verified(
            due="2026-12-15",
            transcript_segments=[
                {
                    "id": "seg-a1",
                    "start": 12.5,
                    "end": 18.2,
                    "speaker_id": "speaker_1",
                    "text": "The API must be ready by December 15, 2026.",
                },
                {
                    "id": "seg-a2",
                    "start": 18.3,
                    "end": 22.0,
                    "speaker_id": "speaker_1",
                    "text": "We reviewed the project status.",
                },
            ],
        )
    )

    assert result.action_due_dates == ("2026-12-15",)
    assert result.action_due_resolutions[0].status == "exact_date"
    assert result.action_review_reasons[0] == ()


@pytest.mark.parametrize("due", ["15 tháng 12", "thứ Sáu tuần sau"])
def test_uncertain_noncanonical_deadline_remains_reviewable(due: str):
    result = TemporalReviewProcessor().process(
        make_verified(
            due=due,
            status_overrides={"actions[0].raw_due_expression": "uncertain"},
        )
    )

    assert result.action_items[0].raw_due_expression == due
    assert result.action_due_dates == (None,)
    assert result.action_due_resolutions[0].status == "unresolved"
    assert result.action_due_resolutions[0].needs_review is True
    assert "temporal_unresolved" in result.action_review_reasons[0]
    assert "claim_uncertain" in result.action_review_reasons[0]


def test_unsupported_deadline_does_not_remove_independently_supported_task():
    result = TemporalReviewProcessor().process(
        make_verified(
            due="2027-01-01",
            status_overrides={"actions[0].raw_due_expression": "unsupported"},
        )
    )

    assert len(result.action_items) == 1
    assert result.action_items[0].task == "Gửi bản ghi chú"
    assert result.action_items[0].raw_due_expression is None
    assert result.action_due_dates == (None,)
    assert result.action_due_resolutions == (None,)
    assert result.action_review_reasons[0] == ("evidence_unverified",)


def test_uncertain_proposed_deadline_change_stays_unresolved():
    result = TemporalReviewProcessor().process(
        make_verified(
            due="2026-12-20",
            status_overrides={"actions[0].raw_due_expression": "uncertain"},
            transcript_segments=[
                {
                    "id": "seg-a1",
                    "start": 12.5,
                    "end": 18.2,
                    "speaker_id": "speaker_1",
                    "text": "API hoàn thành ngày 2026-12-15.",
                },
                {
                    "id": "seg-a2",
                    "start": 18.3,
                    "end": 22.0,
                    "speaker_id": "speaker_1",
                    "text": "Hay chuyển hạn sang 2026-12-20?",
                },
            ],
            action_source_ids=["seg-a1", "seg-a2"],
        )
    )

    assert result.action_items[0].raw_due_expression == "2026-12-20"
    assert result.action_due_dates == (None,)
    assert result.action_due_resolutions[0].status == "unresolved"
    assert "claim_uncertain" in result.action_review_reasons[0]
    assert "temporal_unresolved" in result.action_review_reasons[0]


def test_correction_for_ui_does_not_conflict_with_supported_api_deadline():
    result = TemporalReviewProcessor().process(
        make_verified(
            due="2026-12-15",
            action_task="Hoàn thành API",
            transcript_segments=[
                {
                    "id": "seg-a1",
                    "start": 1.0,
                    "end": 2.0,
                    "speaker_id": "speaker_1",
                    "text": "API hoàn thành ngày 2026-12-15.",
                },
                {
                    "id": "seg-a2",
                    "start": 2.1,
                    "end": 4.0,
                    "speaker_id": "speaker_2",
                    "text": "Đính chính hạn UI: không phải 2026-12-15, chuyển sang 2026-12-20.",
                },
            ],
            action_source_ids=["seg-a1", "seg-a2"],
        )
    )

    assert result.action_items[0].task == "Hoàn thành API"
    assert result.action_due_dates == ("2026-12-15",)
    assert result.action_due_resolutions[0].status == "exact_date"
    assert result.action_review_reasons[0] == ()


def test_supported_final_natural_language_correction_is_not_auto_rewritten():
    result = TemporalReviewProcessor().process(
        make_verified(
            due="2026-12-20",
            action_task="Hoàn thành API",
            action_source_ids=["seg-a1", "seg-a2"],
            transcript_segments=[
                {
                    "id": "seg-a1",
                    "start": 1.0,
                    "end": 2.0,
                    "speaker_id": "speaker_1",
                    "text": "API hoàn thành ngày 2026-12-15.",
                },
                {
                    "id": "seg-a2",
                    "start": 2.1,
                    "end": 4.0,
                    "speaker_id": "speaker_1",
                    "text": "Chốt lại, API chuyển sang ngày 20 tháng 12 năm 2026.",
                },
            ],
        )
    )

    assert result.action_items[0].raw_due_expression == "2026-12-20"
    assert result.action_due_dates == ("2026-12-20",)
    assert result.action_due_resolutions[0].status == "exact_date"
    assert result.action_due_resolutions[0].source_segment_ids == ["seg-a1", "seg-a2"]


def test_unsupported_obsolete_deadline_is_cleared_without_replacement():
    result = TemporalReviewProcessor().process(
        make_verified(
            due="2026-12-15",
            status_overrides={"actions[0].raw_due_expression": "unsupported"},
            transcript_segments=[
                {
                    "id": "seg-a1",
                    "start": 12.5,
                    "end": 18.2,
                    "speaker_id": "speaker_1",
                    "text": "API deadline là 2026-12-15.",
                },
                {
                    "id": "seg-a2",
                    "start": 18.3,
                    "end": 22.0,
                    "speaker_id": "speaker_1",
                    "text": "Chốt lại, API chuyển sang 2026-12-20.",
                },
            ],
            action_source_ids=["seg-a1", "seg-a2"],
        )
    )

    assert result.action_items[0].raw_due_expression is None
    assert result.action_due_dates == (None,)
    assert result.action_due_resolutions == (None,)
    assert "evidence_unverified" in result.action_review_reasons[0]


@pytest.mark.parametrize(
    "due",
    ["thứ Sáu tới", "tuần sau", "03/04/2026", "2026-02-31"],
    ids=["relative-weekday", "relative-week", "ambiguous-date", "invalid-date"],
)
def test_non_iso_or_invalid_deadline_stays_unresolved(due: str) -> None:
    result = TemporalReviewProcessor().process(make_verified(due=due))

    assert result.action_items[0].raw_due_expression == due
    assert result.action_due_dates == (None,)
    assert result.action_due_resolutions[0].status == "unresolved"
    assert "temporal_unresolved" in result.action_review_reasons[0]


def test_missing_deadline_has_all_temporal_fields_null():
    result = TemporalReviewProcessor().process(make_verified(due=None))

    assert result.action_items[0].raw_due_expression is None
    assert result.action_due_dates == (None,)
    assert result.action_due_resolutions == (None,)


def test_unsupported_owner_is_cleared_and_reviewed():
    result = TemporalReviewProcessor().process(
        make_verified(status_overrides={"actions[0].owner": "unsupported"})
    )

    assert result.action_items[0].owner is None
    assert result.action_review_reasons[0] == ("owner_unconfirmed",)


def test_uncertain_first_person_owner_without_speaker_mapping_remains_unconfirmed():
    result = TemporalReviewProcessor().process(
        make_verified(
            mapped_speaker=False,
            status_overrides={"actions[0].owner": "uncertain"},
        )
    )

    assert result.action_items[0].owner is None
    assert result.action_review_reasons[0] == (
        "owner_unconfirmed",
        "speaker_unmapped",
        "claim_uncertain",
    )


def test_supported_owner_is_preserved_when_speaker_mapping_is_missing():
    result = TemporalReviewProcessor().process(
        make_verified(
            mapped_speaker=False,
            status_overrides={"actions[0].owner": "supported"},
        )
    )

    assert result.action_items[0].owner == "Alex"
    assert result.action_review_reasons[0] == ()


def test_verified_speaker_mapping_allows_explicit_first_person_owner():
    result = TemporalReviewProcessor().process(make_verified())

    assert result.action_items[0].owner == "Alex"
    assert result.action_review_reasons[0] == ()


def test_supported_owner_is_not_overridden_by_first_person_speaker_mapping():
    result = TemporalReviewProcessor().process(
        make_verified(
            owner="Minh",
            status_overrides={"actions[0].owner": "supported"},
        )
    )

    assert result.action_items[0].owner == "Minh"
    assert result.action_review_reasons[0] == ()


def test_explicit_named_assignment_is_not_rejected_for_different_speaker():
    result = TemporalReviewProcessor().process(
        make_verified(
            owner="Minh",
            action_task="Hoàn thiện API",
            transcript_segments=[
                {
                    "id": "seg-a1",
                    "start": 12.5,
                    "end": 18.2,
                    "speaker_id": "speaker_1",
                    "text": "Minh nhận hoàn thiện API.",
                },
                {
                    "id": "seg-a2",
                    "start": 18.3,
                    "end": 22.0,
                    "speaker_id": "speaker_1",
                    "text": "Hôm nay chủ yếu rà lại tiến độ.",
                },
            ],
            participants=[
                {"id": "participant-alex", "display_name": "Alex", "speaker_ids": ["speaker_1"]},
                {"id": "participant-minh", "display_name": "Minh", "speaker_ids": ["speaker_2"]},
            ],
        )
    )

    assert result.action_items[0].owner == "Minh"
    assert result.action_review_reasons[0] == ()


def test_supported_owner_survives_reassignment_after_earlier_commitment():
    result = TemporalReviewProcessor().process(
        make_verified(
            owner="Lan",
            action_task="Sửa giao diện",
            action_source_ids=["seg-a1", "seg-a2"],
            transcript_segments=[
                {
                    "id": "seg-a1",
                    "start": 1.0,
                    "end": 2.0,
                    "speaker_id": "speaker_1",
                    "text": "Tôi sẽ sửa giao diện.",
                },
                {
                    "id": "seg-a2",
                    "start": 2.1,
                    "end": 3.0,
                    "speaker_id": "speaker_1",
                    "text": "Chốt lại, Lan sẽ sửa giao diện thay tôi.",
                },
            ],
            participants=[
                {"id": "participant-minh", "display_name": "Minh", "speaker_ids": ["speaker_1"]},
                {"id": "participant-lan", "display_name": "Lan", "speaker_ids": ["speaker_2"]},
            ],
        )
    )

    assert result.action_items[0].owner == "Lan"
    assert result.action_review_reasons[0] == ()


def test_supported_owner_survives_multiple_participants_committing_same_task():
    result = TemporalReviewProcessor().process(
        make_verified(
            owner="Lan",
            action_task="Kiểm thử API",
            action_source_ids=["seg-a1", "seg-a2"],
            transcript_segments=[
                {
                    "id": "seg-a1",
                    "start": 1.0,
                    "end": 2.0,
                    "speaker_id": "speaker_1",
                    "text": "Tôi sẽ kiểm thử API.",
                },
                {
                    "id": "seg-a2",
                    "start": 2.1,
                    "end": 3.0,
                    "speaker_id": "speaker_2",
                    "text": "Tôi cũng sẽ kiểm thử API cùng Minh.",
                },
            ],
            participants=[
                {"id": "participant-minh", "display_name": "Minh", "speaker_ids": ["speaker_1"]},
                {"id": "participant-lan", "display_name": "Lan", "speaker_ids": ["speaker_2"]},
            ],
        )
    )

    assert result.action_items[0].owner == "Lan"
    assert result.action_review_reasons[0] == ()


def test_supported_reassignment_survives_cancelled_earlier_commitment():
    result = TemporalReviewProcessor().process(
        make_verified(
            owner="Lan",
            action_task="Viết tài liệu",
            action_source_ids=["seg-a1", "seg-a2"],
            transcript_segments=[
                {
                    "id": "seg-a1",
                    "start": 1.0,
                    "end": 2.0,
                    "speaker_id": "speaker_1",
                    "text": "Tôi sẽ viết tài liệu.",
                },
                {
                    "id": "seg-a2",
                    "start": 2.1,
                    "end": 3.0,
                    "speaker_id": "speaker_1",
                    "text": "Tôi không làm phần đó nữa. Lan sẽ viết tài liệu.",
                },
            ],
            participants=[
                {"id": "participant-minh", "display_name": "Minh", "speaker_ids": ["speaker_1"]},
                {"id": "participant-lan", "display_name": "Lan", "speaker_ids": ["speaker_2"]},
            ],
        )
    )

    assert result.action_items[0].owner == "Lan"
    assert result.action_review_reasons[0] == ()


def test_multiple_assignments_in_one_sentence_preserve_each_supported_owner():
    result = TemporalReviewProcessor().process(
        make_verified(
            actions=[
                {
                    "task": "Gửi bản ghi chú",
                    "owner": "Minh",
                    "raw_due_expression": None,
                    "priority": None,
                    "context": None,
                    "source_segment_ids": ["seg-a1"],
                },
                {
                    "task": "Sửa giao diện",
                    "owner": "Lan",
                    "raw_due_expression": None,
                    "priority": None,
                    "context": None,
                    "source_segment_ids": ["seg-a1"],
                },
            ],
            transcript_segments=[
                {
                    "id": "seg-a1",
                    "start": 1.0,
                    "end": 4.0,
                    "speaker_id": "speaker_1",
                    "text": "Tôi sẽ gửi bản ghi chú, Lan sẽ sửa giao diện.",
                },
                {
                    "id": "seg-a2",
                    "start": 4.1,
                    "end": 5.0,
                    "speaker_id": "speaker_1",
                    "text": "Hôm nay chủ yếu rà lại tiến độ.",
                },
            ],
            participants=[
                {"id": "participant-minh", "display_name": "Minh", "speaker_ids": ["speaker_1"]},
                {"id": "participant-lan", "display_name": "Lan", "speaker_ids": ["speaker_2"]},
            ],
        )
    )

    assert [item.owner for item in result.action_items] == ["Minh", "Lan"]
    assert result.action_review_reasons == ((), ())


@pytest.mark.parametrize(
    "text",
    [
        "Nếu tôi có thời gian, tôi sẽ gửi bản ghi chú.",
        "Alex nói: “Tôi sẽ gửi bản ghi chú.”",
        "Anh sẽ gửi bản ghi chú.",
    ],
    ids=["hypothetical", "quoted", "ambiguous-pronoun"],
)
def test_ambiguous_or_quoted_first_person_does_not_confirm_owner(text: str):
    result = TemporalReviewProcessor().process(
        make_verified(
            owner="Alex",
            status_overrides={"actions[0].owner": "uncertain"},
            transcript_segments=[
                {
                    "id": "seg-a1",
                    "start": 12.5,
                    "end": 18.2,
                    "speaker_id": "speaker_1",
                    "text": text,
                },
                {
                    "id": "seg-a2",
                    "start": 18.3,
                    "end": 22.0,
                    "speaker_id": "speaker_1",
                    "text": "Hôm nay chủ yếu rà lại tiến độ.",
                },
            ],
        )
    )

    assert result.action_items[0].owner is None
    assert result.action_review_reasons[0] == ("owner_unconfirmed", "claim_uncertain")


def test_multiple_first_person_sources_do_not_override_supported_owner_verdict():
    result = TemporalReviewProcessor().process(
        make_verified(
            owner="Alex",
            action_source_ids=["seg-a1", "seg-a2"],
            transcript_segments=[
                {
                    "id": "seg-a1",
                    "start": 1.0,
                    "end": 2.0,
                    "speaker_id": "speaker_1",
                    "text": "Tôi sẽ gửi bản ghi chú.",
                },
                {
                    "id": "seg-a2",
                    "start": 2.1,
                    "end": 3.0,
                    "speaker_id": "speaker_2",
                    "text": "Tôi sẽ gửi bản ghi chú.",
                },
            ],
            participants=[
                {"id": "participant-alex", "display_name": "Alex", "speaker_ids": ["speaker_1"]},
                {"id": "participant-minh", "display_name": "Minh", "speaker_ids": ["speaker_2"]},
            ],
        )
    )

    assert result.action_items[0].owner == "Alex"
    assert result.action_review_reasons[0] == ()


def test_unrelated_task_in_another_cited_segment_does_not_contradict_owner():
    result = TemporalReviewProcessor().process(
        make_verified(
            owner="Minh",
            action_task="Gửi bản ghi chú",
            action_source_ids=["seg-a1", "seg-a2"],
            transcript_segments=[
                {
                    "id": "seg-a1",
                    "start": 1.0,
                    "end": 2.0,
                    "speaker_id": "speaker_1",
                    "text": "Tôi sẽ gửi bản ghi chú.",
                },
                {
                    "id": "seg-a2",
                    "start": 2.1,
                    "end": 3.0,
                    "speaker_id": "speaker_2",
                    "text": "Lan sẽ sửa giao diện.",
                },
            ],
            participants=[
                {"id": "participant-minh", "display_name": "Minh", "speaker_ids": ["speaker_1"]},
                {"id": "participant-lan", "display_name": "Lan", "speaker_ids": ["speaker_2"]},
            ],
        )
    )

    assert result.action_items[0].owner == "Minh"
    assert result.action_review_reasons[0] == ()


def test_unsupported_priority_is_cleared_without_inference():
    result = TemporalReviewProcessor().process(
        make_verified(priority="High", status_overrides={"actions[0].priority": "unsupported"})
    )

    assert result.action_items[0].priority is None
    assert result.action_review_reasons[0] == ("evidence_unverified",)


def test_unsupported_task_and_unsupported_summary_overview_fail_closed():
    with pytest.raises(EvidenceVerificationFailure):
        TemporalReviewProcessor().process(
            make_verified(status_overrides={"actions[0].task": "unsupported"})
        )
    with pytest.raises(EvidenceVerificationFailure):
        TemporalReviewProcessor().process(
            make_verified(status_overrides={"summary.overview": "unsupported"})
        )


def test_uncertain_assertive_summary_overview_fails_closed():
    with pytest.raises(EvidenceVerificationFailure) as error:
        TemporalReviewProcessor().process(
            make_verified(
                summary_overview="Nhóm đã hoàn thành triển khai.",
                status_overrides={"summary.overview": "uncertain"},
            )
        )

    assert error.value.code == "UNVERIFIED_EVIDENCE"


def test_uncertain_key_topic_is_discarded_without_rewriting_its_assertive_text():
    result = TemporalReviewProcessor().process(
        make_verified(
            summary_topics=[
                {
                    "topic": "Hoàn thành triển khai",
                    "brief_discussion": "Nhóm đã hoàn thành triển khai.",
                    "source_segment_ids": ["seg-a2"],
                }
            ],
            status_overrides={"summary.key_topics[0]": "uncertain"},
        )
    )

    assert result.meeting_summary.key_topics == []
    assert result.topic_review_reasons == ()


def test_verified_empty_actions_is_distinguished_from_failed_items():
    result = TemporalReviewProcessor().process(
        make_verified(actions=[], status_overrides={"actions.absence": "supported"})
    )

    assert result.action_items == ()

    with pytest.raises(EvidenceVerificationFailure):
        TemporalReviewProcessor().process(
            make_verified(actions=[], status_overrides={"actions.absence": "unsupported"})
        )
