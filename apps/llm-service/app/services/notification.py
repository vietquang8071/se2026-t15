"""Best-effort extraction completion notification boundary."""

from __future__ import annotations

from typing import Literal, Protocol, TypedDict


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
