"""TC-006: the stage presets in stage order, with no resets.

docs/spec/test_cases/TC-006-offline-stage-run.md ("Stage progression in
CI"), UC-008 BR-006. The demo is a progression: speakers never reset
between beats, so each preset must work right after the one before it:

    00-baseline → 01-otel-off → 02-quiet-noise → 03-semconv-rules
    → 03a-weather-boost → 03b-incident → 03a-weather-boost (incident over)

Each beat is checked for the core effect STAGE.md promises. Ratios the
stage presets set to 0.1 or 0.5 are checked with wide statistical bands,
retried until they hold; exact ratio checks are in test_tc004 / test_tc005.
The run-through is marked `stage_run`: it runs on pushes to main, nightly
and on manual runs, not on pull requests (NFR-015; every beat has its own
per-PR test). test_tc006_rapid_flips runs on every pull request.

Production geocode is counted on POST /geocode, because 03's recordSpan rule
drops its /health from 03 on. 02 cuts by span kind only (telemetryLevel IO,
OTelFeature/poc#110): from 02 on, no INTERNAL span is exported.
"""

from __future__ import annotations

import time
import uuid

import pytest

from conftest import FLIP_BUDGET_SECONDS, QUIET_SECONDS, URLS, Step
from flags import Flags
from checks import is_db
from spans import STEP_HEADER, describe, tree_problem, wait_until

KNOWN = {"city": "linz", "country": "austria"}  # cached and stub-known: 200
N = 60


def _server_count(step: Step, tag: str) -> int:
    return len([s for s in step.spans.for_step(tag) if s.kind == "server"])


def _batch(step: Step, instance: str, n: int, method: str = "health") -> str:
    """n requests to `instance` under a fresh tag; returns the tag."""
    tag = f"{step.id}-{instance}-{uuid.uuid4().hex[:6]}"
    for _ in range(n):
        if method == "health":
            r = step.http.get(f"{URLS[instance]}/health", headers={STEP_HEADER: tag})
            assert r.status_code == 200
        elif method == "geocode":
            r = step.http.post(f"{URLS[instance]}/geocode", json=KNOWN, headers={STEP_HEADER: tag})
            assert r.status_code == 200
        else:  # weather: 200, or 503 while the fault flag is on
            r = step.http.post(f"{URLS[instance]}/weather", json=KNOWN, headers={STEP_HEADER: tag})
            assert r.status_code in (200, 503), f"/weather: HTTP {r.status_code}"
    return tag


def _settle() -> None:
    """Let the last export batches arrive before counting a statistical
    batch (an absence-style count: missing spans can't be waited for)."""
    time.sleep(QUIET_SECONDS)


def _counted(step: Step, instance: str, method: str = "health") -> int:
    tag = _batch(step, instance, N, method)
    _settle()
    return _server_count(step, tag)


def _all_traced(step: Step, tags: dict[str, tuple[str, int]], timeout: float = 10.0) -> None:
    def problem() -> str | None:
        for name, (tag, n) in tags.items():
            got = _server_count(step, tag)
            if got < n:
                return f"{name}: {got}/{n} traced, expected all"
        return None
    wait_until(problem, timeout=timeout)


def _sender(step: Step, instance: str):
    """send(headers) for wait_for_trace: one request to `instance` that
    reads the database (POST /geocode or /weather, a cached location)."""
    path = "/geocode" if instance.startswith("geocode") else "/weather"

    def send(headers: dict) -> None:
        r = step.http.post(f"{URLS[instance]}{path}", json=KNOWN, headers=headers)
        assert r.status_code == 200, f"{instance}{path}: HTTP {r.status_code}"
    return send


