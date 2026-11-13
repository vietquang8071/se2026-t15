"""Project parsed extraction candidates into an internal verification input."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.schemas.candidates import ActionItemCandidate, MeetingSummaryCandidate
from app.services.models import PreparedExtraction


@dataclass(frozen=True, slots=True)
class ProjectedMeetingSummary:
    """Request-derived meeting metadata paired with unverified summary content."""

    title: str = field(repr=False)
    date: date = field(repr=False)
    duration_minutes: float = field(repr=False)
    participants: tuple[str, ...] = field(repr=False)
    candidate: MeetingSummaryCandidate = field(repr=False)


@dataclass(frozen=True, slots=True)
class ProjectedExtraction:
    """Internal projection retaining its parsed, unverified origin."""

    prepared_extraction: PreparedExtraction = field(repr=False)
    meeting_summary: ProjectedMeetingSummary | None = field(repr=False)
    action_items: list[ActionItemCandidate] | None = field(repr=False)


class ExtractionProjector:
    """Map trusted request metadata and candidate content without verification."""

    def project(self, extraction: PreparedExtraction) -> ProjectedExtraction:
        """Return a deterministic projection without mutating the extraction.

        Candidate null states are trusted from ``parse_candidate``. Candidate
        Pydantic models are reused by reference and remain mutable; callers
        must treat them as read-only until downstream validation is complete.
        """

        request = extraction.request
        candidate = extraction.candidate
        summary_candidate = candidate.meeting_summary

        summary = None
        if summary_candidate is not None:
            summary = ProjectedMeetingSummary(
                title=request.meeting.title,
                date=request.meeting.anchor_date,
                duration_minutes=round(request.meeting.duration_seconds / 60, 2),
                participants=tuple(
                    participant.display_name
                    for participant in request.meeting.participants
                ),
                candidate=summary_candidate,
            )

        actions = (
            None
            if candidate.action_items is None
            else list(candidate.action_items)
        )

        return ProjectedExtraction(
            prepared_extraction=extraction,
            meeting_summary=summary,
            action_items=actions,
        )
