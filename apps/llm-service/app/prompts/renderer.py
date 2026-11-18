"""Render validated extraction requests into provider-neutral messages."""

from __future__ import annotations

import json
from dataclasses import dataclass
from string import Template
from typing import TYPE_CHECKING

from app.prompts.registry import EvidencePromptBundle, PromptBundle
from app.providers.models import ProviderMessage, ProviderRequest
from app.schemas.request import ExtractionRequest

if TYPE_CHECKING:
    from app.services.validation_models import SourceValidatedExtraction

_SUPPORTED_MODULES = frozenset({"meeting_summary", "action_items"})
_REQUIRED_PLACEHOLDERS = frozenset(
    {
        "output_language",
        "requested_modules_json",
        "meeting_context_json",
        "transcript_segments_json",
    }
)
_REQUIRED_EVIDENCE_PLACEHOLDERS = frozenset(
    {
        "request_context_json",
        "participant_mapping_json",
        "transcript_segments_json",
        "claims_json",
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


@dataclass(frozen=True, slots=True)
class RenderedEvidencePrompt:
    """Provider-neutral evidence prompt and the registry version that ran."""

    provider_request: ProviderRequest
    prompt_version: str


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

    def render_evidence(
        self,
        extraction: SourceValidatedExtraction,
        bundle: EvidencePromptBundle,
    ) -> RenderedEvidencePrompt:
        """Render strict verification input, keeping transcript data untrusted."""

        request = extraction.projected.prepared_extraction.request
        template = Template(bundle.verification_template)
        if (
            not template.is_valid()
            or set(template.get_identifiers()) != _REQUIRED_EVIDENCE_PLACEHOLDERS
        ):
            raise PromptRendererError("Evidence prompt placeholders are invalid.")

        action_context_by_claim_id: dict[str, dict[str, object]] = {}
        if extraction.action_candidates is not None:
            for action, original_index in zip(
                extraction.action_candidates, extraction.action_claim_indexes, strict=True
            ):
                action_context = {
                    "task": action.task,
                    "owner": action.owner,
                    "raw_due_expression": action.raw_due_expression,
                    "priority": action.priority,
                    "context": action.context,
                }
                for field_name in (
                    "task",
                    "owner",
                    "raw_due_expression",
                    "priority",
                    "context",
                ):
                    action_context_by_claim_id[
                        f"actions[{original_index}].{field_name}"
                    ] = action_context

        claims_payload = []
        for claim in extraction.claims:
            claim_payload: dict[str, object] = {
                "claim_id": claim.claim_id,
                "content": claim.content,
                "source_segment_ids": claim.source_segment_ids,
            }
            action_context = action_context_by_claim_id.get(claim.claim_id)
            if action_context is not None:
                claim_payload["action_item_context"] = action_context
            claims_payload.append(claim_payload)

        try:
            user_content = template.substitute(
                {
                    "request_context_json": self._serialize(
                        {
                            "request_id": request.request_id,
                            "transcript_revision_id": request.transcript.revision_id,
                            "anchor_date": request.meeting.anchor_date.isoformat(),
                            "timezone": request.meeting.timezone,
                        }
                    ),
                    "participant_mapping_json": self._serialize(
                        [
                            {
                                "participant_id": participant.id,
                                "display_name": participant.display_name,
                                "speaker_ids": participant.speaker_ids,
                            }
                            for participant in request.meeting.participants
                        ]
                    ),
                    "transcript_segments_json": self._serialize(
                        self._transcript_segments(request)
                    ),
                    "claims_json": self._serialize(claims_payload),
                }
            )
        except (KeyError, TypeError, ValueError):
            raise PromptRendererError("Evidence request could not be rendered.") from None

        return RenderedEvidencePrompt(
            provider_request=ProviderRequest(
                messages=[
                    ProviderMessage(role="system", content=bundle.system_template),
                    ProviderMessage(role="user", content=user_content),
                ],
                structured_output_mode="json_object",
                temperature=0,
            ),
            prompt_version=bundle.prompt_version,
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
