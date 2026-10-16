"""TC-005: errors raise sampling for the failing service, and only for it.

docs/spec/test_cases/TC-005-incident-control-loop.md, UC-005, UC-006.

The rule is the control loop of decision D5 on `traceSampleRatio`:

    otelfeature.http.server.error_rate > 0.05  → all (1.0)
    deployment.environment.name == production  → none (0.0; stage: 0.1)
    otherwise                                  → all

Each extension computes its service's error rate from its own
http.server.request.duration metric every OTELFEATURE_ERROR_RATE_INTERVAL
(2 s in the e2e stack) and puts it into the evaluation context. Ratio 0.0
instead of the stage's 0.1 makes "sampling goes up" a yes/no check.
`weatherUpstreamFailure=outage` (1.0) makes every /weather request fail with
HTTP 503 (UC-006).
"""

from __future__ import annotations

import uuid

from conftest import WEATHER_URL, Step
from flags import Flags
from spans import STEP_HEADER, describe

# Error rate lags one to two intervals (NFR-014), then flagd's rule applies
# to the next root span; 2 s intervals plus headroom.
LOOP_TIMEOUT = 20.0


def _loop_config(flags: Flags, failure: str) -> dict:
    config = flags.preset("03-semconv-rules")
    config["flags"]["traceSampleRatio"]["targeting"] = {"if": [
        {">": [{"var": "otelfeature.http.server.error_rate"}, 0.05]}, "all",
        {"==": [{"var": "deployment.environment.name"}, "production"]}, "none",
        "all",
    ]}
    config["flags"]["weatherUpstreamFailure"]["defaultVariant"] = failure
    return config


def _send_weather(step: Step):
    """send(headers) for wait_for_trace: /weather, a failure while the
    outage is on, a cache-missing 404 otherwise."""
    def send(headers: dict) -> None:
        r = step.http.post(f"{WEATHER_URL}/weather",
                           json={"city": f"e2e-{uuid.uuid4().hex[:8]}", "country": "nowhere"},
                           headers=headers)
        assert r.status_code in (404, 503), f"/weather: HTTP {r.status_code}"
    return send


def test_tc005_control_loop(step: Step, flags: Flags):
    # Start of the run-through: the loop rule, no failures. Production is
    # at 0.0, so neither service traces its roots.
    flags.write(_loop_config(flags, failure="none"))
    for service in ("geocode", "weather"):
        step.wait_tracing(service, traced=False)

    # Steps 2-5: inject failures. Every /weather request now fails; once the
    # next collections put weather's error rate above 0.05, its roots are
    # sampled again. Each poll sends one more failing request, which also
    # keeps the interval above OTELFEATURE_ERROR_RATE_MIN_REQUESTS.
    flags.write(_loop_config(flags, failure="outage"))

    def failing_and_traced(trace) -> str | None:
        server = next((s for s in trace if s.kind == "server" and s.service == "weather"), None)
        if server is None:
            return "no weather server span"
        if server.status != "error":
            return f"weather server span status {server.status}, want error:\n{describe(trace)}"
        return None

    latency = step.wait_for_trace(_send_weather(step), failing_and_traced, timeout=LOOP_TIMEOUT)
    print(f"weather sampled up {latency:.1f}s after the failures started")

    # geocode has no errors, so it stays at the environment ratio (0.0).
    step.remark()
    tag = f"{step.id}-geocode"
    for _ in range(5):
        r = step.http.get("http://geocode:8000/health", headers={STEP_HEADER: tag})
        assert r.status_code == 200
    leaked = step.quiet(lambda s: s.step == tag)
    assert not leaked, f"geocode sampled although it has no errors:\n{describe(leaked)}"

    # Steps 8/9: stop the failures. With error-free intervals weather's rate
    # drops below the threshold and it is back at the environment ratio.
    flags.write(_loop_config(flags, failure="none"))
    step.wait_tracing("weather", traced=False, timeout=LOOP_TIMEOUT)
