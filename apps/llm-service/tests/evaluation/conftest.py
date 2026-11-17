from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from evaluation.loader import DATASET_DIR, DatasetCase, load_dataset


@pytest.fixture(scope="session")
def dataset():
    return load_dataset(DATASET_DIR)


@pytest.fixture
def first_case(dataset) -> DatasetCase:
    return dataset.cases[0]


def response_payload(case: DatasetCase, actions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    request = case.request
    first_segment = request.transcript.segments[0]
    return {
        "contract_version": "1.0",
        "request_id": request.request_id,
        "status": "completed",
        "meeting_id": request.meeting.id,
        "transcript_revision_id": request.transcript.revision_id,
        "requested_modules": request.extraction.requested_modules,
        "modules": {
            "meeting_summary": {
                "title": request.meeting.title,
                "date": str(request.meeting.anchor_date),
                "duration_minutes": round(request.meeting.duration_seconds / 60, 2),
                "participants": [participant.display_name for participant in request.meeting.participants],
                "overview": "Tóm tắt nội dung cuộc họp.",
                "key_topics": [],
                "source_segment_ids": [first_segment.id],
                "needs_review": False,
                "review_reasons": [],
            },
            "action_items": actions or [],
            "decision_log": None,
            "open_issues": None,
            "follow_up_items": None,
            "timeline_events": None,
        },
        "processing": {
            "provider": "offline-fixture",
            "model_id": "synthetic-model",
            "prompt_version": "extract-v1.0",
            "evidence_prompt_version": "evidence-v1.0",
            "started_at": "2026-11-16T09:00:00Z",
            "completed_at": "2026-11-16T09:00:01Z",
            "token_usage": {"input_tokens": 12, "output_tokens": 8},
        },
    }


def action_payload(
    segment_id: str,
    *,
    action_id: str = "ACT-001",
    task: str = "Hoàn thiện API đặt lịch",
    owner: str | None = "Minh",
    raw_due_expression: str | None = None,
    due_date: str | None = None,
    priority: str | None = None,
) -> dict[str, Any]:
    segment_start = 8.832 if segment_id == "SEG-0002" else 1.0
    resolution = None
    if raw_due_expression is not None:
        resolution = {
            "status": "unresolved",
            "resolved_date": None,
            "start_date": None,
            "end_date": None,
            "needs_review": True,
            "source_segment_ids": [segment_id],
        }
    return {
        "id": action_id,
        "task": task,
        "owner": owner,
        "due_date": due_date,
        "raw_due_expression": raw_due_expression,
        "due_date_resolution": resolution,
        "priority": priority,
        "source_timestamp": f"00:00:{int(segment_start):02d}.{round((segment_start % 1) * 1000):03d}",
        "context": None,
        "source_segment_ids": [segment_id],
        "needs_review": resolution is not None,
        "review_reasons": ["temporal_unresolved"] if resolution is not None else [],
    }


@pytest.fixture
def write_json(tmp_path):
    def write(path: Path, value: Any) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    return write


@pytest.fixture
def response_payload_factory():
    return response_payload


@pytest.fixture
def action_payload_factory():
    return action_payload
