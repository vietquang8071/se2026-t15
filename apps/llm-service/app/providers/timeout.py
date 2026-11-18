"""Per-generation timeout wrapper for any provider implementation."""

from __future__ import annotations

import asyncio

from app.providers.errors import ProviderTimeoutError
from app.providers.models import ProviderRequest, ProviderResult
from app.providers.protocol import LLMProvider


class ProviderTimeoutBound(LLMProvider):
    """Enforce the configured call budget and preserve cancellation semantics."""

    def __init__(self, provider: LLMProvider, *, timeout_seconds: float) -> None:
        self._provider = provider
        self._timeout_seconds = timeout_seconds

    async def generate(self, request: ProviderRequest) -> ProviderResult:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                return await self._provider.generate(request)
        except TimeoutError:
            raise ProviderTimeoutError from None
