"""TC-004: trace sampling targeted by environment and service (Demo 3).

docs/spec/test_cases/TC-004-target-trace-sampling.md, UC-004.

CI checks the rules deterministically: the same rule shapes as the stage
presets 03-semconv-rules / 03a-weather-full, with ratio 0.0 where the stage
uses 0.1, so "about one in ten" becomes "none" and every request is a
yes/no check. The stage presets themselves, with their real 0.1, run as a
statistical test marked `slow` (nightly).

Every request here is a root (k6-like, no traceparent), so each one makes
its own sampling decision (UC-004 BR-002, roots only).
"""

from __future__ import annotations

import time
import uuid

import pytest

from conftest import FLIP_BUDGET_SECONDS, URLS, Step
from flags import Flags
from spans import STEP_HEADER, describe, tree_problem, wait_until

PRODUCTION = ("geocode", "weather")
STAGING = ("geocode-staging", "weather-staging")


def _eq(key: str, value: str) -> dict:
    return {"==": [{"var": key}, value]}


def _ratio_rule(flags: Flags, weather_full: bool) -> dict:
    """The shape of 03-semconv-rules / 03a's weather override, with 0.0
    instead of 0.1. Built on 00-baseline, *not* on the stage presets: those
    are cumulative and keep 02-quiet-noise's rule dropping geocode /health,
    which would make every geocode probe here untraced whatever the ratio."""
    config = flags.preset("00-baseline")
    branches = []
    if weather_full:
        branches += [{"and": [_eq("deployment.environment.name", "production"),
                              _eq("service.name", "weather")]}, "all"]
    branches += [_eq("deployment.environment.name", "production"), "none", "all"]
    config["flags"]["traceSampleRatio"]["targeting"] = {"if": branches}
    return config


def _traced(step: Step, instance: str, count: int = 5) -> str:
    """Send `count` /health requests to `instance` under a fresh step tag;
    returns the tag, to count the traced ones by."""
    tag = f"{step.id}-{instance}-{uuid.uuid4().hex[:6]}"
    for _ in range(count):
        r = step.http.get(f"{URLS[instance]}/health", headers={"x-e2e-step": tag})
        assert r.status_code == 200
    return tag


def _assert_sampling(step: Step, expected: dict[str, bool], count: int = 5) -> None:
    tags = {instance: _traced(step, instance, count) for instance in expected}

    def problem() -> str | None:
        for instance, sampled in expected.items():
            if not sampled:
                continue
            n = len([s for s in step.spans.for_step(tags[instance]) if s.kind == "server"])
            if n < count:
                return f"{instance}: {n}/{count} requests traced, expected all"
        return None

    wait_until(problem, timeout=10.0)
    unsampled = [instance for instance, sampled in expected.items() if not sampled]
    leaked = step.quiet(lambda s: any(s.step == tags[i] for i in unsampled))
    assert not leaked, f"sampled although the rule says 0.0:\n{describe(leaked)}"


def test_tc004_target_sampling(step: Step, flags: Flags):
    # Step 1: spans carry the environment set by the service.
    for instance in PRODUCTION + STAGING:
        assert step.health(URLS[instance]).status_code == 200

    def env_problem() -> str | None:
        seen = {s.resource.get("service.instance.id"): s.resource.get("deployment.environment.name")
                for s in step.spans.for_step(step.id) if s.kind == "server"}
        for instance in PRODUCTION + STAGING:
            want = "staging" if instance in STAGING else "production"
            if seen.get(instance) != want:
                return f"{instance}: deployment.environment.name={seen.get(instance)!r}, want {want}"
        return None

    wait_until(env_problem, timeout=10.0)

    # Steps 2/3: production → 0.0 (stage: 0.1), staging → 1.0.
    flags.write(_ratio_rule(flags, weather_full=False))
    for service in PRODUCTION:
        latency = step.wait_tracing(service, traced=False)
        assert latency <= FLIP_BUDGET_SECONDS, f"{service} sampled down after {latency:.1f}s"
    step.remark()
    _assert_sampling(step, {"geocode": False, "weather": False,
                            "geocode-staging": True, "weather-staging": True})

    # Steps 4/5: production weather back to 1.0, production geocode stays 0.0.
    flags.write(_ratio_rule(flags, weather_full=True))
    latency = step.wait_tracing("weather", traced=True)
    assert latency <= FLIP_BUDGET_SECONDS, f"weather sampled up after {latency:.1f}s"
    step.remark()
    _assert_sampling(step, {"geocode": False, "weather": True,
                            "geocode-staging": True, "weather-staging": True})


