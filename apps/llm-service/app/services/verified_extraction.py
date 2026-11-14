"""Concrete fail-closed extraction use case used by the HTTP runtime."""

from __future__ import annotations

import math

from pydantic import ValidationError

from app.core.errors import ExtractionServiceError, SAFE_EXTRACTION_ERROR_MESSAGES
from app.parsing.candidates import CandidateParseError
from app.providers.errors import ProviderError
from app.schemas.errors import ErrorCode
from app.schemas.request import ExtractionRequest
from app.schemas.response import ExtractionResponse
from app.services.evidence import EvidenceVerifier
from app.services.orchestration import CandidateExtractionOrchestrator
from app.services.preflight import (
    PromptPreparationError,
    SummaryDurationNotRepresentableError,
    UnsupportedExtractionCapabilityError,
)
from app.services.projection import ExtractionProjector
from app.services.response_builder import ResponseBuilder
from app.services.source_validation import SourceValidator
from app.services.temporal_safeguards import TemporalReviewProcessor
from app.services.validation_models import ValidationStageFailure

class VerifiedExtractionService:
    """Run every mandatory stage before constructing public success output."""

    def __init__(
        self,
        *,
        orchestrator: CandidateExtractionOrchestrator,
        verifier: EvidenceVerifier,
        projector: ExtractionProjector | None = None,
        source_validator: SourceValidator | None = None,
        temporal_processor: TemporalReviewProcessor | None = None,
        response_builder: ResponseBuilder | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._projector = projector or ExtractionProjector()
        self._source_validator = source_validator or SourceValidator()
        self._verifier = verifier
        self._temporal_processor = temporal_processor or TemporalReviewProcessor()
        self._response_builder = response_builder or ResponseBuilder()

    async def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        """Return Contract v1 output only after source, semantic, and safety gates."""

        try:
            candidate = await self._orchestrator.run(request)
            projected = self._projector.project(candidate)
            source_validated = self._source_validator.validate(projected)
            evidence_verified = await self._verifier.verify(source_validated)
            validated = self._temporal_processor.process(evidence_verified)
            return self._response_builder.build(validated)
        except SummaryDurationNotRepresentableError:
            self._raise_public("VALIDATION_ERROR")
        except UnsupportedExtractionCapabilityError:
            self._raise_public("VALIDATION_ERROR")
        except ProviderError as error:
            code = error.code
            if code not in SAFE_EXTRACTION_ERROR_MESSAGES:
                code = "PROVIDER_FAILURE"
            retry_after = getattr(error, "retry_after_seconds", None)
            if (
                isinstance(retry_after, bool)
                or not isinstance(retry_after, (int, float))
                or not math.isfinite(retry_after)
                or retry_after <= 0
                or retry_after > 86_400
            ):
                retry_after = None
            self._raise_public(
                code,
                retryable=error.retryable is True,
                retry_after_seconds=retry_after,
            )
        except CandidateParseError:
            self._raise_public("INVALID_STRUCTURED_OUTPUT")
        except ValidationStageFailure as error:
            code = (
                error.code
                if error.code in SAFE_EXTRACTION_ERROR_MESSAGES
                else "INTERNAL_ERROR"
            )
            self._raise_public(code)
        except ValidationError:
            self._raise_public("INVALID_STRUCTURED_OUTPUT")
        except PromptPreparationError:
            self._raise_public("INTERNAL_ERROR")

    @staticmethod
    def _raise_public(
        code: ErrorCode,
        *,
        retryable: bool = False,
        retry_after_seconds: float | None = None,
    ) -> None:
        raise ExtractionServiceError(
            code=code,
            retryable=retryable,
            retry_after_seconds=retry_after_seconds,
        ) from None
