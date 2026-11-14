"""Small synchronous test facade over HTTPX's ASGI transport."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response


class ASGITestClient:
    """Keep one app lifespan and event loop for a synchronous test context."""

    __test__ = False

    def __init__(self, app: FastAPI) -> None:
        self._app = app
        self._runner: asyncio.Runner | None = None
        self._lifespan: Any = None
        self._client: AsyncClient | None = None

    def __enter__(self) -> ASGITestClient:
        self._runner = asyncio.Runner()
        self._lifespan = self._app.router.lifespan_context(self._app)
        try:
            self._runner.run(self._lifespan.__aenter__())
            self._client = AsyncClient(
                transport=ASGITransport(app=self._app),
                base_url="http://testserver",
            )
            self._runner.run(self._client.__aenter__())
        except BaseException:
            self._runner.close()
            self._runner = None
            raise
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self._runner is None:
            return
        try:
            if self._client is not None:
                self._runner.run(self._client.__aexit__(exc_type, exc, traceback))
            if self._lifespan is not None:
                self._runner.run(self._lifespan.__aexit__(exc_type, exc, traceback))
        finally:
            self._runner.close()
            self._runner = None

    def request(self, method: str, url: str, **kwargs: Any) -> Response:
        if self._runner is None or self._client is None:
            raise RuntimeError("ASGITestClient must be used as a context manager.")
        return self._runner.run(self._client.request(method, url, **kwargs))

    def get(self, url: str, **kwargs: Any) -> Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> Response:
        return self.request("POST", url, **kwargs)
