"""Composition helpers for the internal candidate extraction pipeline."""

from __future__ import annotations

from app.core.config import Settings
from app.providers.openrouter import OpenRouterAdapter
from app.providers.protocol import LLMProvider
from app.services.orchestration import CandidateExtractionOrchestrator
from app.services.preflight import ExtractionPreflight


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

    if provider is None:
        if provider_name not in (None, "openrouter"):
            raise ValueError(
                "The default OpenRouter provider requires provider_name 'openrouter'."
            )
        selected_provider: LLMProvider = OpenRouterAdapter(settings)
        selected_name = "openrouter"
    else:
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
        selected_provider = provider
        selected_name = provider_name

    return CandidateExtractionOrchestrator(
        provider=selected_provider,
        preflight=preflight if preflight is not None else ExtractionPreflight(),
        provider_name=selected_name,
    )
