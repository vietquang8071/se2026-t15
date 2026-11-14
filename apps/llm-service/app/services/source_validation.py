"""Deterministically validate candidate source references per request."""

from __future__ import annotations

from app.schemas.candidates import ActionItemCandidate, MeetingSummaryCandidate
from app.services.projection import ProjectedExtraction
from app.services.validation_models import (
    ClaimIdentity,
    SourceSegmentReference,
    SourceValidatedExtraction,
    SourceValidationFailure,
)


class SourceValidator:
    """Index the current transcript and reject or safely discard bad claims."""

    def validate(self, projected: ProjectedExtraction) -> SourceValidatedExtraction:
        request = projected.prepared_extraction.request
        source_segments = tuple(
            SourceSegmentReference(segment.id, segment.start, index)
            for index, segment in enumerate(request.transcript.segments)
        )
        source_by_id = {segment.segment_id: segment for segment in source_segments}
        claims: list[ClaimIdentity] = []

        def validated_ids(source_ids: list[str], *, label: str) -> tuple[str, ...]:
            if len(source_ids) != len(set(source_ids)):
                raise SourceValidationFailure(
                    "UNVERIFIED_EVIDENCE", f"{label} contains duplicate source IDs."
                )
            unknown = [source_id for source_id in source_ids if source_id not in source_by_id]
            if unknown:
                raise SourceValidationFailure(
                    "UNVERIFIED_EVIDENCE", f"{label} references an unknown source ID."
                )
            return tuple(
                sorted(
                    source_ids,
                    key=lambda source_id: (
                        source_by_id[source_id].start,
                        source_by_id[source_id].transcript_order,
                    ),
                )
            )

        def claim(claim_id: str, content: str, source_ids: tuple[str, ...]) -> ClaimIdentity:
            return ClaimIdentity(
                request_id=request.request_id,
                transcript_revision_id=request.transcript.revision_id,
                claim_id=claim_id,
                content=content,
                source_segment_ids=source_ids,
            )

        summary_candidate: MeetingSummaryCandidate | None = None
        summary_topic_claim_ids: list[str] = []
        if projected.meeting_summary is not None:
            candidate = projected.meeting_summary.candidate
            summary_sources = validated_ids(
                candidate.source_segment_ids, label="Summary overview"
            )
            claims.append(claim("summary.overview", candidate.overview, summary_sources))
            topics = []
            for index, topic in enumerate(candidate.key_topics):
                try:
                    topic_sources = validated_ids(
                        topic.source_segment_ids, label=f"Summary key topic {index}"
                    )
                except SourceValidationFailure:
                    # A bad non-central topic can be excluded while the verified
                    # overview remains usable. Its source IDs are never repaired.
                    continue
                topics.append(topic.model_copy(update={"source_segment_ids": list(topic_sources)}))
                summary_topic_claim_ids.append(f"summary.key_topics[{index}]")
                claims.append(
                    claim(
                        f"summary.key_topics[{index}]",
                        f"Topic: {topic.topic}\nDiscussion: {topic.brief_discussion}",
                        topic_sources,
                    )
                )
            summary_candidate = candidate.model_copy(
                update={
                    "source_segment_ids": list(summary_sources),
                    "key_topics": topics,
                }
            )

        action_candidates: tuple[ActionItemCandidate, ...] | None = None
        action_claim_indexes: list[int] = []
        if projected.action_items is not None:
            retained_actions: list[ActionItemCandidate] = []
            original_actions = projected.action_items
            for index, action in enumerate(original_actions):
                try:
                    action_sources = validated_ids(
                        action.source_segment_ids, label=f"Action Item {index}"
                    )
                except SourceValidationFailure:
                    # Invalid actions cannot be published; keep other independently
                    # valid candidates when at least one remains.
                    continue
                retained = action.model_copy(
                    update={"source_segment_ids": list(action_sources)}
                )
                retained_actions.append(retained)
                action_claim_indexes.append(index)
                claims.append(claim(f"actions[{index}].task", action.task, action_sources))
                for field_name in (
                    "owner",
                    "raw_due_expression",
                    "priority",
                    "context",
                ):
                    value = getattr(action, field_name)
                    if value is not None:
                        claims.append(
                            claim(
                                f"actions[{index}].{field_name}",
                                str(value),
                                action_sources,
                            )
                        )

            if original_actions and not retained_actions:
                raise SourceValidationFailure(
                    "UNVERIFIED_EVIDENCE",
                    "No requested Action Item has a valid source reference.",
                )
            if not original_actions:
                claims.append(
                    claim(
                        "actions.absence",
                        "No qualifying Action Items were extracted. Verify that the transcript contains no clear commitment that was omitted.",
                        (),
                    )
                )
            action_candidates = tuple(retained_actions)

        return SourceValidatedExtraction(
            projected=projected,
            claims=tuple(claims),
            source_segments=source_segments,
            summary_candidate=summary_candidate,
            action_candidates=action_candidates,
            summary_topic_claim_ids=tuple(summary_topic_claim_ids),
            action_claim_indexes=tuple(action_claim_indexes),
        )
