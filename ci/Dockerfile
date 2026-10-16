# Runner image for the end-to-end suite (tests/e2e). Used by `make e2e` and by
# .github/workflows/e2e.yml, so local runs and CI run the same toolchain:
# Python, uv and the locked test dependencies, nothing else. The tests
# themselves are mounted at /e2e/tests at run time (compose.e2e.yaml).
FROM ghcr.io/astral-sh/uv:0.13.1-python3.14-trixie-slim

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
