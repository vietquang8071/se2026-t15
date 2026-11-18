"""Strict internal candidates returned by extraction prompts.

These models validate structure only. Transcript-reference existence and claim
support are checked by later pipeline stages, before building public responses.
"""

from __future__ import annotations

from pydantic import Field, field_validator

from app.schemas.common import ContractModel, NonBlankString, OpaqueId, ensure_unique
from app.schemas.request import ExtractionRequest
from app.schemas.response import Priority

CANDIDATE_SCHEMA_VERSION = "candidate-v1"


class _SourcedCandidate(ContractModel):
    """Shared structural rules for candidates citing transcript segments."""

    source_segment_ids: list[OpaqueId] = Field(min_length=1)

    @field_validator("source_segment_ids")
    @classmethod
    def source_segment_ids_are_unique(cls, value: list[str]) -> list[str]:
        ensure_unique(value, label="source_segment_ids")
        return value


class KeyTopicCandidate(_SourcedCandidate):
    """Unverified topic and discussion text with transcript references."""

    topic: NonBlankString
    brief_discussion: NonBlankString


class MeetingSummaryCandidate(_SourcedCandidate):
    """Unverified summary content, without derived meeting metadata."""

    overview: NonBlankString
    key_topics: list[KeyTopicCandidate]


class ActionItemCandidate(_SourcedCandidate):
    """Unverified commitment candidate before temporal/evidence processing."""

    task: NonBlankString
    owner: NonBlankString | None
    raw_due_expression: NonBlankString | None
    priority: Priority | None
    context: NonBlankString | None


class SummaryActionsCandidate(ContractModel):
    """Candidate output for the currently supported summary/actions modules."""

    meeting_summary: MeetingSummaryCandidate | None
    action_items: list[ActionItemCandidate] | None


def validate_candidate_for_request(
    candidate: SummaryActionsCandidate,
    request: ExtractionRequest,
) -> SummaryActionsCandidate:
    """Ensure candidate module presence matches the request.

    This deliberately does not resolve source IDs against the transcript or
    assess whether the cited text supports any generated claim.
    """

    requested_modules = set(request.extraction.requested_modules)
    supported_modules = {"meeting_summary", "action_items"}
    unsupported_modules = requested_modules - supported_modules
    if unsupported_modules:
        names = ", ".join(sorted(unsupported_modules))
        raise ValueError(f"Unsupported requested modules: {names}.")

    if "meeting_summary" in requested_modules:
        if candidate.meeting_summary is None:
            raise ValueError("Requested meeting_summary module must not be null.")
    elif candidate.meeting_summary is not None:
        raise ValueError("Unrequested meeting_summary module must be null.")

    if "action_items" in requested_modules:
        if candidate.action_items is None:
            raise ValueError("Requested action_items module must not be null.")
    elif candidate.action_items is not None:
        raise ValueError("Unrequested action_items module must be null.")

    return candidate
