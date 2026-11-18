"""Keep the automated test suite isolated from provider credentials and network."""

from __future__ import annotations

import httpx
import pytest


def _block_sync_network(*args: object, **kwargs: object) -> httpx.Response:
    raise AssertionError("Outbound HTTP is disabled in the automated test suite.")


async def _block_async_network(
    *args: object, **kwargs: object
) -> httpx.Response:
    raise AssertionError("Outbound HTTP is disabled in the automated test suite.")


@pytest.fixture(autouse=True)
def isolate_provider_environment_and_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent inherited OpenRouter credentials or accidental live HTTP calls."""

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _block_sync_network)
    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", _block_async_network
    )

