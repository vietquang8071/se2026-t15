"""Tests for request-scoped, fail-closed validation stage contracts."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.providers.models import ProviderUsage
from app.schemas.candidates import SummaryActionsCandidate
from app.schemas.request import ExtractionRequest
from app.services.models import PreparedExtraction
from app.services.projection import ExtractionProjector
from app.services.source_validation import SourceValidator
from app.services.validation_models import (
    EvidenceVerifiedExtraction,
    VerificationMetadata,
    VerificationStatus,
    VerificationVerdict,
)


REQUEST_FIXTURE = Path(__file__).parents[2] / "fixtures/requests/summary_actions_request.json"


def source_validated():
    payload = json.loads(REQUEST_FIXTURE.read_text(encoding="utf-8"))
    request = ExtractionRequest.model_validate(payload)
    candidate = SummaryActionsCandidate.model_validate(
        {
            "meeting_summary": {
                "overview": "Summary canary",
                "key_topics": [],
                "source_segment_ids": [request.transcript.segments[0].id],
            },
            "action_items": [],
        }
    )
    prepared = PreparedExtraction(
        request=request,
        candidate=candidate,
        prompt_version="extract-v1.0",
        candidate_schema_version="candidate-v1",
        model_id="fake-model",
        provider="fake-provider",
    )
    projected = ExtractionProjector().project(prepared)
    return SourceValidator().validate(projected)


def make_metadata() -> VerificationMetadata:
    return VerificationMetadata(
        provider="fake-provider",
        model_id="fake-model",
        prompt_version="evidence-v1.0",
        token_usage=ProviderUsage(input_tokens=10, output_tokens=4),
        started_at=None,
        completed_at=None,
    )


def test_complete_verdict_set_is_bound_to_source_validated_request() -> None:
    source = source_validated()
    verdicts = tuple(
        VerificationVerdict(
            request_id=claim.request_id,
            transcript_revision_id=claim.transcript_revision_id,
            claim_id=claim.claim_id,
            status=VerificationStatus.SUPPORTED,
        )
        for claim in source.claims
    )

    verified = EvidenceVerifiedExtraction(
        source_validated=source,
        verdicts=verdicts,
        metadata=make_metadata(),
    )

    assert verified.source_validated is source
    assert [item.status for item in verified.verdicts] == [
        VerificationStatus.SUPPORTED,
        VerificationStatus.SUPPORTED,
    ]


def test_unknown_verdict_status_is_rejected() -> None:
    with pytest.raises(ValueError):
        VerificationVerdict(
            request_id="req-a",
            transcript_revision_id="rev-a",
            claim_id="summary.overview",
            status="approved",  # type: ignore[arg-type]
        )


def test_duplicate_claim_id_is_rejected() -> None:
    source = source_validated()
    duplicate = source.claims[0]
    with pytest.raises(ValueError, match="duplicate"):
        from app.services.validation_models import SourceValidatedExtraction

        SourceValidatedExtraction(
            projected=source.projected,
            claims=(duplicate, duplicate),
            source_segments=source.source_segments,
        )


def test_source_claim_cannot_reference_a_segment_outside_its_request():
    source = source_validated()
    invalid_claim = replace(source.claims[0], source_segment_ids=("foreign-segment",))

    with pytest.raises(ValueError, match="sources"):
        replace(source, claims=(invalid_claim, *source.claims[1:]))


def test_source_index_must_match_the_current_transcript_revision():
    source = source_validated()

    with pytest.raises(ValueError, match="current transcript revision"):
        replace(source, source_segments=source.source_segments[:-1])


def test_source_claim_revision_must_match_the_projected_request():
    source = source_validated()
    invalid_claim = replace(source.claims[0], transcript_revision_id="other-revision")

    with pytest.raises(ValueError, match="does not belong"):
        replace(source, claims=(invalid_claim, *source.claims[1:]))


def test_missing_verdict_is_rejected() -> None:
    source = source_validated()
    claim = source.claims[0]
    with pytest.raises(ValueError, match="complete"):
        EvidenceVerifiedExtraction(
            source_validated=source,
            verdicts=(
                VerificationVerdict(
                    request_id=claim.request_id,
                    transcript_revision_id=claim.transcript_revision_id,
                    claim_id=claim.claim_id,
                    status=VerificationStatus.SUPPORTED,
                ),
            ),
            metadata=make_metadata(),
        )


def test_unrecognized_extra_verdict_is_rejected() -> None:
    source = source_validated()
    verdicts = tuple(
        VerificationVerdict(
            request_id=claim.request_id,
            transcript_revision_id=claim.transcript_revision_id,
            claim_id=claim.claim_id,
            status=VerificationStatus.SUPPORTED,
        )
        for claim in source.claims
    )
    with pytest.raises(ValueError, match="unknown"):
        EvidenceVerifiedExtraction(
            source_validated=source,
            verdicts=verdicts
            + (
                VerificationVerdict(
                    request_id=source.request_id,
                    transcript_revision_id=source.transcript_revision_id,
                    claim_id="summary.injected",
                    status=VerificationStatus.SUPPORTED,
                ),
            ),
            metadata=make_metadata(),
        )


def test_verdict_from_another_request_is_rejected() -> None:
    source = source_validated()
    claim = source.claims[0]
    verdicts = [
        VerificationVerdict(
            request_id=claim.request_id,
            transcript_revision_id=claim.transcript_revision_id,
            claim_id=claim.claim_id,
            status=VerificationStatus.SUPPORTED,
        ),
        VerificationVerdict(
            request_id="other-request",
            transcript_revision_id=source.transcript_revision_id,
            claim_id=source.claims[1].claim_id,
            status=VerificationStatus.SUPPORTED,
        ),
    ]
    with pytest.raises(ValueError, match="request"):
        EvidenceVerifiedExtraction(
            source_validated=source,
            verdicts=tuple(verdicts),
            metadata=make_metadata(),
        )


def test_validation_failures_and_intermediate_repr_do_not_expose_transcript() -> None:
    source = source_validated()

    assert source.projected.prepared_extraction.request.transcript.segments[0].text not in repr(source)
    assert "Summary canary" not in repr(source)
