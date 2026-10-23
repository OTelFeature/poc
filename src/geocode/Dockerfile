# Selects where otelfeature's extension comes from; see the stages below.
ARG OTELFEATURE_INSTRUMENT_SOURCE=lock

# A FROM, not an inline COPY --from image, so Dependabot keeps bumping uv.
FROM ghcr.io/astral-sh/uv:0.13.5 AS uv

# The builder runs on the runtime's image: the venv only works under the
# Python minor version it was built with (its site-packages path names it).
# Keep both FROM python lines on the same tag; Dependabot bumps them together.
FROM python:3.14-slim-bookworm AS builder
COPY --from=uv /uv /usr/local/bin/uv

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

# ── otelfeature-instrument source ───────────────────────────────────
# OTELFEATURE_INSTRUMENT_SOURCE picks the stage below:
#   lock (default) - the release pinned in pyproject.toml / uv.lock (C-006)
#   git            - built from OTELFEATURE_INSTRUMENT_REF (branch, tag or
#                    commit) of the GitHub repo, for testing unreleased
#                    extension code (only when passed explicitly to
#                    make e2e). ADD of a git URL resolves the ref on every
#                    build, so a moved branch is rebuilt.
# (declared at the top: an ARG used in FROM must come before the first FROM)

FROM builder AS instrument-lock

FROM builder AS instrument-git
ARG OTELFEATURE_INSTRUMENT_REF=main
ADD https://github.com/OTelFeature/otelfeature-instrument.git#${OTELFEATURE_INSTRUMENT_REF} /tmp/otelfeature-instrument
RUN uv pip install --python /app/.venv/bin/python --reinstall-package otelfeature-instrument /tmp/otelfeature-instrument

FROM instrument-${OTELFEATURE_INSTRUMENT_SOURCE} AS deps

# ── Unit tests (make unit-test, OTelFeature/poc#75) ─────────────────
# Only built with `--target test`; the default build skips this stage, so
# the image is unchanged. Standard-library unittest: no dev dependencies.
FROM deps AS test
COPY test_fault_injection.py ./
RUN .venv/bin/python -m unittest -v test_fault_injection

FROM python:3.14-slim-bookworm AS runtime

WORKDIR /app

COPY --from=deps /app/.venv /app/.venv
COPY --from=builder /app/main.py /app/db.py /app/

ENV PATH="/app/.venv/bin:$PATH" \
    GEOCODE_PORT=8000

EXPOSE 8000

CMD ["sh", "-c", "exec otelfeature-instrument uvicorn main:app --host 0.0.0.0 --port ${GEOCODE_PORT}"]
