"""Render validated extraction requests into provider-neutral messages."""

import json
from dataclasses import dataclass
from string import Template

from app.prompts.registry import PromptBundle
from app.providers.models import ProviderMessage, ProviderRequest
from app.schemas.request import ExtractionRequest

_SUPPORTED_MODULES = frozenset({"meeting_summary", "action_items"})
_REQUIRED_PLACEHOLDERS = frozenset(
    {
        "output_language",
        "requested_modules_json",
        "meeting_context_json",
        "transcript_segments_json",
    }
)


class PromptRendererError(Exception):
    """Sanitized error raised when a request cannot be rendered safely."""


@dataclass(frozen=True, slots=True)
class RenderedPrompt:
    """Provider request and prompt/schema metadata for downstream tracking."""

    provider_request: ProviderRequest
    prompt_version: str
    candidate_schema_version: str


class PromptRenderer:
    """Build a provider request without calling a provider or altering speech."""

    def render(
        self,
        request: ExtractionRequest,
        bundle: PromptBundle,
    ) -> RenderedPrompt:
        """Render one supported request using exactly one template pass."""

        requested_modules = request.extraction.requested_modules
        unsupported_modules = set(requested_modules) - _SUPPORTED_MODULES
        if unsupported_modules:
            raise PromptRendererError("Unsupported requested modules for this prompt version.")

        template = Template(bundle.extraction_template)
        if not template.is_valid():
            raise PromptRendererError("Prompt template syntax is invalid.")
        if set(template.get_identifiers()) != _REQUIRED_PLACEHOLDERS:
            raise PromptRendererError("Prompt template placeholders are invalid.")

        try:
            extraction_prompt = template.substitute(
                {
                    "output_language": request.extraction.output_language,
                    "requested_modules_json": self._serialize(
                        list(requested_modules)
                    ),
                    "meeting_context_json": self._serialize(
                        self._meeting_context(request)
                    ),
                    "transcript_segments_json": self._serialize(
                        self._transcript_segments(request)
                    ),
                }
            )
        except (KeyError, TypeError, ValueError):
            raise PromptRendererError("Prompt request could not be rendered.") from None

        provider_request = ProviderRequest(
            messages=[
                ProviderMessage(role="system", content=bundle.system_template),
                ProviderMessage(role="user", content=extraction_prompt),
            ],
            structured_output_mode="json_object",
        )
        return RenderedPrompt(
            provider_request=provider_request,
            prompt_version=bundle.prompt_version,
            candidate_schema_version=bundle.candidate_schema_version,
        )

    @staticmethod
    def _meeting_context(request: ExtractionRequest) -> dict[str, object]:
        return {
            "participants": [
                {
                    "display_name": participant.display_name,
                    "speaker_ids": participant.speaker_ids,
                }
                for participant in request.meeting.participants
            ]
        }

    @staticmethod
    def _transcript_segments(request: ExtractionRequest) -> list[dict[str, object]]:
        return [
            {
                "id": segment.id,
                "start": segment.start,
                "end": segment.end,
                "speaker_id": segment.speaker_id,
                "text": segment.text,
            }
            for segment in request.transcript.segments
        ]

    @staticmethod
    def _serialize(value: object) -> str:
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
