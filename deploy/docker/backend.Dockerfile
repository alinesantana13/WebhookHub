FROM ghcr.io/astral-sh/uv:0.11.24 AS uv
FROM python:3.13-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=uv /uv /uvx /bin/
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/src ./src
RUN uv sync --frozen --no-dev

FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/app/.venv/bin:$PATH

RUN groupadd --system webhookhub && useradd --system --gid webhookhub webhookhub
WORKDIR /app
COPY --from=builder --chown=webhookhub:webhookhub /app/.venv /app/.venv
USER webhookhub
EXPOSE 8000

CMD ["uvicorn", "webhookhub.main:app", "--host", "0.0.0.0", "--port", "8000"]