def _io_problem(spans, instance: str, beat: str, want_db: bool) -> str | None:
    """Under telemetryLevel IO: a server span, no INTERNAL span, and DB
    spans present (want_db) or no JDBC span (03's rule, weather); tree
    connected."""
    if not any(s.kind == "server" for s in spans):
        return f"{beat}: {instance} server span not exported yet"
    if internal := [s for s in spans if s.kind == "internal"]:
        return f"{beat}: {instance} INTERNAL spans still exported:\n{describe(internal)}"
    db = [s for s in spans if is_db(s)]
    if want_db and not db:
        return f"{beat}: {instance} DB spans missing:\n{describe(spans)}"
    if not want_db and (jdbc := [s for s in db if s.scope == "io.opentelemetry.jdbc"]):
        return f"{beat}: {instance} JDBC spans still exported:\n{describe(jdbc)}"
    return tree_problem(spans)


def _geocode_production_low(step: Step, beat: str) -> None:
    """Production geocode stays at 0.1 (1..20 of 60; the odds of a false
    failure at 0.1 are about 1e-7)."""
    got = _counted(step, "geocode", "geocode")
    assert 1 <= got <= 20, f"{beat}: production geocode {got}/{N} traced at 0.1"


@pytest.mark.stage_run
def test_stage_progression(step: Step, flags: Flags):
    # 00-baseline: everything traced (the fixture already applied it).
    _all_traced(step, {i: (_batch(step, i, 3), 3) for i in URLS})

    # 01-otel-off: no spans from either production service.
    flags.apply("01-otel-off")
    for service in ("geocode", "weather"):
        latency = step.wait_tracing(service, traced=False)
        assert latency <= FLIP_BUDGET_SECONDS, f"01: {service} off after {latency:.1f}s"

    # 02-quiet-noise, straight from 01: tracing back on, by span kind only
    # (telemetryLevel IO): requests in both services are traced again, with
    # no INTERNAL span and the DB spans still there.
    flags.apply("02-quiet-noise")
    step.wait_tracing("weather", traced=True)

    def geocode_back() -> str | None:
        tag = _batch(step, "geocode", 1, "geocode")
        _settle()
        return None if _server_count(step, tag) else "02: geocode /geocode not traced yet"

    wait_until(geocode_back, timeout=3 * FLIP_BUDGET_SECONDS, interval=0)
    for instance in ("geocode", "weather"):
        latency = step.wait_for_trace(_sender(step, instance),
                                      lambda t, i=instance: _io_problem(t, i, "02", want_db=True))
        assert latency <= FLIP_BUDGET_SECONDS, f"02: {instance} at IO after {latency:.1f}s"

    # 03-semconv-rules: production at 0.1, staging at 1.0; 02's IO cut stays,
    # and the recordSpan rules drop geocode's /health and weather's JDBC spans.
    flags.apply("03-semconv-rules")

    def sampled_down() -> str | None:
        # Barrier: at 1.0 all 20 are traced; at 0.1 that has odds of 1e-20.
        tag = _batch(step, "weather", 20)
        _settle()
        return None if _server_count(step, tag) < 20 else "03: production weather still fully sampled"

    wait_until(sampled_down, timeout=3 * FLIP_BUDGET_SECONDS, interval=0)
    # The rules, checked in staging (1.0), where an absence can't be sampling.
    step.wait_tracing("geocode-staging", traced=False, path="/health")
    latency = step.wait_for_trace(_sender(step, "weather-staging"),
                                  lambda t: _io_problem(t, "weather-staging", "03", want_db=False))
    assert latency <= FLIP_BUDGET_SECONDS, f"03: weather-staging JDBC spans dropped after {latency:.1f}s"
    step.wait_for_trace(_sender(step, "geocode-staging"),
                        lambda t: _io_problem(t, "geocode-staging", "03", want_db=True))
    _all_traced(step, {
        "weather-staging": (_batch(step, "weather-staging", 10), 10),
        "geocode-staging /geocode": (_batch(step, "geocode-staging", 10, "geocode"), 10),
    })
    got = _counted(step, "weather")
    assert 1 <= got <= 20, f"03: production weather {got}/{N} traced at 0.1"
    _geocode_production_low(step, "03")

    # 03a-weather-boost: production weather at 0.5, geocode stays at 0.1.
    flags.apply("03a-weather-boost")

    def about_half() -> str | None:
        got = _counted(step, "weather")
        # 0.5 of 60: mean 30, sd ~3.9; 20..40 rules out 0.1 (~6) and 1.0 (60).
        return None if 20 <= got <= 40 else f"production weather {got}/{N} traced, want about half"

    wait_until(about_half, timeout=3 * FLIP_BUDGET_SECONDS, interval=0)
    _geocode_production_low(step, "03a")

    # 03b-incident: weather fails ~50% (UC-006 BR-003); its error rate
    # passes 5% and the loop samples production weather fully. The error rate needs continuous
    # traffic (min 5 requests per 2 s interval; below it the key is absent
    # and weather falls back to 0.5), so there is no settle pause between
    # batches here: each poll sends 20 requests and waits only until they're
    # all traced, briefly. "All 20 traced" at 0.5 has odds of 1e-6.
    flags.apply("03b-incident")

    def fully_sampled() -> str | None:
        tag = _batch(step, "weather", 20, "weather")
        try:
            wait_until(lambda: None if _server_count(step, tag) >= 20 else "not all traced", timeout=1.0)
        except AssertionError:
            return f"03b: production weather {_server_count(step, tag)}/20 traced, waiting for the loop"
        errors = [s for s in step.spans.for_step(tag) if s.kind == "server" and s.status == "error"]
        return None if errors else "03b: no failing /weather traced"

    wait_until(fully_sampled, timeout=30.0, interval=0)
    _geocode_production_low(step, "03b")  # the loop raises only the failing service
    # Cumulative: the IO cut and the /health rule are still on in 03b
    # (geocode-staging: 1.0, no fault, so an absence is the rule's).
    step.wait_tracing("geocode-staging", traced=False, path="/health")
    step.wait_for_trace(_sender(step, "geocode-staging"),
                        lambda t: _io_problem(t, "geocode-staging", "03b", want_db=True))

    # Incident over: back to 03a. The fault and the loop rule go with the
    # preset, so weather is back at 0.5 on the flip (OQ-14).
    flags.apply("03a-weather-boost")
    wait_until(about_half, timeout=3 * FLIP_BUDGET_SECONDS, interval=0)
    # ... and 03a still carries the IO cut and both recordSpan rules.
    step.wait_tracing("geocode-staging", traced=False, path="/health")
    step.wait_for_trace(_sender(step, "weather-staging"),
                        lambda t: _io_problem(t, "weather-staging", "03a", want_db=False))


