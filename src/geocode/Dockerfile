FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-dev

COPY main.py db.py ./
RUN uv sync --locked --no-dev

FROM python:3.14-slim-bookworm AS runtime

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/main.py /app/db.py /app/

ENV PATH="/app/.venv/bin:$PATH" \
    GEOCODE_PORT=8000

EXPOSE 8000

CMD opentelemetry-instrument uvicorn main:app --host 0.0.0.0 --port ${GEOCODE_PORT}
