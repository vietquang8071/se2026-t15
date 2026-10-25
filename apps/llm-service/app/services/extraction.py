"""Extraction use-case boundary used by the HTTP runtime."""

from __future__ import annotations

from typing import Protocol

from app.core.errors import ExtractionUnavailableError
from app.schemas.request import ExtractionRequest
from app.schemas.response import ExtractionResponse


class ExtractionService(Protocol):
    async def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        """Return a completed, contract-valid response for a request."""


class UnconfiguredExtractionService:
    """Explicit LLM-02 placeholder that never fabricates extraction results."""

    async def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        raise ExtractionUnavailableError
