"""Strict, private schema returned by the semantic evidence verifier."""

from typing import Literal

from pydantic import Field, StrictStr

from app.schemas.common import ContractModel


class VerificationCheck(ContractModel):
    claim_id: StrictStr = Field(min_length=1, max_length=256)
    status: Literal["supported", "uncertain", "unsupported"]


class EvidenceVerificationOutput(ContractModel):
    checks: list[VerificationCheck] = Field(min_length=1)
