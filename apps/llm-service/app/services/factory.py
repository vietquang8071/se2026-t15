"""Composition helpers for the internal candidate extraction pipeline."""

from __future__ import annotations

from app.core.config import Settings
from app.providers.openrouter import OpenRouterAdapter
from app.providers.protocol import LLMProvider
from app.providers.timeout import ProviderTimeoutBound
from app.services.evidence import EvidenceVerifier
from app.services.orchestration import CandidateExtractionOrchestrator
from app.services.preflight import ExtractionPreflight
from app.services.projection import ExtractionProjector
from app.services.response_builder import ResponseBuilder
from app.services.source_validation import SourceValidator
from app.services.temporal_safeguards import TemporalReviewProcessor
from app.services.verified_extraction import VerifiedExtractionService


def _select_provider(
    settings: Settings,
    *,
    provider: LLMProvider | None,
    provider_name: str | None,
) -> tuple[LLMProvider, str]:
    if provider is None:
        if provider_name not in (None, "openrouter"):
            raise ValueError(
                "The default OpenRouter provider requires provider_name 'openrouter'."
            )
        return OpenRouterAdapter(settings), "openrouter"

    if provider_name is None or not provider_name.strip():
        raise ValueError("A custom provider requires a non-empty provider_name.")
    if provider_name != provider_name.strip():
        raise ValueError("provider_name must be trimmed.")

    is_openrouter = isinstance(provider, OpenRouterAdapter)
    if is_openrouter and provider_name != "openrouter":
        raise ValueError("OpenRouterAdapter must use provider_name 'openrouter'.")
    if not is_openrouter and provider_name == "openrouter":
        raise ValueError(
            "A custom provider cannot use the reserved 'openrouter' identity."
        )
    return provider, provider_name


def create_candidate_orchestrator(
    settings: Settings,
    *,
    provider: LLMProvider | None = None,
    provider_name: str | None = None,
    preflight: ExtractionPreflight | None = None,
) -> CandidateExtractionOrchestrator:
    """Build the internal orchestrator without performing network I/O.

    The default composition is OpenRouter. A custom provider must declare its
    own identity so test or alternate providers cannot be mislabeled.
    """

    selected_provider, selected_name = _select_provider(
        settings, provider=provider, provider_name=provider_name
    )

    return CandidateExtractionOrchestrator(
        provider=selected_provider,
        preflight=preflight if preflight is not None else ExtractionPreflight(),
        provider_name=selected_name,
    )


def create_verified_extraction_service(
    settings: Settings,
    *,
    provider: LLMProvider | None = None,
    provider_name: str | None = None,
    preflight: ExtractionPreflight | None = None,
) -> VerifiedExtractionService:
    """Compose the complete fail-closed pipeline without performing I/O."""

    selected_provider, selected_name = _select_provider(
        settings, provider=provider, provider_name=provider_name
    )
    bounded_provider = ProviderTimeoutBound(
        selected_provider,
        timeout_seconds=settings.llm_service_provider_timeout_seconds,
    )
    selected_preflight = preflight or ExtractionPreflight()
    orchestrator = CandidateExtractionOrchestrator(
        provider=bounded_provider,
        preflight=selected_preflight,
        provider_name=selected_name,
    )
    verifier = EvidenceVerifier(
        provider=bounded_provider,
        provider_name=selected_name,
    )
    return VerifiedExtractionService(
        orchestrator=orchestrator,
        projector=ExtractionProjector(),
        source_validator=SourceValidator(),
        verifier=verifier,
        temporal_processor=TemporalReviewProcessor(),
        response_builder=ResponseBuilder(),
    )
