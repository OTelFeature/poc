# Toolchain image for this repo: Python, uv and the locked dependencies of
# tests/e2e (the e2e suite and the preset checks), nothing else. Used by
# `make e2e`, `make test` and `make shell`, and by .github/workflows/e2e.yml
# and flags.yml, so local runs and CI run the same toolchain. Nothing of the
# repo is baked in: `make e2e` mounts the tests at /e2e/tests
# (compose.e2e.yaml), `make test` / `make shell` the whole repo at /workspace.
#
# Base image pinned by tag and digest; Dependabot (docker, /ci) bumps both.
FROM ghcr.io/astral-sh/uv:0.13.6-python3.14-trixie-slim@sha256:637619278855a77885a94312efa7decd8479ca6cec5f959e134cbab96582821e

ENV UV_PROJECT_ENVIRONMENT=/opt/e2e-venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /e2e
COPY tests/e2e/pyproject.toml tests/e2e/uv.lock ./
RUN uv sync --frozen --no-install-project

ENV PATH="/opt/e2e-venv/bin:$PATH"
WORKDIR /e2e/tests
ENTRYPOINT ["pytest", "-p", "no:cacheprovider"]
