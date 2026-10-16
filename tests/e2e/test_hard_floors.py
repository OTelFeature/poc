"""Hard floors: env vars that switched tracing off can't be undone by a flag.

TC-001 Validation 6 (OTEL_SDK_DISABLED=true) and TC-001 Validation 7 /
TC-004 Validation 8 (OTEL_TRACES_SAMPLER=always_off). compose.e2e.yaml runs
an extra instance of each service per floor, with its own
service.instance.id. The flags are at baseline, which says "trace
everything" (otelEnabled on, telemetryLevel FULL, traceSampleRatio 1.0).
The test sends the floor instances requests, including one with a sampled
traceparent, and asserts that none of them exports a single span. The normal
instances, in the same window, are the positive control.
"""

from __future__ import annotations

import pytest

from checks import APP_SERVICES
from conftest import URLS, Step
from spans import describe, wait_until

PORTS = {"geocode": 8000, "weather": 8001}
FLOORS = ("sdk-disabled", "always-off")

# A sampled remote parent: under always_off it must not be followed either.
SAMPLED_PARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


@pytest.mark.parametrize("floor", FLOORS)
def test_hard_floor(step: Step, floor: str):
    instances = {f"{service}-{floor}" for service in APP_SERVICES}
    step.remark()

    for service in APP_SERVICES:
        url = f"http://{service}-{floor}:{PORTS[service]}"
        assert step.health(url).status_code == 200
        r = step.http.get(f"{url}/health", headers={"traceparent": SAMPLED_PARENT})
        assert r.status_code == 200
        # Positive control: the normal instance, same flags, same window.
        assert step.health(URLS[service]).status_code == 200

    def control_problem() -> str | None:
        seen = {s.service for s in step.since_mark()
                if s.kind == "server" and s.step == step.id
                and s.resource.get("service.instance.id") in APP_SERVICES}
        missing = set(APP_SERVICES) - seen
        return f"control: no span yet from {sorted(missing)}" if missing else None

    wait_until(control_problem, timeout=10.0)

    leaked = step.quiet(lambda s: s.resource.get("service.instance.id") in instances
                        or s.trace_id == SAMPLED_PARENT.split("-")[1])
    assert not leaked, f"spans exported despite the {floor} floor:\n{describe(leaked)}"
