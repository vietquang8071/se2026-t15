"""Unit tests for synchronous extraction request preflight."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.prompts.registry import PromptBundle, PromptRegistry
from app.schemas.request import ExtractionRequest
from app.services import preflight as preflight_module
from app.services.preflight import (
    ExtractionPreflight,
    PromptPreparationError,
    UnsupportedExtractionCapabilityError,
)
from app.services.models import PreparedRequest


REQUEST_FIXTURE = (
    Path(__file__).parents[2] / "fixtures" / "requests" / "summary_actions_request.json"
)


def make_request(
    modules: tuple[str, ...] = ("meeting_summary", "action_items"),
    *,
    request_id: str = "req-preflight-01",
    transcript_segments: list[dict[str, object]] | None = None,
    participants: list[dict[str, object]] | None = None,
) -> ExtractionRequest:
    payload = json.loads(REQUEST_FIXTURE.read_text(encoding="utf-8"))
    payload["request_id"] = request_id
    payload["extraction"]["requested_modules"] = list(modules)
    if transcript_segments is not None:
        payload["transcript"]["segments"] = transcript_segments
    if participants is not None:
        payload["meeting"]["participants"] = participants
    return ExtractionRequest.model_validate(payload)


def requested_modules_in_prompt(prompt: str) -> list[str]:
    line = next(
        line
        for line in prompt.splitlines()
        if line.startswith("- `requested_modules`")
    )
    encoded = line.split(": ", maxsplit=1)[1].strip("`")
    return json.loads(encoded)


def transcript_in_prompt(prompt: str) -> list[dict[str, object]]:
    section = prompt.split("## 4. Transcript Data", maxsplit=1)[1]
    encoded = section.split("```json\n", maxsplit=1)[1].split("\n```", maxsplit=1)[0]
    return json.loads(encoded)


def test_summary_only_prepares_versioned_provider_request() -> None:
    request = make_request(("meeting_summary",))

    prepared = ExtractionPreflight().prepare(request)

    assert isinstance(prepared, PreparedRequest)
    assert prepared.request is request
    assert prepared.rendered_prompt.prompt_version == "extract-v1.0"
    assert prepared.rendered_prompt.candidate_schema_version == "candidate-v1"
    provider_request = prepared.rendered_prompt.provider_request
    assert len(provider_request.messages) == 2
    assert [message.role for message in provider_request.messages] == ["system", "user"]
    assert provider_request.structured_output_mode == "json_object"


def test_actions_only_does_not_add_summary_module() -> None:
    prepared = ExtractionPreflight().prepare(make_request(("action_items",)))

    assert prepared.request.extraction.requested_modules == ["action_items"]
    assert requested_modules_in_prompt(
        prepared.rendered_prompt.provider_request.messages[1].content
    ) == ["action_items"]


def test_summary_and_actions_preserve_requested_order() -> None:
    request = make_request(("meeting_summary", "action_items"))

    prepared = ExtractionPreflight().prepare(request)

    assert prepared.request.extraction.requested_modules == [
        "meeting_summary",
        "action_items",
    ]
    assert requested_modules_in_prompt(
        prepared.rendered_prompt.provider_request.messages[1].content
    ) == ["meeting_summary", "action_items"]


@pytest.mark.parametrize(
    "modules",
    [("decision_log",), ("action_items", "open_issues")],
    ids=["unsupported-only", "mixed-supported-and-unsupported"],
)
def test_unsupported_modules_are_rejected_before_prompt_components(
    modules: tuple[str, ...],
) -> None:
    class RegistryMustNotRun:
        def get(self, prompt_version: str) -> PromptBundle:
            raise AssertionError("Registry must not run for an unsupported module.")

    class RendererMustNotRun:
        def render(self, request: ExtractionRequest, bundle: PromptBundle):
            raise AssertionError("Renderer must not run for an unsupported module.")

    preflight = ExtractionPreflight(
        registry=RegistryMustNotRun(),
        renderer=RendererMustNotRun(),
    )

    with pytest.raises(UnsupportedExtractionCapabilityError):
        preflight.prepare(make_request(modules))


def test_approved_prompt_version_is_resolved_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RecordingRegistry(PromptRegistry):
        def __init__(self) -> None:
            super().__init__()
            self.requested_versions: list[str] = []

        def get(self, prompt_version: str) -> PromptBundle:
            self.requested_versions.append(prompt_version)
            return super().get(prompt_version)

    registry = RecordingRegistry()
    monkeypatch.setattr(preflight_module, "APPROVED_PROMPT_VERSION", "unsupported-version")
    preflight = ExtractionPreflight(registry=registry)

    with pytest.raises(PromptPreparationError) as exc_info:
        preflight.prepare(make_request(("action_items",)))

    assert registry.requested_versions == ["unsupported-version"]
    assert "unsupported-version" not in str(exc_info.value)


def test_missing_prompt_template_becomes_sanitized_preparation_error(
    tmp_path: Path,
) -> None:
    preflight = ExtractionPreflight(registry=PromptRegistry(template_root=tmp_path))

    with pytest.raises(PromptPreparationError) as exc_info:
        preflight.prepare(make_request(("meeting_summary",)))

    assert str(tmp_path) not in str(exc_info.value)
    assert "system.md" not in str(exc_info.value)


def test_invalid_rendering_becomes_sanitized_preparation_error() -> None:
    class InvalidTemplateRegistry(PromptRegistry):
        def get(self, prompt_version: str) -> PromptBundle:
            bundle = super().get(prompt_version)
            invalid_template = bundle.extraction_template.replace(
                "${meeting_context_json}", "${unexpected_placeholder}"
            )
            return replace(bundle, extraction_template=invalid_template)

    preflight = ExtractionPreflight(registry=InvalidTemplateRegistry())

    with pytest.raises(PromptPreparationError) as exc_info:
        preflight.prepare(make_request(("meeting_summary",)))

    assert "unexpected_placeholder" not in str(exc_info.value)
    assert "Transcript" not in str(exc_info.value)


def test_vietnamese_transcript_unicode_and_segment_ids_are_preserved() -> None:
    request = make_request(("meeting_summary",))

    prepared = ExtractionPreflight().prepare(request)
    rendered_transcript = transcript_in_prompt(
        prepared.rendered_prompt.provider_request.messages[1].content
    )

    assert rendered_transcript == [
        {
            "id": "seg-a1",
            "start": 12.5,
            "end": 18.2,
            "speaker_id": "speaker_1",
            "text": "Tôi sẽ gửi bản ghi chú vào thứ Sáu này.",
        },
        {
            "id": "seg-a2",
            "start": 18.3,
            "end": 22.0,
            "speaker_id": "speaker_1",
            "text": "Hôm nay chủ yếu rà lại tiến độ.",
        },
    ]
    assert rendered_transcript[0]["id"] == "seg-a1"
    assert rendered_transcript[0]["text"] == "Tôi sẽ gửi bản ghi chú vào thứ Sáu này."


def test_only_existing_speaker_mappings_are_rendered() -> None:
    segments = [
        {
            "id": "seg-mapped",
            "start": 1.0,
            "end": 2.0,
            "speaker_id": "speaker_1",
            "text": "Người nói đã được ánh xạ.",
        },
        {
            "id": "seg-unmapped",
            "start": 2.1,
            "end": 3.0,
            "speaker_id": "speaker_unknown",
            "text": "Người nói chưa được ánh xạ.",
        },
        {
            "id": "seg-null-speaker",
            "start": 3.1,
            "end": 4.0,
            "speaker_id": None,
            "text": "Không có speaker ID.",
        },
    ]
    request = make_request(("action_items",), transcript_segments=segments)

    prepared = ExtractionPreflight().prepare(request)
    user_prompt = prepared.rendered_prompt.provider_request.messages[1].content
    context = json.loads(
        user_prompt.split("## 3. Meeting Context", maxsplit=1)[1]
        .split("```json\n", maxsplit=1)[1]
        .split("\n```", maxsplit=1)[0]
    )

    assert context == {
        "participants": [{"display_name": "Alex", "speaker_ids": ["speaker_1"]}]
    }
    assert [segment["speaker_id"] for segment in transcript_in_prompt(user_prompt)] == [
        "speaker_1",
        "speaker_unknown",
        None,
    ]


def test_preflight_keeps_two_requests_isolated() -> None:
    preflight = ExtractionPreflight()
    request_a = make_request(
        ("meeting_summary",),
        request_id="req-isolation-a",
        transcript_segments=[
            {
                "id": "seg-a",
                "start": 1.0,
                "end": 2.0,
                "speaker_id": None,
                "text": "Nội dung riêng của yêu cầu A.",
            }
        ],
    )
    request_b = make_request(
        ("action_items",),
        request_id="req-isolation-b",
        transcript_segments=[
            {
                "id": "seg-b",
                "start": 1.0,
                "end": 2.0,
                "speaker_id": None,
                "text": "Nội dung riêng của yêu cầu B.",
            }
        ],
    )

    prepared_a = preflight.prepare(request_a)
    prepared_b = preflight.prepare(request_b)
    prompt_a = prepared_a.rendered_prompt.provider_request.messages[1].content
    prompt_b = prepared_b.rendered_prompt.provider_request.messages[1].content

    assert prepared_a.request is request_a
    assert prepared_b.request is request_b
    assert "Nội dung riêng của yêu cầu A." in prompt_a
    assert "Nội dung riêng của yêu cầu A." not in prompt_b
    assert "Nội dung riêng của yêu cầu B." in prompt_b
    assert "Nội dung riêng của yêu cầu B." not in prompt_a
    assert "req-isolation-a" not in prompt_b
    assert "req-isolation-b" not in prompt_a
