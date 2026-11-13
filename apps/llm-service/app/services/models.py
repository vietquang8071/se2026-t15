"""Internal data contracts between extraction pipeline stages."""

from dataclasses import dataclass, field
from datetime import datetime

from app.providers.models import ProviderUsage
from app.prompts.renderer import RenderedPrompt
from app.schemas.candidates import SummaryActionsCandidate
from app.schemas.request import ExtractionRequest


@dataclass(frozen=True, slots=True)
class PreparedRequest:
    """Validated request and rendered prompt, ready for provider invocation."""

    request: ExtractionRequest = field(repr=False)
    rendered_prompt: RenderedPrompt = field(repr=False)


@dataclass(frozen=True, slots=True)
class PreparedExtraction:
    """Parsed but unverified candidate and metadata from actual generation."""

    request: ExtractionRequest = field(repr=False)
    candidate: SummaryActionsCandidate = field(repr=False)
    prompt_version: str
    candidate_schema_version: str
    model_id: str
    provider: str | None = None
    token_usage: ProviderUsage | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
