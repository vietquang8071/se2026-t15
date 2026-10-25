"""Shared strict types and parsing helpers for the public contract."""

from __future__ import annotations

import math
from datetime import date
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictStr,
)
from pydantic_core import PydanticCustomError


class ContractModel(BaseModel):
    """Base model that rejects undocumented fields and implicit coercion."""

    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)


def _validate_non_blank(value: str) -> str:
    if not value.strip():
        raise PydanticCustomError("blank_string", "String must contain non-whitespace text.")
    return value


NonBlankString = Annotated[StrictStr, Field(min_length=1), AfterValidator(_validate_non_blank)]
OpaqueId = Annotated[NonBlankString, Field(max_length=128)]


def _parse_json_number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PydanticCustomError("json_number_type", "Input must be a JSON number.")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise PydanticCustomError("finite_number", "Input must be a finite number.")
    return parsed


JsonNumber = Annotated[
    float,
    BeforeValidator(_parse_json_number),
    Field(allow_inf_nan=False),
]


def _parse_iso_date(value: object) -> date:
    if not isinstance(value, str):
        raise PydanticCustomError("date_string_type", "Date must be an ISO date string.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise PydanticCustomError(
            "iso_date",
            "Date must be a valid YYYY-MM-DD calendar date.",
        ) from error
    if parsed.isoformat() != value:
        raise PydanticCustomError(
            "iso_date",
            "Date must use the exact YYYY-MM-DD format.",
        )
    return parsed


IsoDate = Annotated[date, BeforeValidator(_parse_iso_date)]


def ensure_unique(values: list[str], *, label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} values must be unique.")
