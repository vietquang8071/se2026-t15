"""Construct the public Contract v1 response from safeguarded internal data."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import ValidationError

from app.schemas.response import (
    ActionItem,
    ExtractionModules,
    ExtractionResponse,
    KeyTopic,
    MeetingSummary,
    ProcessingMetadata,
    TokenUsage,
    validate_response_for_request,
)
from app.services.temporal_safeguards import TemporalReviewProcessor
from app.services.validation_models import (
    ResponseConstructionFailure,
    ValidationStageFailure,
    ValidatedExtraction,
)


class ResponseBuilder:
    """Build a contract-valid response only from ``ValidatedExtraction``."""

    def build(self, extraction: ValidatedExtraction) -> ExtractionResponse:
        if not isinstance(extraction, ValidatedExtraction):
            raise ResponseConstructionFailure(
                "INTERNAL_ERROR", "Response construction requires safeguarded extraction data."
            )

        try:
            extraction.validate_invariants()
            recomputed = TemporalReviewProcessor().process(extraction.evidence_verified)
            if recomputed != extraction:
                raise ValueError("Safeguarded state differs from deterministic revalidation.")
        except (ValidationStageFailure, TypeError, ValueError, KeyError, IndexError):
            raise ResponseConstructionFailure(
                "INVALID_STRUCTURED_OUTPUT",
                "Safeguarded extraction state failed final validation.",
            ) from None

        evidence = extraction.evidence_verified
        source = evidence.source_validated
        prepared = source.projected.prepared_extraction
        request = prepared.request
        requested = request.extraction.requested_modules

        if prepared.provider is None or not prepared.model_id or not prepared.prompt_version:
            raise ResponseConstructionFailure(
                "INTERNAL_ERROR", "Extraction processing metadata is incomplete."
            )
        if (
            evidence.metadata.provider != prepared.provider
            or evidence.metadata.model_id != prepared.model_id
            or not evidence.metadata.prompt_version
            or evidence.metadata.started_at is None
            or evidence.metadata.completed_at is None
            or prepared.started_at is None
        ):
            raise ResponseConstructionFailure(
                "INTERNAL_ERROR", "Verification processing metadata is incomplete."
            )

        wants_summary = "meeting_summary" in requested
        wants_actions = "action_items" in requested
        if wants_summary != (extraction.meeting_summary is not None):
            raise ResponseConstructionFailure(
                "INVALID_STRUCTURED_OUTPUT", "Verified Summary state does not match the request."
            )
        if wants_actions != (extraction.action_items is not None):
            raise ResponseConstructionFailure(
                "INVALID_STRUCTURED_OUTPUT", "Verified Action Item state does not match the request."
            )

        summary = None
        if extraction.meeting_summary is not None:
            projected_summary = source.projected.meeting_summary
            if projected_summary is None or len(extraction.topic_review_reasons) != len(
                extraction.meeting_summary.key_topics
            ):
                raise ResponseConstructionFailure(
                    "INVALID_STRUCTURED_OUTPUT", "Verified Summary metadata is inconsistent."
                )
            summary = MeetingSummary(
                title=projected_summary.title,
                date=projected_summary.date.isoformat(),
                duration_minutes=projected_summary.duration_minutes,
                participants=list(projected_summary.participants),
                overview=extraction.meeting_summary.overview,
                key_topics=[
                    KeyTopic(
                        topic=topic.topic,
                        brief_discussion=topic.brief_discussion,
                        source_segment_ids=topic.source_segment_ids,
                        needs_review=bool(reasons),
                        review_reasons=list(reasons),
                    )
                    for topic, reasons in zip(
                        extraction.meeting_summary.key_topics,
                        extraction.topic_review_reasons,
                        strict=True,
                    )
                ],
                source_segment_ids=extraction.meeting_summary.source_segment_ids,
                needs_review=bool(extraction.summary_review_reasons),
                review_reasons=list(extraction.summary_review_reasons),
            )

        action_items: list[ActionItem] | None = None
        if extraction.action_items is not None:
            if not (
                len(extraction.action_items)
                == len(extraction.action_due_dates)
                == len(extraction.action_due_resolutions)
                == len(extraction.action_review_reasons)
            ):
                raise ResponseConstructionFailure(
                    "INVALID_STRUCTURED_OUTPUT", "Action Item metadata is inconsistent."
                )

            starts = {segment.id: segment.start for segment in request.transcript.segments}
            ordered: list[tuple[float, int, object]] = []
            for original_index, action in enumerate(extraction.action_items):
                try:
                    earliest_start = min(starts[source_id] for source_id in action.source_segment_ids)
                except (KeyError, ValueError):
                    raise ResponseConstructionFailure(
                        "UNVERIFIED_EVIDENCE", "An Action Item source is not in the request transcript."
                    ) from None
                ordered.append((earliest_start, original_index, action))
            ordered.sort(key=lambda item: (item[0], item[1]))

            action_items = []
            for response_index, (earliest_start, original_index, raw_action) in enumerate(
                ordered, start=1
            ):
                action = raw_action
                source_ids = action.source_segment_ids
                if any(source_id not in starts for source_id in source_ids):
                    raise ResponseConstructionFailure(
                        "UNVERIFIED_EVIDENCE", "An Action Item source is not in the request transcript."
                    )
                action_items.append(
                    ActionItem(
                        id=f"ACT-{response_index:03d}",
                        task=action.task,
                        owner=action.owner,
                        due_date=extraction.action_due_dates[original_index],
                        raw_due_expression=action.raw_due_expression,
                        due_date_resolution=extraction.action_due_resolutions[original_index],
                        priority=action.priority,
                        source_timestamp=self._format_timestamp(earliest_start),
                        context=action.context,
                        source_segment_ids=source_ids,
                        needs_review=bool(extraction.action_review_reasons[original_index]),
                        review_reasons=list(extraction.action_review_reasons[original_index]),
                    )
                )

        extraction_usage = prepared.token_usage
        verification_usage = evidence.metadata.token_usage
        token_usage = None
        if extraction_usage is not None and verification_usage is not None:
            token_usage = TokenUsage(
                input_tokens=extraction_usage.input_tokens + verification_usage.input_tokens,
                output_tokens=extraction_usage.output_tokens + verification_usage.output_tokens,
            )

        started_at = prepared.started_at.astimezone(timezone.utc)
        completed_at = max(
            datetime.now(timezone.utc),
            started_at,
            evidence.metadata.completed_at.astimezone(timezone.utc),
        )
        processing = ProcessingMetadata(
            provider=prepared.provider,
            model_id=prepared.model_id,
            prompt_version=prepared.prompt_version,
            evidence_prompt_version=evidence.metadata.prompt_version,
            started_at=started_at.isoformat().replace("+00:00", "Z"),
            completed_at=completed_at.isoformat().replace("+00:00", "Z"),
            token_usage=token_usage,
        )
        response = ExtractionResponse(
            contract_version=request.contract_version,
            request_id=request.request_id,
            status="completed",
            meeting_id=request.meeting.id,
            transcript_revision_id=request.transcript.revision_id,
            requested_modules=list(requested),
            modules=ExtractionModules(
                meeting_summary=summary,
                action_items=action_items,
                decision_log=None,
                open_issues=None,
                follow_up_items=None,
                timeline_events=None,
            ),
            processing=processing,
        )
        try:
            return validate_response_for_request(request, response)
        except (ValidationError, ValueError):
            raise ResponseConstructionFailure(
                "INVALID_STRUCTURED_OUTPUT", "Verified output does not satisfy Contract v1."
            ) from None

    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        milliseconds = round(seconds * 1000)
        hours, remainder = divmod(milliseconds, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        whole_seconds, millis = divmod(remainder, 1000)
        return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{millis:03d}"
