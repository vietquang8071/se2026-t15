"""Parse provider output into the internal Candidate Schema v1 models."""

from pydantic import ValidationError

from app.schemas.candidates import (
    SummaryActionsCandidate,
    validate_candidate_for_request,
)
from app.schemas.request import ExtractionRequest


class CandidateParseError(Exception):
    """Base class for sanitized candidate parsing failures."""


class CandidateFormatError(CandidateParseError):
    """Raised when output is not valid JSON matching Candidate Schema v1."""


class CandidateRequestMismatchError(CandidateParseError):
    """Raised when candidate module values conflict with the extraction request."""


def parse_candidate(
    content: str,
    request: ExtractionRequest,
) -> SummaryActionsCandidate:
    """Parse strict JSON and enforce request-aware module selection.

    This validates structure only. It does not verify that source IDs exist or
    support claims, nor does it infer or validate semantic owner/deadline data.
    """

    if not content.strip():
        raise CandidateFormatError("Candidate output must be non-empty JSON.")

    try:
        candidate = SummaryActionsCandidate.model_validate_json(content)
    except ValidationError:
        raise CandidateFormatError(
            "Candidate output does not match Candidate Schema v1."
        ) from None

    try:
        validate_candidate_for_request(candidate, request)
    except ValueError:
        raise CandidateRequestMismatchError(
            "Candidate modules do not match the extraction request."
        ) from None

    return candidate
