"""FastAPI application factory for the standalone LLM Service."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError, ResponseValidationError

from app.api.routes import router
from app.core.config import Settings
from app.core.errors import (
    AuthenticationRequiredError,
    ExtractionRequestTimeoutError,
    ExtractionUnavailableError,
    authentication_required_handler,
    extraction_timeout_handler,
    extraction_unavailable_handler,
    request_validation_handler,
    response_validation_handler,
)
from app.core.middleware import (
    ExtractionRequestBoundaryMiddleware,
    SafeUnhandledErrorMiddleware,
)
from app.services.extraction import ExtractionService, UnconfiguredExtractionService


def create_app(
    *,
    settings: Settings | None = None,
    extraction_service: ExtractionService | None = None,
) -> FastAPI:
    """Create an isolated ASGI application with injectable runtime dependencies."""

    runtime_settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if runtime_settings.llm_service_token is None:
            raise RuntimeError("LLM_SERVICE_TOKEN must be configured before startup.")
        yield

    application = FastAPI(
        title="Meeting Minutes Assistant LLM Service",
        version="1.0.0",
        openapi_url="/openapi.json",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    application.state.settings = runtime_settings
    application.state.extraction_service = (
        extraction_service
        if extraction_service is not None
        else UnconfiguredExtractionService()
    )
    application.add_middleware(
        ExtractionRequestBoundaryMiddleware,
        max_request_bytes=runtime_settings.llm_service_max_request_bytes,
    )
    application.add_middleware(SafeUnhandledErrorMiddleware)
    application.add_exception_handler(RequestValidationError, request_validation_handler)
    application.add_exception_handler(AuthenticationRequiredError, authentication_required_handler)
    application.add_exception_handler(ExtractionUnavailableError, extraction_unavailable_handler)
    application.add_exception_handler(ExtractionRequestTimeoutError, extraction_timeout_handler)
    application.add_exception_handler(ResponseValidationError, response_validation_handler)
    application.include_router(router)
    return application


app = create_app()
