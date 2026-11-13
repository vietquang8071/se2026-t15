from pathlib import Path

import pytest

from app.prompts.registry import (
    PromptBundle,
    PromptRegistry,
    PromptRegistryError,
)
from app.schemas.candidates import CANDIDATE_SCHEMA_VERSION


PROMPT_DIR = Path(__file__).parents[3] / "app" / "prompts"


def test_loads_approved_markdown_templates_and_versions() -> None:
    bundle = PromptRegistry().get("extract-v1.0")

    assert isinstance(bundle, PromptBundle)
    assert bundle.prompt_version == "extract-v1.0"
    assert bundle.candidate_schema_version == CANDIDATE_SCHEMA_VERSION
    assert bundle.system_template == (PROMPT_DIR / "v1" / "system.md").read_text(
        encoding="utf-8"
    )
    assert bundle.extraction_template == (
        PROMPT_DIR / "v1" / "summary_actions.md"
    ).read_text(encoding="utf-8")
    assert "\u1ec7" in bundle.extraction_template


def test_loading_is_independent_of_current_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    bundle = PromptRegistry().get("extract-v1.0")

    assert bundle.system_template.startswith("#")
    assert bundle.extraction_template.startswith("#")


@pytest.mark.parametrize("prompt_version", ["unknown", "../../secret", ""])
def test_rejects_unsupported_prompt_versions(prompt_version: str) -> None:
    with pytest.raises(PromptRegistryError, match="Unsupported prompt version"):
        PromptRegistry().get(prompt_version)


def test_missing_template_has_sanitized_error(tmp_path: Path) -> None:
    with pytest.raises(PromptRegistryError, match="Prompt template could not be loaded") as exc:
        PromptRegistry(template_root=tmp_path).get("extract-v1.0")

    assert str(tmp_path) not in str(exc.value)
    assert "system.md" not in str(exc.value)


def test_empty_template_has_sanitized_error(tmp_path: Path) -> None:
    prompt_dir = tmp_path / "v1"
    prompt_dir.mkdir()
    (prompt_dir / "system.md").write_text(" \n\t", encoding="utf-8")
    (prompt_dir / "summary_actions.md").write_text("valid", encoding="utf-8")

    with pytest.raises(PromptRegistryError, match="Prompt template is empty") as exc:
        PromptRegistry(template_root=tmp_path).get("extract-v1.0")

    assert str(tmp_path) not in str(exc.value)
    assert "valid" not in str(exc.value)


def test_invalid_utf8_has_sanitized_error(tmp_path: Path) -> None:
    prompt_dir = tmp_path / "v1"
    prompt_dir.mkdir()
    (prompt_dir / "system.md").write_bytes(b"\xff")
    (prompt_dir / "summary_actions.md").write_text("valid", encoding="utf-8")

    with pytest.raises(PromptRegistryError, match="Prompt template could not be loaded") as exc:
        PromptRegistry(template_root=tmp_path).get("extract-v1.0")

    assert str(tmp_path) not in str(exc.value)
    assert "\\xff" not in str(exc.value)
