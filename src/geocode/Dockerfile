FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

# git is needed to fetch the otelfeature-instrument dependency (a git source,
# not yet published to a package index) - see pyproject.toml's [tool.uv.sources].
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

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

CMD ["sh", "-c", "exec otelfeature-instrument uvicorn main:app --host 0.0.0.0 --port ${GEOCODE_PORT}"]
