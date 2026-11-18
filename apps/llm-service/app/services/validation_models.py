"""Typed, request-scoped contracts for verified extraction stages.

All objects hide transcript and candidate content from their representations.
The public response builder is wired to accept only ``ValidatedExtraction``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

from app.providers.models import ProviderUsage
from app.schemas.candidates import ActionItemCandidate, MeetingSummaryCandidate
from app.schemas.temporal import TemporalResolution
from app.services.projection import ProjectedExtraction


class VerificationStatus(str, Enum):
    SUPPORTED = "supported"
    UNCERTAIN = "uncertain"
    UNSUPPORTED = "unsupported"


REVIEW_REASON_ORDER = (
    "owner_unconfirmed",
    "date_range_needs_confirmation",
    "temporal_unresolved",
    "evidence_unverified",
    "conflicting_statements",
    "speaker_unmapped",
    "claim_uncertain",
)


def _validate_review_reasons(reasons: tuple[str, ...]) -> None:
    if len(reasons) != len(set(reasons)) or any(
        reason not in REVIEW_REASON_ORDER for reason in reasons
    ):
        raise ValueError("Review reasons are invalid or duplicated.")
    expected = tuple(reason for reason in REVIEW_REASON_ORDER if reason in reasons)
    if reasons != expected:
        raise ValueError("Review reasons are not in deterministic order.")


@dataclass(frozen=True, slots=True)
class ClaimIdentity:
    """One deterministic candidate claim and its request-bound evidence."""

    request_id: str
    transcript_revision_id: str
    claim_id: str
    content: str = field(repr=False)
    source_segment_ids: tuple[str, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class SourceSegmentReference:
    """Source index entry scoped to one transcript revision."""

    segment_id: str
    start: float
    transcript_order: int


@dataclass(frozen=True, slots=True)
class SourceValidatedExtraction:
    """Projection whose every cited source belongs to its originating request."""

    projected: ProjectedExtraction = field(repr=False)
    claims: tuple[ClaimIdentity, ...] = field(repr=False)
    source_segments: tuple[SourceSegmentReference, ...] = field(repr=False)
    summary_candidate: MeetingSummaryCandidate | None = field(default=None, repr=False)
    action_candidates: tuple[ActionItemCandidate, ...] | None = field(default=None, repr=False)
    summary_topic_claim_ids: tuple[str, ...] = ()
    action_claim_indexes: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        self.validate_invariants()

    def validate_invariants(self) -> None:
        request = self.projected.prepared_extraction.request
        if any(
            claim.request_id != request.request_id
            or claim.transcript_revision_id != request.transcript.revision_id
            for claim in self.claims
        ):
            raise ValueError("Claim identity does not belong to the projected request.")
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("Source-validated extraction contains duplicate claim IDs.")

        requested = set(request.extraction.requested_modules)
        unsupported = requested - {"meeting_summary", "action_items"}
        if unsupported:
            raise ValueError("Source-validated extraction contains an unsupported module.")
        wants_summary = "meeting_summary" in requested
        wants_actions = "action_items" in requested
        if (self.projected.meeting_summary is not None) != wants_summary:
            raise ValueError("Projected Summary state does not match the request.")
        if (self.projected.action_items is not None) != wants_actions:
            raise ValueError("Projected Action Items state does not match the request.")
        if (self.summary_candidate is not None) != wants_summary:
            raise ValueError("Source-validated Summary state does not match the request.")
        if (self.action_candidates is not None) != wants_actions:
            raise ValueError("Source-validated Action Items state does not match the request.")

        source_ids = [item.segment_id for item in self.source_segments]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Source index contains duplicate segment IDs.")
        expected_sources = tuple(
            SourceSegmentReference(segment.id, segment.start, index)
            for index, segment in enumerate(request.transcript.segments)
        )
        if self.source_segments != expected_sources:
            raise ValueError("Source index does not match the current transcript revision.")

        source_by_id = {item.segment_id: item for item in self.source_segments}
        claims_by_id = {claim.claim_id: claim for claim in self.claims}
        expected_claims: list[tuple[str, str, tuple[str, ...]]] = []

        def append_claim(claim_id: str, content: str, cited_ids: tuple[str, ...]) -> None:
            if claim_id not in claims_by_id:
                raise ValueError("Source-validated extraction is missing a candidate claim.")
            claim = claims_by_id[claim_id]
            if claim.content != content or claim.source_segment_ids != cited_ids:
                raise ValueError("Claim content or sources do not match the projected candidate.")
            if claim_id != "actions.absence" and not cited_ids:
                raise ValueError("A non-absence claim requires source references.")
            if any(source_id not in source_by_id for source_id in cited_ids):
                raise ValueError("A claim source is outside the current transcript revision.")
            normalized = tuple(
                sorted(
                    cited_ids,
                    key=lambda source_id: (
                        source_by_id[source_id].start,
                        source_by_id[source_id].transcript_order,
                    ),
                )
            )
            if normalized != cited_ids:
                raise ValueError("Claim sources are not in deterministic transcript order.")
            expected_claims.append((claim_id, content, cited_ids))

        if wants_summary:
            projected_summary = self.projected.meeting_summary
            raw_summary = projected_summary.candidate
            if (
                projected_summary.title != request.meeting.title
                or projected_summary.date != request.meeting.anchor_date
                or projected_summary.duration_minutes
                != round(request.meeting.duration_seconds / 60, 2)
                or projected_summary.participants
                != tuple(participant.display_name for participant in request.meeting.participants)
            ):
                raise ValueError("Projected Summary metadata does not match the request.")
            summary = self.summary_candidate
            if summary.overview != raw_summary.overview or set(summary.source_segment_ids) != set(
                raw_summary.source_segment_ids
            ):
                raise ValueError("Source-validated Summary does not match its candidate.")
            append_claim("summary.overview", summary.overview, tuple(summary.source_segment_ids))
            if len(summary.key_topics) != len(self.summary_topic_claim_ids):
                raise ValueError("Summary topic claim metadata is inconsistent.")
            topic_indexes: list[int] = []
            for topic, claim_id in zip(
                summary.key_topics, self.summary_topic_claim_ids, strict=True
            ):
                prefix = "summary.key_topics["
                if not claim_id.startswith(prefix) or not claim_id.endswith("]"):
                    raise ValueError("Summary topic claim identity is invalid.")
                try:
                    topic_index = int(claim_id[len(prefix) : -1])
                except ValueError:
                    raise ValueError("Summary topic claim identity is invalid.") from None
                if not 0 <= topic_index < len(raw_summary.key_topics):
                    raise ValueError("Summary topic claim identity is outside the candidate.")
                raw_topic = raw_summary.key_topics[topic_index]
                if (
                    topic.topic != raw_topic.topic
                    or topic.brief_discussion != raw_topic.brief_discussion
                    or set(topic.source_segment_ids) != set(raw_topic.source_segment_ids)
                ):
                    raise ValueError("Source-validated topic does not match its candidate.")
                topic_indexes.append(topic_index)
                append_claim(
                    claim_id,
                    f"Topic: {topic.topic}\nDiscussion: {topic.brief_discussion}",
                    tuple(topic.source_segment_ids),
                )
            if topic_indexes != sorted(set(topic_indexes)):
                raise ValueError("Summary topic claim identities are not in candidate order.")
        elif self.summary_topic_claim_ids:
            raise ValueError("Unrequested Summary has topic claim metadata.")

        if wants_actions:
            raw_actions = self.projected.action_items
            actions = self.action_candidates
            if len(actions) != len(self.action_claim_indexes):
                raise ValueError("Action claim metadata does not match candidate count.")
            if self.action_claim_indexes != tuple(sorted(set(self.action_claim_indexes))):
                raise ValueError("Action claim indexes are not unique and ordered.")
            if any(index < 0 or index >= len(raw_actions) for index in self.action_claim_indexes):
                raise ValueError("Action claim index is outside the projected candidate.")
            if not actions:
                if raw_actions:
                    raise ValueError("Source validation discarded all Action Items unexpectedly.")
                append_claim(
                    "actions.absence",
                    "No qualifying Action Items were extracted. Verify that the transcript contains no clear commitment that was omitted.",
                    (),
                )
            else:
                for action, action_index in zip(actions, self.action_claim_indexes, strict=True):
                    raw_action = raw_actions[action_index]
                    if action.model_dump(exclude={"source_segment_ids"}) != raw_action.model_dump(
                        exclude={"source_segment_ids"}
                    ) or set(action.source_segment_ids) != set(raw_action.source_segment_ids):
                        raise ValueError("Source-validated Action Item does not match its candidate.")
                    prefix = f"actions[{action_index}]"
                    cited_ids = tuple(action.source_segment_ids)
                    append_claim(f"{prefix}.task", action.task, cited_ids)
                    for field_name in ("owner", "raw_due_expression", "priority", "context"):
                        value = getattr(action, field_name)
                        if value is not None:
                            append_claim(f"{prefix}.{field_name}", str(value), cited_ids)
        elif self.action_claim_indexes:
            raise ValueError("Unrequested Action Items have claim-index metadata.")

        if tuple(claim.claim_id for claim in self.claims) != tuple(
            claim_id for claim_id, _, _ in expected_claims
        ):
            raise ValueError("Source-validated claims are incomplete or out of order.")

    @property
    def request_id(self) -> str:
        return self.projected.prepared_extraction.request.request_id

    @property
    def transcript_revision_id(self) -> str:
        return self.projected.prepared_extraction.request.transcript.revision_id


@dataclass(frozen=True, slots=True)
class VerificationVerdict:
    """A strict verdict tied to a single request and claim identity."""

    request_id: str
    transcript_revision_id: str
    claim_id: str
    status: VerificationStatus

    def __post_init__(self) -> None:
        if not isinstance(self.status, VerificationStatus):
            raise ValueError("Verification status is not recognized.")


@dataclass(frozen=True, slots=True)
class VerificationMetadata:
    """Provider and executed prompt metadata for one verification generation."""

    provider: str
    model_id: str
    prompt_version: str
    token_usage: ProviderUsage | None
    started_at: datetime | None
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class EvidenceVerifiedExtraction:
    """Source-validated extraction with a complete, isolated verdict set."""

    source_validated: SourceValidatedExtraction = field(repr=False)
    verdicts: tuple[VerificationVerdict, ...] = field(repr=False)
    metadata: VerificationMetadata

    def __post_init__(self) -> None:
        self.validate_invariants()

    def validate_invariants(self) -> None:
        self.source_validated.validate_invariants()
        expected = {claim.claim_id for claim in self.source_validated.claims}
        actual: set[str] = set()
        for verdict in self.verdicts:
            if (
                verdict.request_id != self.source_validated.request_id
                or verdict.transcript_revision_id
                != self.source_validated.transcript_revision_id
            ):
                raise ValueError("Verdict request identity does not match source claims.")
            if verdict.claim_id in actual:
                raise ValueError("Verifier returned duplicate claim IDs.")
            actual.add(verdict.claim_id)
        if actual - expected:
            raise ValueError("Verifier returned unknown claim IDs.")
        if expected - actual:
            raise ValueError("Verifier did not return a complete verdict set.")


@dataclass(frozen=True, slots=True)
class ValidatedExtraction:
    """Evidence-verified content after deterministic temporal/review safeguards."""

    evidence_verified: EvidenceVerifiedExtraction = field(repr=False)
    meeting_summary: MeetingSummaryCandidate | None = field(repr=False)
    summary_review_reasons: tuple[str, ...]
    topic_review_reasons: tuple[tuple[str, ...], ...]
    action_items: tuple[ActionItemCandidate, ...] | None = field(repr=False)
    action_due_dates: tuple[str | None, ...] = field(repr=False)
    action_due_resolutions: tuple[TemporalResolution | None, ...] = field(repr=False)
    action_review_reasons: tuple[tuple[str, ...], ...] = field(repr=False)

    def __post_init__(self) -> None:
        self.validate_invariants()

    def validate_invariants(self) -> None:
        self.evidence_verified.validate_invariants()
        source = self.evidence_verified.source_validated
        request = source.projected.prepared_extraction.request
        wants_summary = "meeting_summary" in request.extraction.requested_modules
        wants_actions = "action_items" in request.extraction.requested_modules
        if wants_summary != (self.meeting_summary is not None):
            raise ValueError("Safeguarded Summary state does not match the request.")
        if wants_actions != (self.action_items is not None):
            raise ValueError("Safeguarded Action Items state does not match the request.")

        if self.action_items is None:
            if self.action_due_dates or self.action_due_resolutions or self.action_review_reasons:
                raise ValueError("Safeguard metadata requires requested Action Items.")
        elif not (
            len(self.action_items)
            == len(self.action_due_dates)
            == len(self.action_due_resolutions)
            == len(self.action_review_reasons)
        ):
            raise ValueError("Action safeguard metadata does not match item count.")
        if self.meeting_summary is None and self.topic_review_reasons:
            raise ValueError("Topic review metadata requires a requested Summary.")
        if self.meeting_summary is None and self.summary_review_reasons:
            raise ValueError("Summary review metadata requires a requested Summary.")
        if self.meeting_summary is not None and len(self.topic_review_reasons) != len(
            self.meeting_summary.key_topics
        ):
            raise ValueError("Topic review metadata does not match topic count.")

        statuses = {item.claim_id: item.status for item in self.evidence_verified.verdicts}
        if self.meeting_summary is not None:
            candidate_summary = source.summary_candidate
            if (
                candidate_summary is None
                or statuses.get("summary.overview") != VerificationStatus.SUPPORTED
                or self.meeting_summary.overview != candidate_summary.overview
                or self.meeting_summary.source_segment_ids != candidate_summary.source_segment_ids
            ):
                raise ValueError("Safeguarded Summary contains an unverified overview.")
            _validate_review_reasons(self.summary_review_reasons)
            if self.summary_review_reasons:
                raise ValueError("A verified Summary cannot carry unsupported uncertainty review.")
            supported_topics = [
                (topic, claim_id)
                for topic, claim_id in zip(
                    candidate_summary.key_topics,
                    source.summary_topic_claim_ids,
                    strict=True,
                )
                if statuses.get(claim_id) == VerificationStatus.SUPPORTED
            ]
            if len(supported_topics) != len(self.meeting_summary.key_topics):
                raise ValueError("Safeguarded Summary retained an unverified topic.")
            for (expected_topic, _), actual_topic, reasons in zip(
                supported_topics,
                self.meeting_summary.key_topics,
                self.topic_review_reasons,
                strict=True,
            ):
                if expected_topic != actual_topic or reasons:
                    raise ValueError("Safeguarded topic or its review state is inconsistent.")

        _validate_review_reasons(self.summary_review_reasons)
        for reasons in self.topic_review_reasons:
            _validate_review_reasons(reasons)

        if self.action_items is not None:
            candidates = source.action_candidates
            candidate_indexes = source.action_claim_indexes
            if not candidates:
                if (
                    self.action_items != ()
                    or statuses.get("actions.absence") != VerificationStatus.SUPPORTED
                ):
                    raise ValueError("Empty Action Items were not verified as absent.")
            else:
                supported_candidates = [
                    (action, index)
                    for action, index in zip(candidates, candidate_indexes, strict=True)
                    if statuses.get(f"actions[{index}].task") == VerificationStatus.SUPPORTED
                ]
                if len(supported_candidates) != len(self.action_items):
                    raise ValueError("Safeguarded Action Items do not match supported tasks.")
                request_source_ids = {
                    segment.id for segment in request.transcript.segments
                }
                for (candidate, index), action, due_date, resolution, reasons in zip(
                    supported_candidates,
                    self.action_items,
                    self.action_due_dates,
                    self.action_due_resolutions,
                    self.action_review_reasons,
                    strict=True,
                ):
                    if action.task != candidate.task or set(action.source_segment_ids) != set(
                        candidate.source_segment_ids
                    ):
                        raise ValueError("Safeguarded Action Item changed verified task or sources.")
                    for field_name in ("owner", "priority", "context"):
                        value = getattr(action, field_name)
                        candidate_value = getattr(candidate, field_name)
                        if value is not None and (
                            value != candidate_value
                            or statuses.get(f"actions[{index}].{field_name}")
                            != VerificationStatus.SUPPORTED
                        ):
                            raise ValueError("Safeguarded Action Item retained an unverified field.")
                    if action.raw_due_expression is not None and (
                        action.raw_due_expression != candidate.raw_due_expression
                        or statuses.get(f"actions[{index}].raw_due_expression")
                        == VerificationStatus.UNSUPPORTED
                    ):
                        raise ValueError("Safeguarded Action Item retained an unsupported deadline.")
                    if action.raw_due_expression is None:
                        if due_date is not None or resolution is not None:
                            raise ValueError("Deadline resolution requires a raw expression.")
                    elif resolution is None or (
                        resolution.status == "exact_date"
                        and (
                            due_date != resolution.resolved_date.isoformat()
                            or statuses.get(f"actions[{index}].raw_due_expression")
                            != VerificationStatus.SUPPORTED
                        )
                    ) or (resolution.status == "unresolved" and due_date is not None):
                        raise ValueError("Deadline expression and temporal resolution conflict.")
                    if resolution is not None and (
                        not set(resolution.source_segment_ids).issubset(action.source_segment_ids)
                        or not set(resolution.source_segment_ids).issubset(request_source_ids)
                    ):
                        raise ValueError("Temporal sources are outside the Action Item evidence.")
                    if (action.owner is None) != ("owner_unconfirmed" in reasons):
                        raise ValueError("Owner review state does not match the verified owner.")
                    if resolution is not None and (
                        (resolution.status == "unresolved")
                        != ("temporal_unresolved" in reasons)
                    ):
                        raise ValueError("Temporal review state does not match its resolution.")
                    _validate_review_reasons(reasons)

        source_ids = {segment.id for segment in request.transcript.segments}
        if self.meeting_summary is not None:
            summary_ids = list(self.meeting_summary.source_segment_ids)
            if any(source_id not in source_ids for source_id in summary_ids):
                raise ValueError("Safeguarded Summary references another transcript.")
            for topic in self.meeting_summary.key_topics:
                if any(source_id not in source_ids for source_id in topic.source_segment_ids):
                    raise ValueError("Safeguarded topic references another transcript.")
        if self.action_items is not None:
            for action, resolution in zip(
                self.action_items, self.action_due_resolutions, strict=True
            ):
                if any(source_id not in source_ids for source_id in action.source_segment_ids):
                    raise ValueError("Safeguarded Action Item references another transcript.")
                if resolution is not None and any(
                    source_id not in source_ids for source_id in resolution.source_segment_ids
                ):
                    raise ValueError("Temporal resolution references another transcript.")


class ValidationStageFailure(Exception):
    """Sanitized failure raised when a mandatory validation stage cannot pass."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code!r})"


class SourceValidationFailure(ValidationStageFailure):
    """A source reference is unknown, duplicated, or otherwise invalid."""


class EvidenceVerificationFailure(ValidationStageFailure):
    """Evidence is unsupported, incomplete, or could not be verified."""


class TemporalSafeguardFailure(ValidationStageFailure):
    """A temporal or review invariant cannot be represented safely."""


class ResponseConstructionFailure(ValidationStageFailure):
    """A verified extraction cannot satisfy the public response contract."""