@pytest.mark.slow
def test_tc004_stage_preset_ratio(step: Step, flags: Flags):
    """The stage preset as it is: production at 0.1 ("about one in ten",
    UC-004 step 6). 300 roots per service: the expected 30 has a standard
    deviation of about 5, so 10..55 still fails on 0.0, 0.5 or 1.0.

    The preset keeps 02-quiet-noise's rules, so geocode is counted on
    POST /geocode (a location the stub knows), not /health."""
    # Start from a deterministic 0.0 (barrier), so a late flip to 0.1 can
    # only deflate the counts by a few, never inflate them toward 1.0.
    flags.write(_ratio_rule(flags, weather_full=False))
    for service in PRODUCTION:
        step.wait_tracing(service, traced=False)
    flags.apply("03-semconv-rules")
    # 0.0 → 0.1 has no deterministic probe; uncounted warm-up traffic for
    # the flip budget covers the services picking the preset up.
    deadline = time.monotonic() + FLIP_BUDGET_SECONDS
    while time.monotonic() < deadline:
        step.http.get(f"{URLS['weather']}/health")
        step.http.post(f"{URLS['geocode']}/geocode", json={"city": "linz", "country": "austria"})

    n = 300
    tags = {"geocode": f"{step.id}-geocode", "weather": f"{step.id}-weather"}
    for _ in range(n):
        r = step.http.post(f"{URLS['geocode']}/geocode", json={"city": "linz", "country": "austria"},
                           headers={STEP_HEADER: tags["geocode"]})
        assert r.status_code == 200
        r = step.http.get(f"{URLS['weather']}/health", headers={STEP_HEADER: tags["weather"]})
        assert r.status_code == 200
    step.quiet(lambda s: False)  # let the last batches arrive
    for service, tag in tags.items():
        count = len([s for s in step.spans.for_step(tag) if s.kind == "server"])
        assert 10 <= count <= 55, f"{service} production: {count}/{n} sampled at 0.1"


FORECAST = {"city": "linz", "country": "austria"}  # stub-known: geocode and weather answer 200


def _forecast_trace_problem(trace) -> str | None:
    """A /forecast trace: geocode server root, geocode HTTP client span to
    weather, weather server span as that client span's child, connected."""
    root = next((s for s in trace if s.is_root), None)
    if root is None or root.service != "geocode" or root.attrs.get("url.path") != "/forecast":
        return f"no geocode /forecast root:\n{describe(trace)}"
    weather = next((s for s in trace if s.service == "weather" and s.kind == "server"), None)
    if weather is None:
        return f"no weather server span in the /forecast trace:\n{describe(trace)}"
    parent = next((s for s in trace if s.span_id == weather.parent_id), None)
    if parent is None or parent.service != "geocode" or parent.kind != "client":
        return f"weather's parent is not geocode's HTTP client span:\n{describe(trace)}"
    return tree_problem(trace)


def test_tc004_cross_service(step: Step, flags: Flags):
    """TC-004 step 6 / UC-004 BR-003 and A2 on the cross-service path
    (FR-026): geocode's POST /forecast calls weather. A sampled trace has
    spans from both services, and the entry point (geocode) decides for the
    whole trace, whatever weather's own ratio says."""
    # Baseline: complete across services.
    r = step.http.post(f"{URLS['geocode']}/forecast", json=FORECAST)
    assert r.status_code == 200, f"/forecast: HTTP {r.status_code} {r.text}"
    assert "weather" in r.json()

    def complete() -> str | None:
        traces = [t for t in step.traces().values()
                  if any(s.is_root and s.attrs.get("url.path") == "/forecast" for s in t)]
        if not traces:
            return "no /forecast trace yet"
        return _forecast_trace_problem(traces[0])

    wait_until(complete, timeout=10.0)

    # Production geocode at 0.0, production weather at 1.0 (the 03a shape
    # with 0.0 for 0.1): /forecast traces are absent in *both* services,
    # while direct /weather traces are sampled.
    config = flags.preset("00-baseline")
    config["flags"]["traceSampleRatio"]["targeting"] = {"if": [
        {"and": [_eq("deployment.environment.name", "production"), _eq("service.name", "weather")]}, "all",
        _eq("deployment.environment.name", "production"), "none",
        "all",
    ]}
    flags.write(config)
    step.wait_tracing("geocode", traced=False)
    step.wait_tracing("weather", traced=True)

    step.remark()
    forecast_tag, weather_tag = f"{step.id}-forecast", f"{step.id}-weather"
    for _ in range(5):
        r = step.http.post(f"{URLS['geocode']}/forecast", json=FORECAST, headers={STEP_HEADER: forecast_tag})
        assert r.status_code == 200
        r = step.http.post(f"{URLS['weather']}/weather", json=FORECAST, headers={STEP_HEADER: weather_tag})
        assert r.status_code == 200

    def direct_sampled() -> str | None:
        n = len([s for s in step.spans.for_step(weather_tag) if s.kind == "server"])
        return None if n >= 5 else f"direct /weather: {n}/5 traced, expected all"

    wait_until(direct_sampled, timeout=10.0)
    # A weather server span with a parent comes from /forecast (direct calls
    # and Docker's healthchecks are roots), so any of them is a leak.
    leaked = step.quiet(lambda s: s.step == forecast_tag
                        or (s.service == "weather" and s.kind == "server" and not s.is_root
                            and s.resource.get("service.instance.id") == "weather"))
    assert not leaked, f"/forecast traced although geocode decided 0.0:\n{describe(leaked)}"
