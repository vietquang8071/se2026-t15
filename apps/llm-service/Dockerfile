FROM ghcr.io/astral-sh/uv:0.11.32 AS uv

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock ./

RUN uv sync --locked --no-dev --no-install-project \
    && addgroup --system --gid 10001 llm-service \
    && adduser --system --uid 10001 --ingroup llm-service --home /home/llm-service llm-service \
    && chown -R llm-service:llm-service /app

COPY --chown=llm-service:llm-service app ./app

USER 10001:10001

EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn app.main:app --host \"${LLM_SERVICE_HOST:-0.0.0.0}\" --port \"${LLM_SERVICE_PORT:-8000}\" --log-level \"${LLM_SERVICE_LOG_LEVEL:-info}\""]
