"""Provider-neutral semantic evidence verification for Summary and Actions."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import ValidationError

from app.prompts.registry import PromptRegistry, PromptRegistryError
from app.prompts.renderer import PromptRenderer, PromptRendererError
from app.providers.errors import ProviderConfigurationError
from app.providers.protocol import LLMProvider
from app.schemas.verification import EvidenceVerificationOutput
from app.services.validation_models import (
    EvidenceVerificationFailure,
    EvidenceVerifiedExtraction,
    SourceValidatedExtraction,
    VerificationMetadata,
    VerificationStatus,
    VerificationVerdict,
)

EVIDENCE_PROMPT_VERSION = "evidence-v1.3"


class EvidenceVerifier:
    """Verify all source-validated claims in one strict provider generation."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        provider_name: str,
        registry: PromptRegistry | None = None,
        renderer: PromptRenderer | None = None,
    ) -> None:
        self._provider = provider
        self._provider_name = provider_name
        self._registry = registry if registry is not None else PromptRegistry()
        self._renderer = renderer if renderer is not None else PromptRenderer()

    async def verify(
        self, extraction: SourceValidatedExtraction
    ) -> EvidenceVerifiedExtraction:
        """Return a complete request-bound verdict set, or fail closed."""

        prepared = extraction.projected.prepared_extraction
        if prepared.provider != self._provider_name:
            raise ProviderConfigurationError
        try:
            bundle = self._registry.get_evidence(EVIDENCE_PROMPT_VERSION)
            rendered = self._renderer.render_evidence(extraction, bundle)
        except (PromptRegistryError, PromptRendererError):
            raise EvidenceVerificationFailure(
                "INTERNAL_ERROR", "Evidence verification could not be prepared."
            ) from None

        started_at = datetime.now(timezone.utc)
        result = await self._provider.generate(rendered.provider_request)
        completed_at = datetime.now(timezone.utc)
        if completed_at < started_at:
            completed_at = started_at

        if result.model_id != prepared.model_id:
            raise ProviderConfigurationError
        try:
            parsed = EvidenceVerificationOutput.model_validate_json(result.content)
            verdicts = tuple(
                VerificationVerdict(
                    request_id=extraction.request_id,
                    transcript_revision_id=extraction.transcript_revision_id,
                    claim_id=check.claim_id,
                    status=VerificationStatus(check.status),
                )
                for check in parsed.checks
            )
            metadata = VerificationMetadata(
                provider=self._provider_name,
                model_id=result.model_id,
                prompt_version=rendered.prompt_version,
                token_usage=result.usage,
                started_at=started_at,
                completed_at=completed_at,
            )
            return EvidenceVerifiedExtraction(
                source_validated=extraction,
                verdicts=verdicts,
                metadata=metadata,
            )
        except (ValidationError, ValueError):
            raise EvidenceVerificationFailure(
                "INVALID_STRUCTURED_OUTPUT",
                "Evidence verifier output does not match the required schema.",
            ) from None
