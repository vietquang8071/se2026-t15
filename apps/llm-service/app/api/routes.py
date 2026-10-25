"""Versioned HTTP endpoints for the LLM Service."""

from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from app.api.dependencies import get_extraction_service, get_settings, require_service_token
from app.core.config import Settings
from app.core.errors import ExtractionRequestTimeoutError
from app.schemas.errors import ErrorEnvelope
from app.schemas.request import ExtractionRequest
from app.schemas.response import ExtractionResponse
from app.services.extraction import ExtractionService

router = APIRouter()


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["ok"]
    service: Literal["llm-service"]
    contract_version: Literal["1.0"]


_ERROR_RESPONSES = {
    400: {"model": ErrorEnvelope, "description": "Yêu cầu không hợp lệ."},
    401: {"model": ErrorEnvelope, "description": "Bearer token thiếu hoặc không hợp lệ."},
    403: {"model": ErrorEnvelope, "description": "Service caller không được phép."},
    413: {"model": ErrorEnvelope, "description": "Request vượt giới hạn kích thước."},
    422: {"model": ErrorEnvelope, "description": "Transcript không có nội dung lời nói."},
    429: {"model": ErrorEnvelope, "description": "Service đang giới hạn tải."},
    500: {"model": ErrorEnvelope, "description": "Lỗi nội bộ."},
    502: {"model": ErrorEnvelope, "description": "Provider hoặc output không hợp lệ."},
    503: {"model": ErrorEnvelope, "description": "Extraction backend chưa sẵn sàng."},
    504: {"model": ErrorEnvelope, "description": "Request đã vượt quá thời gian xử lý."},
}


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    """Report process health without checking an LLM provider or database."""

    return HealthResponse(status="ok", service="llm-service", contract_version="1.0")


@router.post(
    "/v1/extractions",
    response_model=ExtractionResponse,
    responses=_ERROR_RESPONSES,
    tags=["extractions"],
    dependencies=[Depends(require_service_token)],
)
async def create_extraction(
    request: ExtractionRequest,
    http_request: Request,
    service: ExtractionService = Depends(get_extraction_service),
    settings: Settings = Depends(get_settings),
) -> ExtractionResponse:
    """Validate and delegate an extraction request to the application service."""

    http_request.state.request_id = request.request_id
    try:
        async with asyncio.timeout(settings.llm_service_request_timeout_seconds):
            return await service.extract(request)
    except TimeoutError as error:
        raise ExtractionRequestTimeoutError from error
