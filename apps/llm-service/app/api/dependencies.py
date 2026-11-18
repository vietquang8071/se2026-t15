"""FastAPI dependencies for settings, authentication, and extraction."""

from __future__ import annotations

import hmac

from fastapi import Depends, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings
from app.core.errors import AuthenticationRequiredError
from app.services.extraction import ExtractionService
from app.services.notification import CompletionNotifier

bearer_scheme = HTTPBearer(auto_error=False)


async def get_settings(request: Request) -> Settings:
    return request.app.state.settings


async def get_extraction_service(request: Request) -> ExtractionService:
    return request.app.state.extraction_service


async def get_completion_notifier(request: Request) -> CompletionNotifier:
    return request.app.state.completion_notifier


async def require_service_token(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> None:
    expected_token = settings.llm_service_token
    supplied_token = credentials.credentials if credentials is not None else None
    if expected_token is None or supplied_token is None:
        raise AuthenticationRequiredError
    expected_value = expected_token.get_secret_value()
    if not hmac.compare_digest(
        supplied_token.encode("utf-8"),
        expected_value.encode("utf-8"),
    ):
        raise AuthenticationRequiredError
