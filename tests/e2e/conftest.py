"""Fixtures for the e2e suite. Runs inside the runner container
(ci/Dockerfile) on the e2e compose network; see README.md."""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import httpx
import pytest

from flags import Flags
from spans import STEP_HEADER, SpanLog, wait_until

GEOCODE_URL = os.environ.get("GEOCODE_URL", "http://geocode:8000")
WEATHER_URL = os.environ.get("WEATHER_URL", "http://weather:8001")
URLS = {"geocode": GEOCODE_URL, "weather": WEATHER_URL}

# How long an absence has to hold before it counts. Spans are exported
# within ~200 ms (100 ms batch delay + 100 ms file flush), so this is
# several export cycles. Proving "nothing arrived" needs *some* window;
# it is the only deliberate wait in the suite.
QUIET_SECONDS = 1.5


class Step:
    """One test step: every request carries the same x-e2e-step header, so
    the step's traces can be told apart from anything else in the span file."""

    def __init__(self, spans: SpanLog):
        self.id = uuid.uuid4().hex
        self.spans = spans
        self.mark = spans.mark()
        self.http = httpx.Client(timeout=10.0, headers={STEP_HEADER: self.id})

    def geocode(self, city: str, country: str) -> httpx.Response:
        return self.http.post(f"{GEOCODE_URL}/geocode", json={"city": city, "country": country})

    def weather(self, city: str, country: str) -> httpx.Response:
        return self.http.post(f"{WEATHER_URL}/weather", json={"city": city, "country": country})

    def health(self, base_url: str) -> httpx.Response:
        return self.http.get(f"{base_url}/health")

    def remark(self) -> int:
        """Start a new absence window: call after a flag flip *and* a probe
        showing it took effect, so spans still queued from before the flip
        (100 ms batches) don't leak in. Docker's healthchecks keep calling
        /health every 2 s in every state: filter by service and path."""
        self.mark = self.spans.mark()
        return self.mark

    def since_mark(self) -> list:
        return self.spans.since(self.mark)

    def wait_tracing(self, service: str, traced: bool, path: str = "/health",
                     timeout: float = 10.0) -> None:
        """Barrier after a flag flip: wait until requests to `service` are
        (traced=True) or are no longer (traced=False) traced.

        Sends a probe request with its own header value on every poll.
        traced=True: done as soon as one probe shows up. traced=False: done
        once the last three probes are older than QUIET_SECONDS and none of
        them showed up.
        """
        probes: list[tuple[str, float]] = []

        def check() -> str | None:
            probe = f"probe-{uuid.uuid4().hex}"
            self.http.get(f"{URLS[service]}{path}", headers={STEP_HEADER: probe})
            probes.append((probe, time.monotonic()))
            self.spans.refresh()
            seen = {s.step for s in self.spans.spans if s.kind == "server" and s.step}
            if traced:
                return None if any(p in seen for p, _ in probes) else f"{service}: no probe traced yet"
            now = time.monotonic()
            settled = [p for p, sent in probes if now - sent >= QUIET_SECONDS]
            if len(settled) < 3:
                return f"{service}: waiting for probes to settle"
            if any(p in seen for p in settled[-3:]):
                return f"{service}: requests still traced"
            return None

        wait_until(check, timeout=timeout, interval=0.2)

    def quiet(self, where) -> list:
        """Spans matching `where` since the mark, after waiting QUIET_SECONDS."""
        time.sleep(QUIET_SECONDS)
        return [s for s in self.since_mark() if where(s)]

    def traces(self) -> dict[str, list]:
        """This step's traces so far, by trace id."""
        by_trace: dict[str, list] = {}
        for span in self.spans.for_step(self.id):
            by_trace.setdefault(span.trace_id, []).append(span)
        return by_trace


@pytest.fixture(scope="session")
def spans() -> SpanLog:
    return SpanLog(Path(os.environ.get("E2E_SPANS_FILE", "/out/spans.jsonl")))


@pytest.fixture(scope="session")
def flags() -> Flags:
    return Flags(
        flags_file=Path(os.environ.get("E2E_FLAGS_FILE", "/flags/flagd.json")),
        presets_dir=Path(os.environ.get("E2E_PRESETS_DIR", "/presets")),
        ofrep_url=os.environ.get("FLAGD_OFREP_URL", "http://flagd:8016"),
    )


@pytest.fixture(scope="session", autouse=True)
def stack_ready():
    """compose `up --wait` already waited for the healthchecks; this only
    guards against running the suite against a half-started stack."""
    def problem():
        for url in (GEOCODE_URL, WEATHER_URL):
            try:
                if httpx.get(f"{url}/health", timeout=2.0).status_code != 200:
                    return f"{url} not healthy"
            except httpx.HTTPError as e:
                return f"{url}: {e!r}"
        return None
    wait_until(problem, timeout=60.0, interval=0.5)


@pytest.fixture
def baseline(flags):
    """Every test starts and ends on the baseline preset."""
    flags.apply("00-baseline")
    yield
    flags.apply("00-baseline")


@pytest.fixture
def step(spans, baseline):
    s = Step(spans)
    yield s
    s.http.close()
