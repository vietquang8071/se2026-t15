"""Internal orchestration from a validated request to an unverified candidate."""

from __future__ import annotations

from datetime import datetime, timezone

from app.parsing.candidates import parse_candidate
from app.providers.protocol import LLMProvider
from app.schemas.request import ExtractionRequest
from app.services.models import PreparedExtraction
from app.services.preflight import ExtractionPreflight


class CandidateExtractionOrchestrator:
    """Run preflight, one provider generation, and candidate parsing.

    The result is intentionally an internal, unverified extraction. This class
    does not implement the public ``ExtractionService`` contract.
    """

    def __init__(
        self,
        *,
        provider: LLMProvider,
        preflight: ExtractionPreflight,
        provider_name: str,
    ) -> None:
        if not provider_name or not provider_name.strip():
            raise ValueError("provider_name must be a non-empty identity.")
        if provider_name != provider_name.strip():
            raise ValueError("provider_name must be trimmed.")

        self._provider = provider
        self._preflight = preflight
        self._provider_name = provider_name

    async def run(self, request: ExtractionRequest) -> PreparedExtraction:
        """Return one parsed candidate, preserving provider and prompt metadata."""

        prepared = self._preflight.prepare(request)
        started_at = datetime.now(timezone.utc)
        result = await self._provider.generate(prepared.rendered_prompt.provider_request)
        candidate = parse_candidate(result.content, prepared.request)
        completed_at = datetime.now(timezone.utc)

        # A system clock adjustment can move wall time backwards during a run.
        # Keep the reported interval ordered while using only captured UTC times.
        if completed_at < started_at:
            completed_at = started_at

        return PreparedExtraction(
            request=prepared.request,
            candidate=candidate,
            prompt_version=prepared.rendered_prompt.prompt_version,
            candidate_schema_version=prepared.rendered_prompt.candidate_schema_version,
            model_id=result.model_id,
            provider=self._provider_name,
            token_usage=result.usage,
            started_at=started_at,
            completed_at=completed_at,
        )
