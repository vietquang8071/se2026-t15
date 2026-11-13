"""Load approved, versioned prompt templates from this application package."""

from dataclasses import dataclass
from pathlib import Path

from app.schemas.candidates import CANDIDATE_SCHEMA_VERSION

_PROMPT_FILES: dict[str, tuple[str, str]] = {
    "extract-v1.0": ("v1/system.md", "v1/summary_actions.md"),
}


class PromptRegistryError(Exception):
    """Sanitized error raised when a prompt bundle cannot be loaded."""


@dataclass(frozen=True, slots=True)
class PromptBundle:
    """Immutable prompt templates and their independent schema versions."""

    prompt_version: str
    candidate_schema_version: str
    system_template: str
    extraction_template: str


class PromptRegistry:
    """Resolve supported prompt versions without accepting arbitrary paths."""

    def __init__(self, template_root: Path | None = None) -> None:
        self._template_root = template_root or Path(__file__).parent
        self._bundles: dict[str, PromptBundle] = {}

    def get(self, prompt_version: str) -> PromptBundle:
        """Return a cached bundle for an explicitly supported prompt version."""

        try:
            system_path, extraction_path = _PROMPT_FILES[prompt_version]
        except (KeyError, TypeError) as error:
            raise PromptRegistryError("Unsupported prompt version.") from error

        cached = self._bundles.get(prompt_version)
        if cached is not None:
            return cached

        system_template = self._read_template(system_path)
        extraction_template = self._read_template(extraction_path)
        bundle = PromptBundle(
            prompt_version=prompt_version,
            candidate_schema_version=CANDIDATE_SCHEMA_VERSION,
            system_template=system_template,
            extraction_template=extraction_template,
        )
        self._bundles[prompt_version] = bundle
        return bundle

    def _read_template(self, relative_path: str) -> str:
        try:
            template = (self._template_root / relative_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise PromptRegistryError("Prompt template could not be loaded.") from error

        if not template.strip():
            raise PromptRegistryError("Prompt template is empty.")
        return template
