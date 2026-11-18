"""Dataset, evidence and saved-response validation for offline evaluation."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import ValidationError

from app.schemas.request import ExtractionRequest
from app.schemas.response import ExtractionResponse, validate_response_for_request


@dataclass(frozen=True)
class ValidationIssue:
    case_id: str
    code: str
    message: str
    path: str | None = None


@dataclass(frozen=True)
class ResponseValidation:
    json_valid: bool
    schema_valid: bool
    relationship_valid: bool | None
    completed: bool
    semantic_evaluation_available: bool
    structural_grounding_valid: bool | None
    semantic_grounding_status: str
    response: ExtractionResponse | None
    failure_category: str | None
    errors: tuple[str, ...] = ()


def validate_audio_transcript(audio: Any, *, case_id: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    def issue(path: str, message: str) -> None:
        issues.append(ValidationIssue(case_id, "audio_invalid", message, path))

    if not isinstance(audio, dict):
        issue("audio", "Audio transcript must be a JSON object.")
        return issues
    if audio.get("schema_version") != 2:
        issue("schema_version", "Audio transcript must use schema_version 2.")
    expected_audio_fields = {"schema_version", "audio_id", "language", "timeline", "source_audio_start_sec", "duration_sec", "text", "speakers", "segments", "warnings", "models"}
    if set(audio) != expected_audio_fields:
        issue("audio", f"Audio Transcript v2 fields must be exactly {sorted(expected_audio_fields)}.")
    if audio.get("language") != "vi":
        issue("language", "Audio Transcript v2 language must be 'vi'.")
    if audio.get("timeline") != "source":
        issue("timeline", "Audio Transcript v2 timeline must be 'source'.")
    for field in ("audio_id", "language", "text"):
        if not isinstance(audio.get(field), str) or not audio[field].strip():
            issue(field, f"{field} must be a non-empty string.")
    if not isinstance(audio.get("source_audio_start_sec"), (int, float)) or isinstance(audio.get("source_audio_start_sec"), bool) or not math.isfinite(audio["source_audio_start_sec"]) or audio["source_audio_start_sec"] < 0:
        issue("source_audio_start_sec", "source_audio_start_sec must be a finite non-negative number.")
    duration = audio.get("duration_sec")
    if not isinstance(duration, (int, float)) or isinstance(duration, bool) or not math.isfinite(duration) or duration <= 0:
        issue("duration_sec", "duration_sec must be a finite positive number.")
        duration = None
    offset = audio.get("source_audio_start_sec")
    if duration is not None and isinstance(offset, (int, float)) and offset > duration:
        issue("source_audio_start_sec", "Source timeline offset must not exceed duration_sec.")
    if not isinstance(audio.get("segments"), list):
        issue("segments", "segments must be an array.")
        segments: list[Any] = []
    else:
        segments = audio["segments"]
    seen: set[str] = set()
    previous_start = -math.inf
    used_speakers: list[str] = []
    expected_keys = {"id", "start", "end", "speaker", "text"}
    for index, segment in enumerate(segments):
        path = f"segments[{index}]"
        if not isinstance(segment, dict):
            issue(path, "Audio segment must be an object.")
            continue
        if set(segment) != expected_keys:
            issue(path, f"Audio v2 segment fields must be exactly {sorted(expected_keys)}.")
        segment_id = segment.get("id")
        if not isinstance(segment_id, str) or not segment_id.strip():
            issue(f"{path}.id", "Segment id must be a non-empty string.")
        elif segment_id in seen:
            issue(f"{path}.id", f"Duplicate segment ID {segment_id!r}.")
        else:
            seen.add(segment_id)
        start, end = segment.get("start"), segment.get("end")
        valid_start = isinstance(start, (int, float)) and not isinstance(start, bool) and math.isfinite(start)
        valid_end = isinstance(end, (int, float)) and not isinstance(end, bool) and math.isfinite(end)
        if not valid_start or start < 0:
            issue(f"{path}.start", "Segment start must be finite and non-negative.")
        if not valid_end or end < 0 or (valid_start and valid_end and end < start):
            issue(f"{path}.end", "Segment end must be finite and greater than or equal to start.")
        if valid_start and start < previous_start:
            issue(f"{path}.start", "Audio segments must preserve nondecreasing source-time order.")
        if valid_start:
            previous_start = start
        if valid_end and duration is not None and end > duration + 0.05:
            issue(f"{path}.end", "Segment end exceeds source audio duration by more than 0.05 seconds.")
        speaker = segment.get("speaker")
        if not isinstance(speaker, str) or not speaker.strip():
            issue(f"{path}.speaker", "Segment speaker must be a non-empty string.")
        elif speaker not in used_speakers:
            used_speakers.append(speaker)
        if not isinstance(segment.get("text"), str):
            issue(f"{path}.text", "Segment text must be a string.")
    speakers = audio.get("speakers")
    if not isinstance(speakers, list):
        issue("speakers", "speakers must be an array.")
    else:
        speaker_ids = [
            speaker.get("id")
            for speaker in speakers
            if isinstance(speaker, dict) and isinstance(speaker.get("id"), str)
        ]
        if len(speaker_ids) != len(set(speaker_ids)):
            issue("speakers", "Audio speaker IDs must be unique.")
        if speaker_ids != used_speakers:
            issue("speakers", "Audio speaker list must contain used segment speakers in first-seen order.")
        for index, speaker in enumerate(speakers):
            if not isinstance(speaker, dict) or set(speaker) != {"id", "name"} or not all(isinstance(speaker.get(key), str) and speaker[key].strip() for key in ("id", "name")):
                issue(f"speakers[{index}]", "Each speaker needs non-empty id and name strings.")
    warnings = audio.get("warnings")
    if not isinstance(warnings, list) or any(not isinstance(item, str) for item in warnings):
        issue("warnings", "warnings must be an array of strings.")
    models = audio.get("models")
    if not isinstance(models, dict) or set(models) != {"transcription_and_diarization"} or not isinstance(models.get("transcription_and_diarization"), str) or not models["transcription_and_diarization"].strip():
        issue("models", "Audio Transcript v2 models must include transcription_and_diarization.")
    expected_text = "\n".join(
        segment["text"].strip()
        for segment in segments
        if isinstance(segment, dict) and isinstance(segment.get("text"), str) and segment["text"].strip()
    )
    if isinstance(audio.get("text"), str) and audio["text"] != expected_text:
        issue("text", "Transcript text must equal non-empty trimmed segment texts joined with newlines.")
    return issues


def validate_audio_request_consistency(
    audio: dict[str, Any], request: ExtractionRequest, *, case_id: str
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    def add(path: str, message: str) -> None:
        issues.append(ValidationIssue(case_id, "audio_request_mismatch", message, path))

    if not isinstance(audio, dict):
        add("audio", "Audio payload must be an object before consistency validation.")
        return issues
    audio_segments = audio.get("segments")
    if not isinstance(audio_segments, list):
        add("segments", "Audio segments must be a structurally valid array before consistency validation.")
        return issues
    if any(not isinstance(segment, dict) for segment in audio_segments):
        add("segments", "Every Audio segment must be a structurally valid object before consistency validation.")
        return issues
    duration = audio.get("duration_sec")
    if not isinstance(duration, (int, float)) or isinstance(duration, bool) or not math.isfinite(duration) or duration <= 0:
        add("duration_sec", "Audio duration_sec must be a finite positive number before consistency validation.")
        return issues
    offset = audio.get("source_audio_start_sec")
    if not isinstance(offset, (int, float)) or isinstance(offset, bool) or not math.isfinite(offset) or offset < 0:
        add("source_audio_start_sec", "Audio source offset must be a finite non-negative number before consistency validation.")
        return issues
    required_segment_fields = {"id", "start", "end", "speaker", "text"}
    for index, segment in enumerate(audio_segments):
        start, end = segment.get("start"), segment.get("end")
        valid_start = isinstance(start, (int, float)) and not isinstance(start, bool) and math.isfinite(start)
        valid_end = isinstance(end, (int, float)) and not isinstance(end, bool) and math.isfinite(end)
        if (
            set(segment) != required_segment_fields
            or not isinstance(segment.get("id"), str)
            or not segment["id"].strip()
            or not valid_start
            or not valid_end
            or start < 0
            or end < start
            or not isinstance(segment.get("speaker"), str)
            or not segment["speaker"].strip()
            or not isinstance(segment.get("text"), str)
        ):
            add(f"segments[{index}]", "Audio segment must pass structural validation before consistency checks.")
            return issues
    llm_segments = request.transcript.segments
    if len(audio_segments) != len(llm_segments):
        add("transcript.segments", f"Audio has {len(audio_segments)} segments but LLM request has {len(llm_segments)}.")
    for index, (a, q) in enumerate(zip(audio_segments, llm_segments)):
        for audio_field, request_field in (("id", "id"), ("text", "text"), ("start", "start"), ("end", "end")):
            if a.get(audio_field) != getattr(q, request_field):
                add(f"transcript.segments[{index}].{request_field}", f"Audio {audio_field} is not preserved in the LLM request.")
        speaker = a.get("speaker")
        expected_speaker = None if speaker == "unknown" else speaker
        if q.speaker_id != expected_speaker:
            add(f"transcript.segments[{index}].speaker_id", f"Audio speaker {speaker!r} must map to LLM speaker_id {expected_speaker!r}.")
    if duration != request.meeting.duration_seconds:
        add("meeting.duration_seconds", "LLM duration_seconds must equal Audio Transcript v2 duration_sec on the source timeline.")
    if audio.get("timeline") == "source" and audio.get("source_audio_start_sec") != 0:
        # A source timeline may start after zero when representing a source window; request timestamps still remain absolute.
        for index, (a, q) in enumerate(zip(audio_segments, llm_segments)):
            if a["start"] < offset or q.start != a["start"]:
                add(f"transcript.segments[{index}].start", "Source timeline timestamps must be passed through unchanged; do not add an offset twice.")
    return issues


def validate_gold(gold: Any, request: ExtractionRequest, *, case_id: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    def add(path: str, message: str) -> None:
        issues.append(ValidationIssue(case_id, "gold_invalid", message, path))

    if not isinstance(gold, dict):
        add("gold", "Gold label must be an object.")
        return issues
    if gold.get("gold_schema_version") != "llm03.7-gold-v1":
        add("gold_schema_version", "Expected gold schema llm03.7-gold-v1.")
    if gold.get("case_id") != case_id:
        add("case_id", f"Gold case_id must equal {case_id!r}.")
    if gold.get("evaluation_scope") != ["meeting_summary", "action_items"]:
        add("evaluation_scope", "LLM-03 gold evaluation_scope must be meeting_summary and action_items.")
    known_ids = {segment.id for segment in request.transcript.segments}

    def source_ids(value: Any, path: str, *, required: bool = True) -> list[str]:
        if not isinstance(value, list) or (required and not value) or any(not isinstance(item, str) for item in value):
            add(path, "Source references must be a non-empty string array." if required else "Evidence references must be a string array.")
            return []
        if len(value) != len(set(value)):
            add(path, "Source IDs must be unique within each list.")
        for source_id in value:
            if source_id not in known_ids:
                add(path, f"Gold references unknown source segment ID {source_id!r}.")
        return value

    summary = gold.get("meeting_summary")
    if not isinstance(summary, dict):
        add("meeting_summary", "meeting_summary must be an object.")
    else:
        for field in ("reference_overview",):
            if not isinstance(summary.get(field), str) or not summary[field].strip():
                add(f"meeting_summary.{field}", f"{field} must be non-empty text.")
        source_ids(summary.get("source_segment_ids"), "meeting_summary.source_segment_ids")
        if not isinstance(summary.get("key_topics"), list):
            add("meeting_summary.key_topics", "key_topics must be an array.")
        else:
            for index, topic in enumerate(summary["key_topics"]):
                path = f"meeting_summary.key_topics[{index}]"
                if not isinstance(topic, dict) or not all(isinstance(topic.get(key), str) and topic[key].strip() for key in ("topic", "brief_discussion")):
                    add(path, "Each key topic needs non-empty topic and brief_discussion strings.")
                    continue
                source_ids(topic.get("source_segment_ids"), f"{path}.source_segment_ids")
        if not isinstance(summary.get("forbidden_claims"), list) or any(not isinstance(item, str) or not item.strip() for item in summary.get("forbidden_claims", [])):
            add("meeting_summary.forbidden_claims", "forbidden_claims must be an array of non-empty strings.")
    actions = gold.get("action_items")
    if not isinstance(actions, list):
        add("action_items", "action_items must be an array.")
        return issues
    ids: list[str] = []
    for index, action in enumerate(actions):
        path = f"action_items[{index}]"
        if not isinstance(action, dict):
            add(path, "Gold action must be an object.")
            continue
        gold_id = action.get("gold_id")
        if not isinstance(gold_id, str) or not gold_id.strip():
            add(f"{path}.gold_id", "gold_id must be a non-empty string.")
        else:
            ids.append(gold_id)
        if not isinstance(action.get("task"), str) or not action["task"].strip():
            add(f"{path}.task", "Gold task must be non-empty text.")
        if action.get("owner") is not None and (not isinstance(action.get("owner"), str) or not action["owner"].strip()):
            add(f"{path}.owner", "Owner must be a non-empty string or null.")
        if action.get("priority") not in (None, "High", "Medium", "Low"):
            add(f"{path}.priority", "Priority must be High, Medium, Low or null.")
        raw_due, due_date = action.get("raw_due_expression"), action.get("due_date")
        status = action.get("due_date_resolution_status")
        if raw_due is not None and (not isinstance(raw_due, str) or not raw_due.strip()):
            add(f"{path}.raw_due_expression", "Raw due expression must be non-empty text or null.")
        if due_date is not None:
            try:
                parsed = date.fromisoformat(due_date) if isinstance(due_date, str) else None
                if parsed is None or parsed.isoformat() != due_date:
                    raise ValueError
            except ValueError:
                add(f"{path}.due_date", "Due date must be a valid ISO YYYY-MM-DD date or null.")
        if status not in ("exact_date", "date_range", "unresolved"):
            add(f"{path}.due_date_resolution_status", "Temporal status must be exact_date, date_range or unresolved.")
        elif status == "exact_date" and (raw_due is None or due_date is None):
            add(path, "exact_date requires a raw due expression and resolved due_date.")
        elif status in ("date_range", "unresolved") and due_date is not None:
            add(path, f"{status} deadline must not contain a resolved due_date.")
        if raw_due is None and (due_date is not None or status != "unresolved"):
            add(path, "A gold action without a raw deadline must have null date and unresolved status.")
        if raw_due is not None and not action.get("deadline_evidence_segment_ids"):
            add(f"{path}.deadline_evidence_segment_ids", "A stated deadline requires source evidence.")
        if raw_due is None and action.get("deadline_evidence_segment_ids"):
            add(f"{path}.deadline_evidence_segment_ids", "A null deadline must not carry deadline evidence.")
        if action.get("context") is not None and (not isinstance(action.get("context"), str) or not action["context"].strip()):
            add(f"{path}.context", "Context must be non-empty text or null.")
        if not isinstance(action.get("notes"), str):
            add(f"{path}.notes", "Gold notes must be a string.")
        action_source_ids = source_ids(action.get("source_segment_ids"), f"{path}.source_segment_ids")
        for field in ("owner_evidence_segment_ids", "deadline_evidence_segment_ids"):
            evidence = source_ids(action.get(field), f"{path}.{field}", required=False)
            if field == "owner_evidence_segment_ids" and action.get("owner") is None and evidence:
                # An unassigned owner can cite correction/uncertainty evidence; do not reject it.
                pass
            if not set(evidence).issubset(set(action_source_ids)):
                add(f"{path}.{field}", "Attribute evidence IDs must be a subset of action source_segment_ids.")
    if len(ids) != len(set(ids)):
        add("action_items", "Gold action IDs must be unique.")
    if not isinstance(gold.get("evaluation_notes"), list) or any(not isinstance(note, str) for note in gold.get("evaluation_notes", [])):
        add("evaluation_notes", "evaluation_notes must be an array of strings.")
    policy = gold.get("gold_policy")
    if not isinstance(policy, dict) or any(not isinstance(policy.get(field), bool) for field in ("semantic_paraphrases_allowed", "source_ids_are_evidence_not_just_syntactic_checks", "candidate_exact_text_match_required")):
        add("gold_policy", "gold_policy must include all three boolean policy fields.")
    return issues


def validate_response(request: ExtractionRequest, value: Any) -> ResponseValidation:
    if isinstance(value, (str, bytes, bytearray)):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as error:
            return ResponseValidation(False, False, None, False, False, None, "pending_review", None, "invalid_json", (str(error),))
    if not isinstance(value, dict):
        return ResponseValidation(True, False, None, False, False, None, "pending_review", None, "schema_invalid", ("Response JSON must be an object.",))
    try:
        response = ExtractionResponse.model_validate(value)
    except ValidationError as error:
        messages = tuple(f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in error.errors())
        return ResponseValidation(True, False, None, False, False, None, "pending_review", None, "schema_invalid", messages)
    try:
        validate_response_for_request(request, response)
        validate_output_timestamps(request, response)
    except (ValueError, TypeError) as error:
        return ResponseValidation(True, True, False, response.status == "completed", False, False, "pending_review", response, "relationship_invalid", (str(error),))
    completed = response.status == "completed"
    return ResponseValidation(True, True, True, completed, completed, True, "pending_review", response, None if completed else "not_completed", ())


def validate_output_timestamps(request: ExtractionRequest, response: ExtractionResponse) -> None:
    """Check timestamps derived from cited source starts, which the model schema cannot infer."""
    starts = {segment.id: segment.start for segment in request.transcript.segments}
    for module_name in ("action_items", "decision_log", "open_issues", "follow_up_items", "timeline_events"):
        artifacts = getattr(response.modules, module_name)
        if artifacts is None:
            continue
        previous_start: float | None = None
        for item in artifacts:
            first_start = min(starts[source_id] for source_id in item.source_segment_ids)
            expected = _format_source_timestamp(first_start)
            if item.source_timestamp != expected:
                raise ValueError(
                    f"{module_name} {item.id} source_timestamp must equal cited source start {expected}."
                )
            if module_name != "timeline_events" and previous_start is not None and first_start < previous_start:
                raise ValueError(f"{module_name} artifacts must be ordered by source_timestamp.")
            previous_start = first_start


def _format_source_timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{millis:03d}"


def normalize_exact_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", value).strip().casefold()
    return normalized.rstrip(" .,!?:;。！？、")


def normalize_raw_expression(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip().strip(".,!?:;。！？、 \t\r\n")

