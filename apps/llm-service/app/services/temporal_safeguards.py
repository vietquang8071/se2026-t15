"""Apply conservative date, owner, priority, and review safeguards."""

from __future__ import annotations

from datetime import date

from app.schemas.temporal import TemporalResolution
from app.services.validation_models import (
    EvidenceVerificationFailure,
    EvidenceVerifiedExtraction,
    TemporalSafeguardFailure,
    ValidatedExtraction,
    VerificationStatus,
)

_REVIEW_REASON_ORDER = (
    "owner_unconfirmed",
    "date_range_needs_confirmation",
    "temporal_unresolved",
    "evidence_unverified",
    "conflicting_statements",
    "speaker_unmapped",
    "claim_uncertain",
)


def _ordered_reasons(reasons: set[str]) -> tuple[str, ...]:
    return tuple(reason for reason in _REVIEW_REASON_ORDER if reason in reasons)


class TemporalReviewProcessor:
    """Return only claims that remain truthful after deterministic safeguards."""

    def process(self, extraction: EvidenceVerifiedExtraction) -> ValidatedExtraction:
        source = extraction.source_validated
        statuses = {item.claim_id: item.status for item in extraction.verdicts}
        summary = source.summary_candidate
        summary_review_reasons: tuple[str, ...] = ()
        topic_review_reasons: tuple[tuple[str, ...], ...] = ()

        if summary is not None:
            overview_status = statuses["summary.overview"]
            if overview_status == VerificationStatus.UNSUPPORTED:
                raise EvidenceVerificationFailure(
                    "UNVERIFIED_EVIDENCE", "The requested Summary overview is unsupported."
                )
            if overview_status == VerificationStatus.UNCERTAIN:
                raise EvidenceVerificationFailure(
                    "UNVERIFIED_EVIDENCE",
                    "The requested Summary overview is not verified for safe publication.",
                )

            retained_topics = []
            topic_reasons = []
            if len(summary.key_topics) != len(source.summary_topic_claim_ids):
                raise TemporalSafeguardFailure(
                    "INTERNAL_ERROR", "Summary topic claim metadata is inconsistent."
                )
            for topic, claim_id in zip(
                summary.key_topics, source.summary_topic_claim_ids, strict=True
            ):
                status = statuses[claim_id]
                if status != VerificationStatus.SUPPORTED:
                    continue
                retained_topics.append(topic)
                topic_reasons.append(())
            summary = summary.model_copy(update={"key_topics": retained_topics})
            topic_review_reasons = tuple(topic_reasons)

        actions = source.action_candidates
        if actions is None:
            return ValidatedExtraction(
                evidence_verified=extraction,
                meeting_summary=summary,
                summary_review_reasons=summary_review_reasons,
                topic_review_reasons=topic_review_reasons,
                action_items=None,
                action_due_dates=(),
                action_due_resolutions=(),
                action_review_reasons=(),
            )

        if len(actions) != len(source.action_claim_indexes):
            raise TemporalSafeguardFailure(
                "INTERNAL_ERROR", "Action claim metadata is inconsistent."
            )

        if not actions:
            if statuses.get("actions.absence") != VerificationStatus.SUPPORTED:
                raise EvidenceVerificationFailure(
                    "UNVERIFIED_EVIDENCE",
                    "The absence of qualifying Action Items was not verified.",
                )
            return ValidatedExtraction(
                evidence_verified=extraction,
                meeting_summary=summary,
                summary_review_reasons=summary_review_reasons,
                topic_review_reasons=topic_review_reasons,
                action_items=(),
                action_due_dates=(),
                action_due_resolutions=(),
                action_review_reasons=(),
            )

        request = source.projected.prepared_extraction.request
        source_by_id = {segment.id: segment for segment in request.transcript.segments}
        speaker_to_owner = {
            speaker_id: participant.display_name
            for participant in request.meeting.participants
            for speaker_id in participant.speaker_ids
        }
        retained_actions = []
        due_dates: list[str | None] = []
        due_resolutions: list[TemporalResolution | None] = []
        review_reasons: list[tuple[str, ...]] = []

        for action, original_index in zip(actions, source.action_claim_indexes, strict=True):
            task_status = statuses[f"actions[{original_index}].task"]
            if task_status != VerificationStatus.SUPPORTED:
                continue

            reasons: set[str] = set()
            owner = action.owner
            owner_claim_id = f"actions[{original_index}].owner"
            if owner is None:
                reasons.add("owner_unconfirmed")
            elif statuses[owner_claim_id] != VerificationStatus.SUPPORTED:
                owner = None
                reasons.add("owner_unconfirmed")
                if statuses[owner_claim_id] == VerificationStatus.UNCERTAIN:
                    reasons.add("claim_uncertain")

            if owner is None:
                cited_speakers = [
                    source_by_id[source_id].speaker_id
                    for source_id in action.source_segment_ids
                ]
                if not any(speaker_id in speaker_to_owner for speaker_id in cited_speakers):
                    reasons.add("speaker_unmapped")

            priority = action.priority
            priority_claim_id = f"actions[{original_index}].priority"
            if priority is not None and statuses[priority_claim_id] != VerificationStatus.SUPPORTED:
                priority = None
                reasons.add(
                    "claim_uncertain"
                    if statuses[priority_claim_id] == VerificationStatus.UNCERTAIN
                    else "evidence_unverified"
                )

            context = action.context
            context_claim_id = f"actions[{original_index}].context"
            if context is not None and statuses[context_claim_id] != VerificationStatus.SUPPORTED:
                context = None
                reasons.add(
                    "claim_uncertain"
                    if statuses[context_claim_id] == VerificationStatus.UNCERTAIN
                    else "evidence_unverified"
                )

            raw_due = action.raw_due_expression
            due_date: str | None = None
            due_resolution: TemporalResolution | None = None
            due_claim_id = f"actions[{original_index}].raw_due_expression"
            if raw_due is not None:
                due_status = statuses[due_claim_id]
                if due_status == VerificationStatus.UNSUPPORTED:
                    raw_due = None
                    reasons.add("evidence_unverified")
                else:
                    if due_status == VerificationStatus.UNCERTAIN:
                        reasons.add("claim_uncertain")
                    exact_date: date | None = None
                    try:
                        parsed_date = date.fromisoformat(raw_due)
                        if parsed_date.isoformat() == raw_due:
                            exact_date = parsed_date
                    except ValueError:
                        pass
                    source_ids = tuple(
                        claim.source_segment_ids
                        for claim in source.claims
                        if claim.claim_id == due_claim_id
                    )
                    temporal_sources = source_ids[0] if source_ids else action.source_segment_ids
                    if (
                        exact_date is not None
                        and due_status == VerificationStatus.SUPPORTED
                    ):
                        due_date = exact_date.isoformat()
                        due_resolution = TemporalResolution(
                            status="exact_date",
                            resolved_date=due_date,
                            start_date=None,
                            end_date=None,
                            needs_review=False,
                            source_segment_ids=list(temporal_sources),
                        )
                    else:
                        reasons.add("temporal_unresolved")
                        due_resolution = TemporalResolution(
                            status="unresolved",
                            resolved_date=None,
                            start_date=None,
                            end_date=None,
                            needs_review=True,
                            source_segment_ids=list(temporal_sources),
                        )

            retained_actions.append(
                action.model_copy(
                    update={
                        "owner": owner,
                        "raw_due_expression": raw_due,
                        "priority": priority,
                        "context": context,
                    }
                )
            )
            due_dates.append(due_date)
            due_resolutions.append(due_resolution)
            review_reasons.append(_ordered_reasons(reasons))

        if not retained_actions:
            raise EvidenceVerificationFailure(
                "UNVERIFIED_EVIDENCE",
                "No requested Action Item passed mandatory evidence verification.",
            )

        return ValidatedExtraction(
            evidence_verified=extraction,
            meeting_summary=summary,
            summary_review_reasons=summary_review_reasons,
            topic_review_reasons=topic_review_reasons,
            action_items=tuple(retained_actions),
            action_due_dates=tuple(due_dates),
            action_due_resolutions=tuple(due_resolutions),
            action_review_reasons=tuple(review_reasons),
        )
