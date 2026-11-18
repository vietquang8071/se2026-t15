from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI

import asgi_client
from asgi_client import ASGITestClient


def app_with_lifecycle() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.started = True
        try:
            yield
        finally:
            app.state.stopped = True

    return FastAPI(lifespan=lifespan)


def test_lifespan_is_closed_when_http_client_enter_fails(monkeypatch: pytest.MonkeyPatch):
    app = app_with_lifecycle()

    class BrokenAsyncClient:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def __aenter__(self):
            raise RuntimeError("client startup failed")

    monkeypatch.setattr(asgi_client, "AsyncClient", BrokenAsyncClient)

    with pytest.raises(RuntimeError, match="client startup failed"):
        with ASGITestClient(app):
            pass

    assert app.state.started is True
    assert app.state.stopped is True


def test_lifespan_is_closed_when_http_client_exit_fails(monkeypatch: pytest.MonkeyPatch):
    app = app_with_lifecycle()

    class BrokenAsyncClient:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args: object):
            raise RuntimeError("client shutdown failed")

    monkeypatch.setattr(asgi_client, "AsyncClient", BrokenAsyncClient)

    with pytest.raises(RuntimeError, match="client shutdown failed"):
        with ASGITestClient(app):
            pass

    assert app.state.started is True
    assert app.state.stopped is True
