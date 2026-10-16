"""TC-006: the stage presets in stage order, with no resets.

docs/spec/test_cases/TC-006-offline-stage-run.md ("Stage progression in
CI"), UC-008 BR-006. The demo is a progression: speakers never reset
between beats, so each preset must work right after the one before it:

    00-baseline → 01-otel-off → 02-quiet-noise → 03-semconv-rules
    → 03a-weather-boost → 03b-incident → 03a-weather-boost (incident over)

Each beat is checked with the effect STAGE.md promises. Ratios the stage
presets set to 0.1 or 0.5 are checked where they are deterministic (staging
at 1.0, production weather at 1.0 during the incident) or with wide
statistical bands; the exact ratio checks are in test_tc004 / test_tc005.
"""

from __future__ import annotations

import uuid

from conftest import FLIP_BUDGET_SECONDS, URLS, Step
from flags import Flags
from spans import STEP_HEADER, describe, wait_until

KNOWN = {"city": "linz", "country": "austria"}  # cached and stub-known: 200


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


def _all_traced(step: Step, tags: dict[str, tuple[str, int]], timeout: float = 10.0) -> None:
    def problem() -> str | None:
        for name, (tag, n) in tags.items():
            got = _server_count(step, tag)
            if got < n:
                return f"{name}: {got}/{n} traced, expected all"
        return None
    wait_until(problem, timeout=timeout)


def test_stage_progression(step: Step, flags: Flags):
    # 00-baseline: everything traced (the fixture already applied it).
    _all_traced(step, {i: (_batch(step, i, 3), 3) for i in URLS})

    # 01-otel-off: no spans from either production service.
    flags.apply("01-otel-off")
    for service in ("geocode", "weather"):
        latency = step.wait_tracing(service, traced=False)
        assert latency <= FLIP_BUDGET_SECONDS, f"01: {service} off after {latency:.1f}s"

    # 02-quiet-noise, straight from 01: tracing back on, with geocode's
    # /health and weather's JDBC spans dropped.
    flags.apply("02-quiet-noise")
    step.wait_tracing("weather", traced=True)
    step.wait_tracing("geocode", traced=False, path="/health")
    geocode_tag = _batch(step, "geocode", 3, "geocode")
    _all_traced(step, {"geocode /geocode": (geocode_tag, 3)})

    def no_jdbc() -> str | None:
        tag = _batch(step, "weather", 1, "weather")
        spans = step.spans.for_step(tag)
        if not any(s.kind == "server" for s in spans):
            return "weather /weather not traced yet"
        jdbc = [s for s in spans if s.scope == "io.opentelemetry.jdbc"]
        return f"02: JDBC spans still exported:\n{describe(jdbc)}" if jdbc else None

    wait_until(no_jdbc, timeout=FLIP_BUDGET_SECONDS)

    # 03-semconv-rules: production at 0.1, staging at 1.0; 02's drops stay.
    flags.apply("03-semconv-rules")
    n = 60

    def sampled_down() -> str | None:
        # Barrier: at 1.0 all 20 are traced; at 0.1 that has odds of 1e-20.
        tag = _batch(step, "weather", 20)
        step.quiet(lambda s: False)
        got = _server_count(step, tag)
        return None if got < 20 else "03: production weather still fully sampled"

    wait_until(sampled_down, timeout=3 * FLIP_BUDGET_SECONDS, interval=0)
    # Cumulative: 02's geocode /health drop holds in staging too.
    step.wait_tracing("geocode-staging", traced=False, path="/health")
    tags = {
        "weather-staging": (_batch(step, "weather-staging", 10), 10),
        "geocode-staging /geocode": (_batch(step, "geocode-staging", 10, "geocode"), 10),
    }
    _all_traced(step, tags)
    prod = _batch(step, "weather", n)
    step.quiet(lambda s: False)
    got = _server_count(step, prod)
    assert got <= 20, f"03: production weather {got}/{n} traced at 0.1 (expected about 6)"

    # 03a-weather-boost: production weather at 0.5.
    flags.apply("03a-weather-boost")

    def about_half() -> str | None:
        tag = _batch(step, "weather", n)
        step.quiet(lambda s: False)
        got = _server_count(step, tag)
        # 0.5 of 60: mean 30, sd ~3.9. 0.1 gives ~6, 1.0 gives 60.
        return None if 15 <= got <= 45 else f"03a: production weather {got}/{n} traced, want about half"

    wait_until(about_half, timeout=3 * FLIP_BUDGET_SECONDS, interval=0)

    # 03b-incident: weather fails ~30%; its error rate passes 5% and the
    # loop samples production weather fully. Traffic keeps the error-rate
    # interval above its minimum; "all of a batch of 20 traced" is how 1.0
    # shows (at 0.5 that has a chance of 1 in a million).
    flags.apply("03b-incident")

    def fully_sampled() -> str | None:
        tag = _batch(step, "weather", 20, "weather")
        step.quiet(lambda s: False)
        got = _server_count(step, tag)
        errors = len([s for s in step.spans.for_step(tag) if s.kind == "server" and s.status == "error"])
        if got < 20:
            return f"03b: production weather {got}/20 traced, waiting for the loop ({errors} errors seen)"
        return None if errors else "03b: no failing /weather traced"

    wait_until(fully_sampled, timeout=30.0, interval=0)

    # Incident over: back to 03a; error-free traffic brings weather's rate
    # to 0.0 and it returns to about half.
    flags.apply("03a-weather-boost")
    wait_until(about_half, timeout=30.0, interval=0)


def test_tc006_rapid_flips(step: Step, flags: Flags):
    """TC-006 V7: three flips within one second end in the last preset's
    state (each write gets a strictly newer mtime, so none is ignored)."""
    flags.write(flags.preset("01-otel-off"), wait=False)
    flags.write(flags.preset("00-baseline"), wait=False)
    flags.write(flags.preset("01-otel-off"))  # waits until flagd serves this one
    assert flags.evaluate("otelEnabled") is False
    for service in ("geocode", "weather"):
        step.wait_tracing(service, traced=False)
