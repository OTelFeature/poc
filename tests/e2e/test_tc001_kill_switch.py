"""TC-001: one flag switches tracing off in both services, and back on.

docs/spec/test_cases/TC-001-tracing-kill-switch.md, UC-001. The same flow
runs for both ways of switching off: the boolean `otelEnabled=false` (the
`01-otel-off` preset, Demo 1) and the string variant `telemetryLevel=OFF`
(Validation 2: both must give the same span output).
"""

from __future__ import annotations

import pytest

from checks import APP_SERVICES, by_root_service, complete_problem
from conftest import FLIP_BUDGET_SECONDS, URLS, Step
from flags import Flags
from spans import MetricLog, describe, wait_until


def _telemetry_level_off(flags: Flags) -> None:
    config = flags.preset("00-baseline")
    config["flags"]["telemetryLevel"]["defaultVariant"] = "off"
    flags.write(config)


SWITCHES = {
    "otelEnabled": lambda flags: flags.apply("01-otel-off"),
    "telemetryLevel": _telemetry_level_off,
}


def _send_cache_misses(step: Step, tag: str) -> None:
    city = f"e2e-{tag}-{step.id[:8]}"
    assert step.geocode(city, "nowhere").status_code == 404
    assert step.weather(city, "nowhere").status_code == 404


def _assert_complete_traces(step: Step) -> None:
    def problem() -> str | None:
        by_service = by_root_service(step.traces())
        for service in APP_SERVICES:
            trace = by_service.get(service)
            if trace is None:
                return f"no {service} trace for step yet"
            missing = complete_problem(trace, service)
            if missing:
                return f"{missing}:\n{describe(trace)}"
        return None

    wait_until(problem, timeout=10.0)


@pytest.mark.parametrize("switch", sorted(SWITCHES))
def test_tc001_kill_switch(step: Step, flags: Flags, metrics: MetricLog, switch: str):
    # Steps 1/5: turn tracing off.
    SWITCHES[switch](flags)
    for service in APP_SERVICES:
        latency = step.wait_tracing(service, traced=False)
        assert latency <= FLIP_BUDGET_SECONDS, f"{service}: off after {latency:.1f}s"

    # Steps 2/6: no new spans from either service, whatever they serve
    # (requests, Docker's healthchecks, weather's own flagd client calls).
    step.remark()
    metrics_mark = metrics.mark()
    _send_cache_misses(step, "off")
    for service in APP_SERVICES:
        assert step.health(URLS[service]).status_code == 200
    leaked = step.quiet(lambda s: s.resource.get("service.instance.id") in APP_SERVICES)
    assert not leaked, f"spans exported while {switch} is off:\n{describe(leaked)}"

    # Step 2, second half: the services keep *recording* metrics (spans only
    # are switched off; the HTTP metric is the input of the error-rate loop).
    # The requests above must show up in http.server.request.duration: its
    # cumulative count grows past the count exported before the window.
    before = {i: metrics.request_count(i, until=metrics_mark) or 0 for i in APP_SERVICES}

    def metrics_problem() -> str | None:
        for instance in APP_SERVICES:
            now = metrics.request_count(instance)
            if now is None or now <= before[instance]:
                return (f"{instance}: http.server.request.duration count {now} not above "
                        f"{before[instance]} since tracing went off")
        return None

    wait_until(metrics_problem, timeout=10.0)

    # Steps 3/7: back on; steps 4: complete traces again.
    flags.apply("00-baseline")
    for service in APP_SERVICES:
        latency = step.wait_tracing(service, traced=True)
        assert latency <= FLIP_BUDGET_SECONDS, f"{service}: on after {latency:.1f}s"
    _send_cache_misses(step, "on")
    _assert_complete_traces(step)
