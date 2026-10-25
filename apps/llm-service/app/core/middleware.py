"""HTTP boundary checks that must run before FastAPI parses extraction JSON."""

from __future__ import annotations

import logging
from typing import Any

from app.core.errors import error_response, valid_request_id

logger = logging.getLogger(__name__)


class SafeUnhandledErrorMiddleware:
    """Convert unexpected exceptions to a safe envelope without re-raising."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def track_response(message: dict[str, Any]) -> None:
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, track_response)
        except Exception:
            # Exception text and traceback can contain transcript or secret data.
            logger.error("Unhandled internal error in LLM Service request.")
            if response_started:
                return
            state = scope.get("state", {})
            request_id = valid_request_id(state.get("request_id")) if isinstance(state, dict) else None
            await error_response(
                "INTERNAL_ERROR",
                "Đã xảy ra lỗi nội bộ.",
                request_id=request_id,
            )(scope, receive, track_response)


class ExtractionRequestBoundaryMiddleware:
    """Enforce JSON content type and a bounded extraction request body."""

    def __init__(self, app: Any, *, max_request_bytes: int) -> None:
        self.app = app
        self.max_request_bytes = max_request_bytes

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if not (
            scope.get("type") == "http"
            and scope.get("method") == "POST"
            and scope.get("path") == "/v1/extractions"
        ):
            await self.app(scope, receive, send)
            return

        headers = scope.get("headers", [])
        content_types = [value for name, value in headers if name.lower() == b"content-type"]
        media_type = content_types[-1].decode("latin-1").split(";", 1)[0].strip().lower() if content_types else ""
        if media_type != "application/json":
            await error_response(
                "VALIDATION_ERROR",
                "Yêu cầu phải sử dụng Content-Type application/json.",
            )(scope, receive, send)
            return

        content_lengths = [value for name, value in headers if name.lower() == b"content-length"]
        for raw_length in content_lengths:
            try:
                declared_length = int(raw_length)
            except (TypeError, ValueError):
                continue
            if declared_length > self.max_request_bytes:
                await error_response(
                    "PAYLOAD_TOO_LARGE",
                    "Kích thước request vượt giới hạn cho phép.",
                )(scope, receive, send)
                return

        chunks: list[bytes] = []
        received_bytes = 0
        while True:
            message = await receive()
            if message.get("type") == "http.disconnect":
                return
            if message.get("type") != "http.request":
                continue

            chunk = message.get("body", b"")
            received_bytes += len(chunk)
            if received_bytes > self.max_request_bytes:
                await error_response(
                    "PAYLOAD_TOO_LARGE",
                    "Kích thước request vượt giới hạn cho phép.",
                )(scope, receive, send)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break

        request_body = b"".join(chunks)
        body_sent = False

        async def replay_bounded_body() -> dict[str, Any]:
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": request_body, "more_body": False}
            return {"type": "http.disconnect"}

        await self.app(scope, replay_bounded_body, send)
