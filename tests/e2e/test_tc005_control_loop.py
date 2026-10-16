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
yes/no check. `<service>UpstreamFailure=outage` (1.0) makes every request
to that service's business endpoint fail with HTTP 503 (UC-006).

Runs once per language (TC-005 item 14, OTelFeature/poc#80): failures in
weather exercise the Java error-rate reader, failures in geocode the Python
one; each time the other service must stay unchanged.

Built on 00-baseline plus these two flags only, not on the stage presets
(their geocode /health drop rule would hide geocode's sampling). The stage
preset 03b-incident is covered by the stage-progression test.

Traffic matters: below the minimum requests per interval the error-rate key
is absent, not 0.0. So every poll sends several requests to *both*
services, and the other service's are error-free: its rate is a real 0.0,
and "unchanged" is measured, not assumed.
"""

from __future__ import annotations

import uuid

import pytest

from conftest import GEOCODE_URL, WEATHER_URL, Step
from flags import Flags
from spans import STEP_HEADER, describe

# Error rate lags one to two intervals (NFR-014), then the rule applies to
# the next root span; 2 s intervals plus headroom.
LOOP_TIMEOUT = 20.0
PER_POLL = 3  # requests per service per poll (~15/s), well above min 5 per 2 s


FAULT_FLAGS = {"weather": "weatherUpstreamFailure", "geocode": "geocodeUpstreamFailure"}
OTHER = {"weather": "geocode", "geocode": "weather"}


def _loop_config(flags: Flags, failing: str, failure: str) -> dict:
    config = flags.preset("00-baseline")
    config["flags"]["traceSampleRatio"]["targeting"] = {"if": [
        {">": [{"var": "otelfeature.http.server.error_rate"}, 0.05]}, "all",
        {"==": [{"var": "deployment.environment.name"}, "production"]}, "none",
        "all",
    ]}
    # geocode's flag isn't in the stage presets (UC-006 BR-004): define it here.
    config["flags"]["geocodeUpstreamFailure"] = {
        "state": "ENABLED", "defaultVariant": "none", "variants": {"none": 0.0, "outage": 1.0},
    }
    config["flags"][FAULT_FLAGS[failing]]["defaultVariant"] = failure
    return config


class Traffic:
    """send(headers) for the barriers: PER_POLL business requests to the
    failing service (503 during the outage, cache-missing 404 otherwise; the
    first carries the probe header) and PER_POLL error-free /health requests
    to the other service, tagged `other_tag`."""

    def __init__(self, step: Step, failing: str):
        self.step = step
        self.failing = failing
        self.other_tag = f"{step.id}-{OTHER[failing]}"

    def __call__(self, headers: dict) -> None:
        url = f"{WEATHER_URL}/weather" if self.failing == "weather" else f"{GEOCODE_URL}/geocode"
        other = GEOCODE_URL if self.failing == "weather" else WEATHER_URL
        for i in range(PER_POLL):
            r = self.step.http.post(url, json={"city": f"e2e-{uuid.uuid4().hex[:8]}", "country": "nowhere"},
                                    headers=headers if i == 0 else {})
            assert r.status_code in (404, 503), f"{url}: HTTP {r.status_code}"
            r = self.step.http.get(f"{other}/health", headers={STEP_HEADER: self.other_tag})
            assert r.status_code == 200, f"{other}/health: HTTP {r.status_code}"


# What the OpenFeature OTel hook pinned in each service emits (UC-007 BR-004,
# OQ-4): weather's Java hook dev.openfeature.contrib.hooks:otel 3.3.1 the
# semantic conventions 1.28 names, geocode's Python hook
# openfeature-hooks-opentelemetry 0.3.1 the current ones.
# (event name, key, variant, provider name)
HOOK_NAMES = {
    "weather": ("feature_flag", "feature_flag.key", "feature_flag.variant", "feature_flag.provider_name"),
    "geocode": ("feature_flag.evaluation", "feature_flag.key", "feature_flag.result.variant",
                "feature_flag.provider.name"),
}

# Written by the extensions? They must not (FR-014, UC-007 BR-001).
EXTENSION_ATTRS = ("otelfeature.sample_ratio",)


def _failing_and_traced(service: str):
    def check(trace) -> str | None:
        server = next((s for s in trace if s.kind == "server" and s.service == service), None)
        if server is None:
            return f"no {service} server span"
        if server.status != "error":
            return f"{service} server span status {server.status}, want error:\n{describe(trace)}"
        return None
    return check


def _flag_explains_failure(service: str):
    """TC-005 steps 6-7 / UC-007 (A2 for geocode): a span of the failed
    request carries the hook's evaluation event for the service's fault flag,
    under the names that service's hook writes."""
    flag = FAULT_FLAGS[service]
    event, key, variant, provider = HOOK_NAMES[service]

    def check(trace) -> str | None:
        if problem := _failing_and_traced(service)(trace):
            return problem
        events = [(s, attrs) for s in trace for name, attrs in s.events
                  if name == event and attrs.get(key) == flag]
        if not events:
            names = sorted({name for s in trace for name, _ in s.events})
            return f"no {event!r} event for {flag} (events seen: {names}):\n{describe(trace)}"
        span, attrs = events[0]
        if span.service != service:
            return f"hook event on a {span.service} span"
        if attrs.get(variant) != "outage" or not attrs.get(provider):
            return f"hook event attributes {attrs}, want {variant}='outage' and a {provider}"
        return None
    return check


@pytest.mark.parametrize("failing", ["weather", "geocode"])
def test_tc005_control_loop(step: Step, flags: Flags, failing: str):
    other = OTHER[failing]
    traffic = Traffic(step, failing)

    # Start: the loop rule, no failures. Production is at 0.0, so neither
    # service traces its roots, and both error rates are 0.0.
    flags.write(_loop_config(flags, failing, failure="none"))
    step.wait_tracing(failing, traced=False, send=traffic)
    step.wait_tracing(other, traced=False)
    # Count the other service only from here: requests sent while the flip
    # to 0.0 was still propagating may legitimately have been traced.
    traffic.other_tag = f"{step.id}-{other}-{uuid.uuid4().hex[:6]}"

    # Steps 2-5: inject failures. Once the next collections put the failing
    # service's error rate above 0.05, its roots are sampled: a failing
    # request (span status ERROR) is traced.
    flags.write(_loop_config(flags, failing, failure="outage"))
    latency = step.wait_for_trace(traffic, _failing_and_traced(failing), timeout=LOOP_TIMEOUT)
    print(f"{failing} sampled up {latency:.1f}s after the failures started")

    # Still sampled a few intervals later, with traffic going on (not a
    # one-off), and the trace says which flag failed it (steps 6-7, UC-007).
    step.wait_for_trace(traffic, _flag_explains_failure(failing), timeout=LOOP_TIMEOUT)

    # FR-014 / UC-007 BR-001, over every span exported so far in the session
    # (both services, sampled down and up): no span carries attributes the
    # extensions would have written. Outside the barrier, so one violating
    # trace can't be skipped. Only the services the extensions run in:
    # flagd's own spans (flagSync) carry feature_flag.* attributes of their own.
    written = [s for s in step.spans.spans
               if s.service in ("geocode", "weather")
               and any(k.startswith("feature_flag.") or k in EXTENSION_ATTRS for k in s.attrs)]
    assert not written, f"span attributes the extensions must not write:\n{describe(written)}"

    # The other service had error-free traffic all along (rate 0.0): none of
    # it traced.
    leaked = [s for s in step.spans.for_step(traffic.other_tag)]
    assert not leaked, f"{other} sampled although it has no errors:\n{describe(leaked)}"

    # Steps 8/9: stop the failures. The failing service's traffic keeps
    # going (now error-free 404s), so its rate falls to a measured 0.0 and it
    # is back at the environment ratio.
    flags.write(_loop_config(flags, failing, failure="none"))
    step.wait_tracing(failing, traced=False, send=traffic, timeout=LOOP_TIMEOUT)
    leaked = step.quiet(lambda s: s.step == traffic.other_tag)
    assert not leaked, f"{other} sampled at some point:\n{describe(leaked)}"
