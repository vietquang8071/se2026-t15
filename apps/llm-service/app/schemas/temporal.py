"""Structured temporal resolution result models."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.common import ContractModel, IsoDate, OpaqueId, ensure_unique

TemporalStatus = Literal["exact_date", "date_range", "unresolved"]


class TemporalResolution(ContractModel):
    status: TemporalStatus
    resolved_date: IsoDate | None
    start_date: IsoDate | None
    end_date: IsoDate | None
    needs_review: bool
    source_segment_ids: list[OpaqueId] = Field(min_length=1)

    @field_validator("source_segment_ids")
    @classmethod
    def source_ids_are_unique(cls, value: list[str]) -> list[str]:
        ensure_unique(value, label="temporal source_segment_ids")
        return value

    @model_validator(mode="after")
    def temporal_state_is_consistent(self) -> TemporalResolution:
        if self.status == "exact_date":
            if self.resolved_date is None or self.start_date is not None or self.end_date is not None:
                raise ValueError(
                    "exact_date requires resolved_date and forbids range endpoints."
                )
            if self.needs_review:
                raise ValueError("exact_date must not require temporal review.")
        elif self.status == "date_range":
            if self.resolved_date is not None:
                raise ValueError("date_range must not include resolved_date.")
            if self.start_date is None or self.end_date is None:
                raise ValueError("date_range requires both inclusive endpoints.")
            if self.start_date > self.end_date:
                raise ValueError("date_range start_date must not exceed end_date.")
            if not self.needs_review:
                raise ValueError("date_range must require review.")
        else:
            if any((self.resolved_date, self.start_date, self.end_date)):
                raise ValueError("unresolved must not include resolved date fields.")
            if not self.needs_review:
                raise ValueError("unresolved must require review.")
        return self
