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
from spans import STEP_HEADER, MetricLog, SpanLog, describe, wait_until

GEOCODE_URL = os.environ.get("GEOCODE_URL", "http://geocode:8000")
WEATHER_URL = os.environ.get("WEATHER_URL", "http://weather:8001")
URLS = {
    "geocode": GEOCODE_URL,
    "weather": WEATHER_URL,
    # Staging twins (deployment.environment.name=staging), TC-004.
    "geocode-staging": os.environ.get("GEOCODE_STAGING_URL", "http://geocode-staging:8000"),
    "weather-staging": os.environ.get("WEATHER_STAGING_URL", "http://weather-staging:8001"),
}

# How long an absence has to hold before it counts. Spans are exported
# within ~200 ms (100 ms batch delay + 100 ms file flush), so this is
# several export cycles; 2 s also matches TC-001's "after 2 s". Proving
# "nothing arrived" needs *some* window; it is the only deliberate wait in
# the suite. E2E_QUIET_SECONDS raises it for slow runners.
QUIET_SECONDS = float(os.environ.get("E2E_QUIET_SECONDS", "2.0"))

# Spec NFR: a flag flip is visible within 2 s. The barrier allows this much
# from the moment flagd serves the new flags (headroom for CI), and tests
# assert it, so slow propagation is a failure, not just a longer wait.
FLIP_BUDGET_SECONDS = float(os.environ.get("E2E_FLIP_BUDGET_SECONDS", "5.0"))


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
                     timeout: float | None = None, send=None) -> float:
        """Barrier after a flag flip: wait until requests to `service` are
        (traced=True) or are no longer (traced=False) traced.

        Sends a probe request with its own header value on every poll.
        traced=True: done as soon as one probe shows up. traced=False: done
        once the last three probes are older than QUIET_SECONDS and none of
        them showed up.

        Returns the flip latency: when the first probe with the new
        behaviour was sent, counted from the call. The timeout defaults to
        FLIP_BUDGET_SECONDS (plus the settling time for traced=False).

        `send(headers)` replaces the default probe (GET `path` on `service`),
        for example to send several requests per poll.
        """
        if timeout is None:
            timeout = FLIP_BUDGET_SECONDS + (0 if traced else QUIET_SECONDS + 1.0)
        start = time.monotonic()
        probes: list[tuple[str, float]] = []
        latency: list[float] = []

        def check() -> str | None:
            probe = f"probe-{uuid.uuid4().hex}"
            if send is not None:
                send({STEP_HEADER: probe})
            else:
                r = self.http.get(f"{URLS[service]}{path}", headers={STEP_HEADER: probe})
                assert r.status_code == 200, f"probe to {service}{path}: HTTP {r.status_code}"
            probes.append((probe, time.monotonic()))
            self.spans.refresh()
            seen = {s.step for s in self.spans.spans if s.kind == "server" and s.step}
            if traced:
                hit = next((sent for p, sent in probes if p in seen), None)
                if hit is None:
                    return f"{service}: no probe traced yet"
                latency.append(hit - start)
                return None
            now = time.monotonic()
            settled = [(p, sent) for p, sent in probes if now - sent >= QUIET_SECONDS]
            if len(settled) < 3:
                return f"{service}: waiting for probes to settle"
            if any(p in seen for p, _ in settled[-3:]):
                return f"{service}: requests still traced"
            # The first probe of the untraced run that ends now.
            traced_at = [sent for p, sent in settled if p in seen]
            first_off = next(sent for p, sent in settled if not traced_at or sent > traced_at[-1])
            latency.append(first_off - start)
            return None

        wait_until(check, timeout=timeout, interval=0.2)
        return latency[-1]

    def wait_for_trace(self, send, satisfied, timeout: float | None = None) -> float:
        """Barrier for a change that shows *inside* a traced request (rather
        than whether the request is traced at all).

        On every poll, `send(headers)` sends one fresh request carrying its
        own probe header. `satisfied(spans)` gets the spans of each probe's
        trace(s) so far and returns None once they show the new behaviour,
        or a description of what is still missing. Returns the flip latency:
        when the first satisfying probe was sent, counted from the call.
        Probes sent before the flip keep failing, so they can't satisfy it.
        """
        if timeout is None:
            timeout = FLIP_BUDGET_SECONDS
        start = time.monotonic()
        probes: list[tuple[str, float]] = []
        latency: list[float] = []
        last: list[str] = []

        def check() -> str | None:
            probe = f"probe-{uuid.uuid4().hex}"
            send({STEP_HEADER: probe})
            probes.append((probe, time.monotonic()))
            for p, sent in probes:
                spans = self.spans.for_step(p)
                if not spans:
                    continue  # not exported yet (or not traced at all)
                problem = satisfied(spans)
                if problem is None:
                    latency.append(sent - start)
                    return None
                last[:] = [problem]  # report the newest probe that has spans
            return last[0] if last else "no probe traced yet"

        wait_until(check, timeout=timeout, interval=0.2)
        return latency[-1]

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


# Attributes only the extensions could write. They must not (FR-014,
# UC-007 BR-001).
EXTENSION_ATTRS = ("otelfeature.sample_ratio",)


@pytest.fixture(scope="session", autouse=True)
def no_extension_attributes(spans):
    """FR-014 / UC-007 BR-001 over every span the session exported, checked
    once the last test is done: no geocode or weather span carries attributes
    the extensions would have written. Session-wide, so it covers every
    test's spans (sampled down and up) whichever tests run, and no violating
    trace can hide behind a barrier. flagd's own spans (flagSync) carry
    feature_flag.* attributes of their own and are left out."""
    yield
    time.sleep(QUIET_SECONDS)  # let the last test's spans reach the file
    spans.refresh()
    written = [s for s in spans.spans
               if s.service in ("geocode", "weather")
               and any(k.startswith("feature_flag.") or k in EXTENSION_ATTRS for k in s.attrs)]
    assert not written, f"span attributes the extensions must not write:\n{describe(written)}"


@pytest.fixture(scope="session")
def metrics() -> MetricLog:
    return MetricLog(Path(os.environ.get("E2E_METRICS_FILE", "/out/metrics.jsonl")))


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
def baseline(flags, spans):
    """Every test starts and ends on the baseline preset, and starts only
    once both services trace again (a failed test may have left them off)."""
    flags.apply("00-baseline")
    probe = Step(spans)
    for service in URLS:
        probe.wait_tracing(service, traced=True, timeout=30.0)
    probe.http.close()
    yield
    flags.apply("00-baseline")


@pytest.fixture
def step(spans, baseline):
    s = Step(spans)
    yield s
    s.http.close()
