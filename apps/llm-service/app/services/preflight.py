"""Prepare validated extraction requests without invoking a provider."""

from app.prompts.registry import PromptRegistry, PromptRegistryError
from app.prompts.renderer import PromptRenderer, PromptRendererError
from app.schemas.request import ExtractionRequest
from app.services.models import PreparedRequest

APPROVED_PROMPT_VERSION = "extract-v1.0"
SUPPORTED_MODULES = frozenset({"meeting_summary", "action_items"})


class ExtractionPreflightError(Exception):
    """Base class for sanitized extraction preflight failures."""


class UnsupportedExtractionCapabilityError(ExtractionPreflightError):
    """Raised when a request includes a module not supported by this pipeline."""

    def __init__(self) -> None:
        super().__init__("Requested extraction modules are not supported.")


class PromptPreparationError(ExtractionPreflightError):
    """Raised when the approved prompt bundle cannot be rendered safely."""

    def __init__(self) -> None:
        super().__init__("The extraction prompt could not be prepared.")


class SummaryDurationNotRepresentableError(ExtractionPreflightError):
    """Requested Summary duration rounds to a value forbidden by Contract v1."""

    def __init__(self) -> None:
        super().__init__(
            "Summary duration cannot be represented as a positive Contract v1 value."
        )


class ExtractionPreflight:
    """Validate capabilities and render one provider-neutral request."""

    def __init__(
        self,
        *,
        registry: PromptRegistry | None = None,
        renderer: PromptRenderer | None = None,
    ) -> None:
        self._registry = registry if registry is not None else PromptRegistry()
        self._renderer = renderer if renderer is not None else PromptRenderer()

    def prepare(self, request: ExtractionRequest) -> PreparedRequest:
        """Return a rendered request or raise a sanitized preflight error."""

        if (
            "meeting_summary" in request.extraction.requested_modules
            and round(request.meeting.duration_seconds / 60, 2) <= 0
        ):
            raise SummaryDurationNotRepresentableError

        if any(
            module not in SUPPORTED_MODULES
            for module in request.extraction.requested_modules
        ):
            raise UnsupportedExtractionCapabilityError

        try:
            bundle = self._registry.get(APPROVED_PROMPT_VERSION)
            rendered_prompt = self._renderer.render(request, bundle)
        except (PromptRegistryError, PromptRendererError):
            raise PromptPreparationError from None

        return PreparedRequest(request=request, rendered_prompt=rendered_prompt)
