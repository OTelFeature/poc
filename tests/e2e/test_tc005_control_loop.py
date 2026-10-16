"""TC-005: errors raise sampling for the failing service, and only for it.

docs/spec/test_cases/TC-005-incident-control-loop.md, UC-005, UC-006.

The rule is the control loop of decision D5 on `traceSampleRatio`:

    otelfeature.http.server.error_rate > 0.05  → all (1.0)
    deployment.environment.name == production  → none (0.0; stage: 0.1/0.5)
    otherwise                                  → all

Each extension computes its service's error rate from its own
http.server.request.duration metric every OTELFEATURE_ERROR_RATE_INTERVAL
(2 s in the e2e stack, min 5 requests) and puts it into the evaluation
context. Ratio 0.0 instead of the stage's values makes "sampling goes up" a
yes/no check. `weatherUpstreamFailure=outage` (1.0) makes every /weather
request fail with HTTP 503 (UC-006).

Built on 00-baseline plus these two flags only, not on the stage presets
(their geocode /health drop rule would hide geocode's sampling). The stage
preset 03b-incident is covered by the stage-progression test.

Traffic matters: below the minimum requests per interval the error-rate key
is absent, not 0.0. So every poll sends several requests to *both*
services, and geocode's are error-free: its rate is a real 0.0, and "geocode
unchanged" is measured, not assumed.
"""

from __future__ import annotations

import uuid

from conftest import GEOCODE_URL, WEATHER_URL, Step
from flags import Flags
from spans import STEP_HEADER, describe

# Error rate lags one to two intervals (NFR-014), then the rule applies to
# the next root span; 2 s intervals plus headroom.
LOOP_TIMEOUT = 20.0
PER_POLL = 3  # requests per service per poll (~15/s), well above min 5 per 2 s


def _loop_config(flags: Flags, failure: str) -> dict:
    config = flags.preset("00-baseline")
    config["flags"]["traceSampleRatio"]["targeting"] = {"if": [
        {">": [{"var": "otelfeature.http.server.error_rate"}, 0.05]}, "all",
        {"==": [{"var": "deployment.environment.name"}, "production"]}, "none",
        "all",
    ]}
    config["flags"]["weatherUpstreamFailure"]["defaultVariant"] = failure
    return config


class Traffic:
    """send(headers) for the barriers: PER_POLL /weather requests (503 during
    the outage, cache-missing 404 otherwise; the first carries the probe
    header) and PER_POLL error-free geocode requests tagged `geocode_tag`."""

    def __init__(self, step: Step):
        self.step = step
        self.geocode_tag = f"{step.id}-geocode"

    def __call__(self, headers: dict) -> None:
        for i in range(PER_POLL):
            r = self.step.http.post(f"{WEATHER_URL}/weather",
                                    json={"city": f"e2e-{uuid.uuid4().hex[:8]}", "country": "nowhere"},
                                    headers=headers if i == 0 else {})
            assert r.status_code in (404, 503), f"/weather: HTTP {r.status_code}"
            r = self.step.http.get(f"{GEOCODE_URL}/health", headers={STEP_HEADER: self.geocode_tag})
            assert r.status_code == 200, f"geocode /health: HTTP {r.status_code}"


# What the OpenFeature OTel hook pinned in weather emits (UC-007 BR-004:
# dev.openfeature.contrib.hooks:otel 3.3.1, semantic conventions 1.28).
HOOK_EVENT = "feature_flag"
HOOK_KEY, HOOK_VARIANT, HOOK_PROVIDER = "feature_flag.key", "feature_flag.variant", "feature_flag.provider_name"

# Written by the extensions? They must not (FR-014, UC-007 BR-001).
EXTENSION_ATTRS = ("otelfeature.sample_ratio",)


def _failing_and_traced(trace) -> str | None:
    server = next((s for s in trace if s.kind == "server" and s.service == "weather"), None)
    if server is None:
        return "no weather server span"
    if server.status != "error":
        return f"weather server span status {server.status}, want error:\n{describe(trace)}"
    return None


def _flag_explains_failure(trace) -> str | None:
    """TC-005 steps 6-7 / UC-007: a span of the failed request carries the
    hook's evaluation event for weatherUpstreamFailure."""
    if problem := _failing_and_traced(trace):
        return problem
    events = [(s, attrs) for s in trace for name, attrs in s.events
              if name == HOOK_EVENT and attrs.get(HOOK_KEY) == "weatherUpstreamFailure"]
    if not events:
        names = sorted({name for s in trace for name, _ in s.events})
        return f"no {HOOK_EVENT!r} event for weatherUpstreamFailure (events seen: {names}):\n{describe(trace)}"
    span, attrs = events[0]
    if span.service != "weather":
        return f"hook event on a {span.service} span"
    if attrs.get(HOOK_VARIANT) != "outage" or not attrs.get(HOOK_PROVIDER):
        return f"hook event attributes {attrs}, want variant 'outage' and a provider name"
    return None


def test_tc005_control_loop(step: Step, flags: Flags):
    traffic = Traffic(step)

    # Start: the loop rule, no failures. Production is at 0.0, so neither
    # service traces its roots, and both error rates are 0.0.
    flags.write(_loop_config(flags, failure="none"))
    step.wait_tracing("weather", traced=False, send=traffic)
    step.wait_tracing("geocode", traced=False)
    # Count geocode only from here: requests sent while the flip to 0.0 was
    # still propagating may legitimately have been traced.
    traffic.geocode_tag = f"{step.id}-geocode-{uuid.uuid4().hex[:6]}"

    # Steps 2-5: inject failures. Once the next collections put weather's
    # error rate above 0.05, its roots are sampled: a failing /weather
    # request (span status ERROR) is traced.
    flags.write(_loop_config(flags, failure="outage"))
    latency = step.wait_for_trace(traffic, _failing_and_traced, timeout=LOOP_TIMEOUT)
    print(f"weather sampled up {latency:.1f}s after the failures started")

    # Still sampled a few intervals later, with traffic going on (not a
    # one-off): a fresh failing request is traced again, and the trace says
    # which flag failed it (steps 6-7, UC-007).
    step.wait_for_trace(traffic, _flag_explains_failure, timeout=LOOP_TIMEOUT)

    # FR-014 / UC-007 BR-001, over every span exported so far in the session (both
    # services, sampled down and up): no span carries attributes the
    # extensions would have written. Outside the barrier, so one violating
    # trace can't be skipped.
    # Only the services the extensions run in: flagd's own spans (flagSync)
    # legitimately carry feature_flag.* attributes of their own.
    written = [s for s in step.spans.spans
               if s.service in ("geocode", "weather")
               and any(k.startswith("feature_flag.") or k in EXTENSION_ATTRS for k in s.attrs)]
    assert not written, f"span attributes the extensions must not write:\n{describe(written)}"

    # geocode had error-free traffic all along (rate 0.0): none of it traced.
    leaked = [s for s in step.spans.for_step(traffic.geocode_tag)]
    assert not leaked, f"geocode sampled although it has no errors:\n{describe(leaked)}"

    # Steps 8/9: stop the failures. /weather keeps going (now error-free
    # 404s), so weather's rate falls to a measured 0.0 and it is back at
    # the environment ratio.
    flags.write(_loop_config(flags, failure="none"))
    step.wait_tracing("weather", traced=False, send=traffic, timeout=LOOP_TIMEOUT)
    leaked = step.quiet(lambda s: s.step == traffic.geocode_tag)
    assert not leaked, f"geocode sampled at some point:\n{describe(leaked)}"
