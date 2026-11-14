"""Load approved, versioned prompt templates from this application package."""

from dataclasses import dataclass
from pathlib import Path

from app.schemas.candidates import CANDIDATE_SCHEMA_VERSION

_PROMPT_FILES: dict[str, tuple[str, str]] = {
    "extract-v1.0": ("v1/system.md", "v1/summary_actions.md"),
}
_EVIDENCE_PROMPT_FILES: dict[str, tuple[str, str]] = {
    "evidence-v1.0": ("v1/evidence_system.md", "v1/evidence_verification.md"),
    "evidence-v1.1": ("v1_1/evidence_system.md", "v1_1/evidence_verification.md"),
    "evidence-v1.2": ("v1_2/evidence_system.md", "v1_2/evidence_verification.md"),
    "evidence-v1.3": ("v1_3/evidence_system.md", "v1_3/evidence_verification.md"),
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


@dataclass(frozen=True, slots=True)
class EvidencePromptBundle:
    """Immutable versioned templates for semantic evidence verification."""

    prompt_version: str
    system_template: str
    verification_template: str


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

    def get_evidence(self, prompt_version: str) -> EvidencePromptBundle:
        """Return an approved evidence-verification prompt bundle."""

        try:
            system_path, verification_path = _EVIDENCE_PROMPT_FILES[prompt_version]
        except (KeyError, TypeError) as error:
            raise PromptRegistryError("Unsupported evidence prompt version.") from error

        system_template = self._read_template(system_path)
        verification_template = self._read_template(verification_path)
        return EvidencePromptBundle(
            prompt_version=prompt_version,
            system_template=system_template,
            verification_template=verification_template,
        )

    def _read_template(self, relative_path: str) -> str:
        try:
            template = (self._template_root / relative_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise PromptRegistryError("Prompt template could not be loaded.") from error

        if not template.strip():
            raise PromptRegistryError("Prompt template is empty.")
        return template
