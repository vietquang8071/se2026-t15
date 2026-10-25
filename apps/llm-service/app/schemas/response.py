"""Pydantic models for completed extraction responses."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import (
    BeforeValidator,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app.schemas.common import (
    ContractModel,
    IsoDate,
    JsonNumber,
    NonBlankString,
    OpaqueId,
    ensure_unique,
)
from app.schemas.request import ExtractionRequest, ModuleName
from app.schemas.temporal import TemporalResolution

ReviewReason = Literal[
    "owner_unconfirmed",
    "date_range_needs_confirmation",
    "temporal_unresolved",
    "evidence_unverified",
    "conflicting_statements",
    "speaker_unmapped",
    "claim_uncertain",
]
Priority = Literal["High", "Medium", "Low"]
EventType = Literal["milestone", "deadline", "demo", "release", "review", "other"]
ArtifactId = Annotated[StrictStr, Field(pattern=r"^(?:ACT|DEC|ISS|FLW|EVT)-\d{3,}$")]
SourceTimestamp = Annotated[
    StrictStr,
    Field(pattern=r"^\d{2,}:[0-5]\d:[0-5]\d\.\d{3}$"),
]
NonNegativeInteger = Annotated[StrictInt, Field(ge=0)]
PositiveJsonNumber = Annotated[JsonNumber, Field(gt=0)]


def _parse_utc_datetime(value: object) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)",
        value,
    ):
        raise PydanticCustomError(
            "utc_datetime",
            "Timestamp must be an RFC 3339 UTC string.",
        )
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise PydanticCustomError(
            "utc_datetime",
            "Timestamp must be a valid RFC 3339 UTC value.",
        ) from error
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise PydanticCustomError(
            "utc_datetime",
            "Timestamp must use the UTC timezone.",
        )
    return parsed


RFC3339UTC = Annotated[datetime, BeforeValidator(_parse_utc_datetime)]


def _source_lists_are_unique(value: list[str]) -> list[str]:
    ensure_unique(value, label="source_segment_ids")
    return value


class ReviewableModel(ContractModel):
    needs_review: bool
    review_reasons: list[ReviewReason]

    @field_validator("review_reasons")
    @classmethod
    def review_reasons_are_unique(cls, value: list[ReviewReason]) -> list[ReviewReason]:
        ensure_unique(value, label="review_reasons")
        return value

    @model_validator(mode="after")
    def review_state_matches_reasons(self) -> ReviewableModel:
        if self.needs_review != bool(self.review_reasons):
            raise ValueError("needs_review must match whether review_reasons is nonempty.")
        return self


class SourcedReviewableModel(ReviewableModel):
    source_segment_ids: list[OpaqueId] = Field(min_length=1)

    @field_validator("source_segment_ids")
    @classmethod
    def source_segment_ids_are_unique(cls, value: list[str]) -> list[str]:
        return _source_lists_are_unique(value)


class TimestampedArtifact(SourcedReviewableModel):
    source_timestamp: SourceTimestamp


class KeyTopic(SourcedReviewableModel):
    topic: NonBlankString
    brief_discussion: NonBlankString


class MeetingSummary(ReviewableModel):
    title: Annotated[NonBlankString, Field(max_length=200)]
    date: IsoDate
    duration_minutes: PositiveJsonNumber
    participants: list[NonBlankString]
    overview: NonBlankString
    key_topics: list[KeyTopic]
    source_segment_ids: list[OpaqueId] = Field(min_length=1)

    @field_validator("source_segment_ids")
    @classmethod
    def source_segment_ids_are_unique(cls, value: list[str]) -> list[str]:
        return _source_lists_are_unique(value)


class ActionItem(TimestampedArtifact):
    id: Annotated[StrictStr, Field(pattern=r"^ACT-\d{3,}$")]
    task: NonBlankString
    owner: NonBlankString | None
    due_date: IsoDate | None
    raw_due_expression: NonBlankString | None
    due_date_resolution: TemporalResolution | None
    priority: Priority | None
    context: NonBlankString | None

    @model_validator(mode="after")
    def due_date_matches_temporal_resolution(self) -> ActionItem:
        if self.raw_due_expression is None:
            if self.due_date is not None or self.due_date_resolution is not None:
                raise ValueError("Due-date fields require raw_due_expression.")
        elif self.due_date_resolution is None:
            raise ValueError("A raw due expression requires temporal resolution.")
        if self.due_date_resolution is not None:
            if self.due_date != self.due_date_resolution.resolved_date:
                raise ValueError("due_date must match the exact temporal resolution date.")
            if not set(self.due_date_resolution.source_segment_ids).issubset(
                self.source_segment_ids
            ):
                raise ValueError("Temporal source IDs must be a subset of artifact source IDs.")
        return self


class DecisionArtifact(TimestampedArtifact):
    id: Annotated[StrictStr, Field(pattern=r"^DEC-\d{3,}$")]
    decision: NonBlankString
    rationale: NonBlankString | None
    alternatives_considered: NonBlankString | None


class OpenIssue(TimestampedArtifact):
    id: Annotated[StrictStr, Field(pattern=r"^ISS-\d{3,}$")]
    issue_or_question: NonBlankString
    raised_by: NonBlankString | None
    blocker_severity: Priority | None
    status: Literal["Unresolved"]


class FollowUpItem(TimestampedArtifact):
    id: Annotated[StrictStr, Field(pattern=r"^FLW-\d{3,}$")]
    item: NonBlankString
    responsible_party: NonBlankString | None
    target_trigger_or_date: NonBlankString | None
    target_temporal_resolution: TemporalResolution | None

    @model_validator(mode="after")
    def temporal_source_is_part_of_artifact(self) -> FollowUpItem:
        resolution = self.target_temporal_resolution
        if resolution is not None:
            if self.target_trigger_or_date is None:
                raise ValueError("Temporal resolution requires target_trigger_or_date.")
            if not set(resolution.source_segment_ids).issubset(self.source_segment_ids):
                raise ValueError("Temporal source IDs must be a subset of artifact source IDs.")
        return self


class TimelineEvent(TimestampedArtifact):
    id: Annotated[StrictStr, Field(pattern=r"^EVT-\d{3,}$")]
    event: NonBlankString
    resolved_date: IsoDate | None
    event_type: EventType
    raw_statement: NonBlankString
    temporal_resolution: TemporalResolution

    @model_validator(mode="after")
    def resolved_date_matches_temporal_resolution(self) -> TimelineEvent:
        resolution = self.temporal_resolution
        if self.resolved_date != resolution.resolved_date:
            raise ValueError("resolved_date must match temporal_resolution.")
        if not set(resolution.source_segment_ids).issubset(self.source_segment_ids):
            raise ValueError("Temporal source IDs must be a subset of artifact source IDs.")
        if self.needs_review != resolution.needs_review and not self.review_reasons:
            raise ValueError("Temporal uncertainty must be reflected in artifact review state.")
        return self


class TokenUsage(ContractModel):
    input_tokens: NonNegativeInteger
    output_tokens: NonNegativeInteger


class ProcessingMetadata(ContractModel):
    provider: NonBlankString
    model_id: NonBlankString
    prompt_version: NonBlankString
    evidence_prompt_version: NonBlankString
    started_at: RFC3339UTC
    completed_at: RFC3339UTC
    token_usage: TokenUsage | None

    @model_validator(mode="after")
    def completion_follows_start(self) -> ProcessingMetadata:
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must not precede started_at.")
        return self


class ExtractionModules(ContractModel):
    meeting_summary: MeetingSummary | None
    action_items: list[ActionItem] | None
    decision_log: list[DecisionArtifact] | None
    open_issues: list[OpenIssue] | None
    follow_up_items: list[FollowUpItem] | None
    timeline_events: list[TimelineEvent] | None

    @model_validator(mode="after")
    def artifact_ids_are_unique_within_each_module(self) -> ExtractionModules:
        for items in (
            self.action_items,
            self.decision_log,
            self.open_issues,
            self.follow_up_items,
            self.timeline_events,
        ):
            if items is not None:
                ensure_unique([item.id for item in items], label="artifact IDs")
        return self


class ExtractionResponse(ContractModel):
    contract_version: Literal["1.0"]
    request_id: OpaqueId
    status: Literal["completed"]
    meeting_id: OpaqueId
    transcript_revision_id: OpaqueId
    requested_modules: list[ModuleName] = Field(min_length=1, max_length=6)
    modules: ExtractionModules
    processing: ProcessingMetadata

    @field_validator("requested_modules")
    @classmethod
    def requested_modules_are_unique(cls, value: list[ModuleName]) -> list[ModuleName]:
        ensure_unique(value, label="requested_modules")
        return value

    @model_validator(mode="after")
    def module_null_state_matches_request(self) -> ExtractionResponse:
        for module_name in ModuleName.__args__:
            value = getattr(self.modules, module_name)
            is_requested = module_name in self.requested_modules
            if is_requested and value is None:
                raise ValueError(f"Requested module {module_name} cannot be null.")
            if not is_requested and value is not None:
                raise ValueError(f"Unrequested module {module_name} must be null.")
        return self


def validate_response_for_request(
    request: ExtractionRequest,
    response: ExtractionResponse,
) -> ExtractionResponse:
    """Validate request/response identity and references without deriving timestamps."""

    if response.contract_version != request.contract_version:
        raise ValueError("Response contract_version does not match request.")
    if response.request_id != request.request_id:
        raise ValueError("Response request_id does not match request.")
    if response.meeting_id != request.meeting.id:
        raise ValueError("Response meeting_id does not match request.")
    if response.transcript_revision_id != request.transcript.revision_id:
        raise ValueError("Response transcript_revision_id does not match request.")
    if response.requested_modules != request.extraction.requested_modules:
        raise ValueError("Response requested_modules do not match request.")

    summary = response.modules.meeting_summary
    if summary is not None:
        expected_duration = round(request.meeting.duration_seconds / 60, 2)
        expected_participants = [
            participant.display_name for participant in request.meeting.participants
        ]
        if (
            summary.title != request.meeting.title
            or summary.date != request.meeting.anchor_date
            or summary.duration_minutes != expected_duration
            or summary.participants != expected_participants
        ):
            raise ValueError("Meeting summary metadata does not match request context.")

    segment_ids = {segment.id for segment in request.transcript.segments}
    segment_starts = {segment.id: segment.start for segment in request.transcript.segments}
    for source_ids in _response_source_lists(response):
        missing = [source_id for source_id in source_ids if source_id not in segment_ids]
        if missing:
            raise ValueError(f"Response source references unknown transcript segments: {missing}")
        source_starts = [segment_starts[source_id] for source_id in source_ids]
        if source_starts != sorted(source_starts):
            raise ValueError("source_segment_ids must be ordered by segment start time.")
    return response


def _response_source_lists(response: ExtractionResponse) -> list[list[str]]:
    sources: list[list[str]] = []
    summary = response.modules.meeting_summary
    if summary is not None:
        sources.append(summary.source_segment_ids)
        sources.extend(topic.source_segment_ids for topic in summary.key_topics)
    for items in (
        response.modules.action_items,
        response.modules.decision_log,
        response.modules.open_issues,
        response.modules.follow_up_items,
        response.modules.timeline_events,
    ):
        if items is not None:
            sources.extend(item.source_segment_ids for item in items)
            for item in items:
                if isinstance(item, ActionItem) and item.due_date_resolution is not None:
                    sources.append(item.due_date_resolution.source_segment_ids)
                elif (
                    isinstance(item, FollowUpItem)
                    and item.target_temporal_resolution is not None
                ):
                    sources.append(item.target_temporal_resolution.source_segment_ids)
                elif isinstance(item, TimelineEvent):
                    sources.append(item.temporal_resolution.source_segment_ids)
    return sources
