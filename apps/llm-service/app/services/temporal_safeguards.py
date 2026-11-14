"""Apply conservative date, owner, priority, and review safeguards."""

from __future__ import annotations

from datetime import date
import re

from app.schemas.candidates import ActionItemCandidate
from app.schemas.request import TranscriptSegment
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

_FIRST_PERSON_COMMITMENT = re.compile(
    r"(?<!\w)(?:tôi|i)\s+"
    r"(?:sẽ|nhận|cam kết|phụ trách|will|shall|commit(?:\s+to)?|"
    r"take responsibility for)\b",
    re.IGNORECASE,
)
_HYPOTHETICAL_PREFIX = re.compile(
    r"\b(?:nếu|giả sử|trong trường hợp|if|suppose)\b", re.IGNORECASE
)
_NEGATION_AFTER_COMMITMENT = re.compile(
    r"^\s*(?:không|chưa|not|never|won't|will not)\b", re.IGNORECASE
)
_QUOTE_PAIRS = (("“", "”"), ("‘", "’"), ("«", "»"), ("「", "」"), ("『", "』"))
def _ordered_reasons(reasons: set[str]) -> tuple[str, ...]:
    return tuple(reason for reason in _REVIEW_REASON_ORDER if reason in reasons)


def _inside_quote(text: str, position: int) -> bool:
    for opening, closing in _QUOTE_PAIRS:
        start = text.rfind(opening, 0, position)
        end = text.find(closing, position)
        if start >= 0 and end > position:
            return True
    preceding_quotes = text[:position].count('"')
    return preceding_quotes % 2 == 1 and text.find('"', position) >= 0


def _first_person_state(clause: str, match: re.Match[str]) -> str:
    """Classify only a narrow, explicit first-person commitment construction."""

    if (
        _inside_quote(clause, match.start())
        or _HYPOTHETICAL_PREFIX.search(clause[: match.start()])
        or _NEGATION_AFTER_COMMITMENT.search(clause[match.end() : match.end() + 32])
        or "?" in clause
    ):
        return "ambiguous"
    return "direct"


def _contains_exact_text(phrase: str, text: str) -> bool:
    words = phrase.strip().split()
    if not words:
        return False
    pattern = r"(?<!\w)" + r"\s+".join(re.escape(word) for word in words) + r"(?!\w)"
    return re.search(pattern, text, re.IGNORECASE) is not None


def _speaker_owner_matches(
    action: ActionItemCandidate,
    source_by_id: dict[str, TranscriptSegment],
    speaker_to_owner: dict[str, str],
) -> tuple[bool, bool]:
    """Check only exact-task first-person speaker contradictions.

    Returns ``(confirmed, has_unmapped_speaker)``. This deliberately recognizes
    only a direct first-person construction whose exact task text occurs in the
    same simple clause. Task attribution and named assignments otherwise remain
    the semantic verifier's responsibility.
    """

    owner = action.owner
    if owner is None:
        return False, False

    direct_speakers: list[str | None] = []
    for source_id in action.source_segment_ids:
        segment = source_by_id[source_id]
        text = segment.text
        clauses = re.split(
            r",|;|\b(?:và|and)\b|(?<=[.!?])\s+|\n", text, flags=re.IGNORECASE
        )
        for clause in clauses:
            normalized_clause = " ".join(clause.casefold().split())
            if not _contains_exact_text(action.task, normalized_clause):
                continue
            if _contains_exact_text(owner, normalized_clause):
                continue
            for match in _FIRST_PERSON_COMMITMENT.finditer(clause):
                if _first_person_state(clause, match) != "direct":
                    continue
                direct_speakers.append(
                    speaker_to_owner.get(segment.speaker_id)
                    if segment.speaker_id is not None
                    else None
                )

    normalized_owner = " ".join(owner.casefold().split())
    normalized_speakers = {
        " ".join(name.casefold().split()) for name in direct_speakers if name is not None
    }
    has_unmapped = any(name is None for name in direct_speakers)
    if direct_speakers and (
        has_unmapped or normalized_speakers != {normalized_owner}
    ):
        return False, has_unmapped
    if direct_speakers:
        return True, False
    return True, False


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
            else:
                owner_confirmed, has_unmapped_speaker = _speaker_owner_matches(
                    action, source_by_id, speaker_to_owner
                )
                if not owner_confirmed:
                    owner = None
                    reasons.add("owner_unconfirmed")
                    if has_unmapped_speaker:
                        reasons.add("speaker_unmapped")

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