def test_tc006_rapid_flips(step: Step, flags: Flags):
    """TC-006 V7: three flips within one second end in the last preset's
    state (each write gets a strictly newer mtime, so none is ignored). The
    last state, 02-quiet-noise, differs from the start and from the first
    flip, so the services must have applied the last write."""
    def no_internal(spans) -> str | None:
        if not any(s.kind == "server" for s in spans):
            return "geocode /health server span not exported yet"
        internal = [s for s in spans if s.kind == "internal"]
        return f"INTERNAL spans still exported:\n{describe(internal)}" if internal else None

    flags.write(flags.preset("01-otel-off"), wait=False)
    flags.write(flags.preset("00-baseline"), wait=False)
    flags.write(flags.preset("02-quiet-noise"))  # waits until flagd serves this one
    assert flags.evaluate("otelEnabled") is True
    # Tracing is on (not 01) ...
    step.wait_tracing("weather", traced=True)
    # ... at telemetryLevel IO (not 00): geocode's /health trace without its
    # INTERNAL http send spans.
    assert flags.evaluate("telemetryLevel") == "IO"

    def send_health(headers: dict) -> None:
        assert step.http.get(f"{URLS['geocode']}/health", headers=headers).status_code == 200

    step.wait_for_trace(send_health, no_internal)
