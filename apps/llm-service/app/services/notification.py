"""Best-effort extraction completion notification boundary."""

from __future__ import annotations

import asyncio
import logging
from typing import Literal, Protocol, TypedDict


logger = logging.getLogger(__name__)


class CompletionEvent(TypedDict):
    """Allowlisted metadata for a successfully completed extraction."""

    event_type: Literal["extraction.completed"]
    request_id: str
    meeting_id: str
    status: Literal["completed"]


class CompletionNotifier(Protocol):
    """Asynchronous adapter for dispatching a completion event."""

    async def dispatch(self, event: CompletionEvent) -> None:
        """Attempt to dispatch one completion event."""


class NoOpCompletionNotifier:
    """Runtime placeholder until a real notification sink is authorized."""

    async def dispatch(self, event: CompletionEvent) -> None:
        """Accept the event without external delivery."""

        return None


async def dispatch_completion_safely(
    notifier: CompletionNotifier,
    event: CompletionEvent,
    timeout_seconds: float,
) -> None:
    """Keep ordinary adapter failures from escaping the extraction response path."""

    try:
        async with asyncio.timeout(timeout_seconds):
            await notifier.dispatch(event)
    except TimeoutError:
        logger.warning("Completion notification timed out.")
    except Exception:
        # Do not log event metadata or exception text; either may contain sensitive data.
        logger.warning("Completion notification dispatch failed.")
