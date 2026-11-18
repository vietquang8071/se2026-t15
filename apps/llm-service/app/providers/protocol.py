"""Generation boundary consumed by application services."""

from typing import Protocol

from app.providers.models import ProviderRequest, ProviderResult


class LLMProvider(Protocol):
    async def generate(self, request: ProviderRequest) -> ProviderResult:
        """Return an unverified generation candidate or raise a provider error."""
