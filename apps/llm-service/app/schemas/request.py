"""Pydantic models for extraction requests."""

from __future__ import annotations

from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, StrictStr, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.schemas.common import (
    ContractModel,
    IsoDate,
    JsonNumber,
    NonBlankString,
    OpaqueId,
    ensure_unique,
)

ModuleName = Literal[
    "meeting_summary",
    "action_items",
    "decision_log",
    "open_issues",
    "follow_up_items",
    "timeline_events",
]
OutputLanguage = Literal["vi", "en"]
TranscriptLanguage = Annotated[
    StrictStr,
    Field(pattern=r"^(?:[A-Za-z]{2,3}|mul)(?:-[A-Za-z0-9]{2,8})*$"),
]
NonNegativeNumber = Annotated[JsonNumber, Field(ge=0)]
PositiveNumber = Annotated[JsonNumber, Field(gt=0)]


class Participant(ContractModel):
    id: OpaqueId
    display_name: Annotated[NonBlankString, Field(max_length=200)]
    speaker_ids: list[OpaqueId]

    @field_validator("speaker_ids")
    @classmethod
    def speaker_ids_are_unique(cls, value: list[str]) -> list[str]:
        ensure_unique(value, label="speaker_ids")
        return value


class MeetingContext(ContractModel):
    id: OpaqueId
    title: Annotated[NonBlankString, Field(max_length=200)]
    anchor_date: IsoDate
    timezone: Annotated[NonBlankString, Field(max_length=128)]
    duration_seconds: Annotated[PositiveNumber, Field(allow_inf_nan=False)]
    participants: list[Participant]

    @field_validator("title")
    @classmethod
    def title_must_be_trimmed(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("Meeting title must be trimmed.")
        return value

    @field_validator("timezone")
    @classmethod
    def timezone_must_be_iana(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise PydanticCustomError(
                "iana_timezone",
                "Timezone must be a valid IANA timezone key.",
            ) from error
        return value

    @model_validator(mode="after")
    def participant_ids_are_unique(self) -> MeetingContext:
        ensure_unique([participant.id for participant in self.participants], label="participant IDs")
        return self


class TranscriptSegment(ContractModel):
    id: OpaqueId
    start: NonNegativeNumber
    end: PositiveNumber
    speaker_id: OpaqueId | None
    text: NonBlankString

    @model_validator(mode="after")
    def end_follows_start(self) -> TranscriptSegment:
        if self.end <= self.start:
            raise ValueError("Segment end must be greater than start.")
        return self


class Transcript(ContractModel):
    revision_id: OpaqueId
    language: TranscriptLanguage
    segments: list[TranscriptSegment]

    @model_validator(mode="before")
    @classmethod
    def reject_transcript_without_speech(cls, value: object) -> object:
        if isinstance(value, dict) and isinstance(value.get("segments"), list):
            segments = value["segments"]
            if not segments:
                raise PydanticCustomError(
                    "empty_transcript",
                    "Transcript contains no usable speech text.",
                )
            required_keys = {"id", "start", "end", "speaker_id", "text"}
            well_shaped_segments = all(
                isinstance(segment, dict)
                and set(segment) == required_keys
                and isinstance(segment.get("id"), str)
                and isinstance(segment.get("start"), (int, float))
                and not isinstance(segment.get("start"), bool)
                and isinstance(segment.get("end"), (int, float))
                and not isinstance(segment.get("end"), bool)
                and (
                    segment.get("speaker_id") is None
                    or isinstance(segment.get("speaker_id"), str)
                )
                and isinstance(segment.get("text"), str)
                for segment in segments
            )
            if well_shaped_segments and all(
                not segment["text"].strip() for segment in segments
            ):
                raise PydanticCustomError(
                    "empty_transcript",
                    "Transcript contains no usable speech text.",
                )
        return value

    @field_validator("segments")
    @classmethod
    def segment_ids_are_unique(cls, value: list[TranscriptSegment]) -> list[TranscriptSegment]:
        ensure_unique([segment.id for segment in value], label="segment IDs")
        return value

    @model_validator(mode="after")
    def segments_are_time_ordered(self) -> Transcript:
        previous_start: float | None = None
        for segment in self.segments:
            if previous_start is not None and segment.start < previous_start:
                raise ValueError("Transcript segments must be ordered by nondecreasing start time.")
            previous_start = segment.start
        return self


class ExtractionConfiguration(ContractModel):
    output_language: OutputLanguage
    requested_modules: Annotated[list[ModuleName], Field(min_length=1, max_length=6)]

    @field_validator("requested_modules")
    @classmethod
    def requested_modules_are_unique(cls, value: list[ModuleName]) -> list[ModuleName]:
        ensure_unique(value, label="requested_modules")
        return value


class ExtractionRequest(ContractModel):
    contract_version: Literal["1.0"]
    request_id: OpaqueId
    meeting: MeetingContext
    transcript: Transcript
    extraction: ExtractionConfiguration

    @field_validator("contract_version", mode="before")
    @classmethod
    def require_supported_contract_version(cls, value: object) -> object:
        if value != "1.0":
            raise PydanticCustomError(
                "unsupported_contract_version",
                "Only contract_version 1.0 is supported.",
            )
        return value

    @model_validator(mode="after")
    def request_invariants(self) -> ExtractionRequest:
        segment_ids = [segment.id for segment in self.transcript.segments]
        ensure_unique(segment_ids, label="segment IDs")

        previous_start: float | None = None
        for segment in self.transcript.segments:
            if segment.end > self.meeting.duration_seconds:
                raise ValueError("Segment end must not exceed meeting duration.")
            if previous_start is not None and segment.start < previous_start:
                raise ValueError("Transcript segments must be ordered by nondecreasing start time.")
            previous_start = segment.start

        speaker_owners: dict[str, str] = {}
        for participant in self.meeting.participants:
            for speaker_id in participant.speaker_ids:
                existing_owner = speaker_owners.get(speaker_id)
                if existing_owner is not None and existing_owner != participant.id:
                    raise ValueError("A speaker_id must not map to multiple participants.")
                speaker_owners[speaker_id] = participant.id
        return self
