"""Flagsmith mode through the real Edge Proxy and flagd: TC-008 items 3 to 5.

Runs in compose.test.yaml (`make flagsmith-test`): a stub of Flagsmith Cloud
(otelfeature_flagsmith.stub_cloud) applies each preset command's CLI calls
one by one, each with its own real-time event; the Flagsmith proxy follows
the stream and serves flagd, and flagd's OFREP endpoint is what the preset
command confirms against (UC-008 BR-010).
"""

import json
import os
import time

import httpx
import pytest

from otelfeature_flagsmith import PRESETS, STAGE_ORDER

STUB = os.environ["STUB_URL"]
PROXY = os.environ["PROXY_URL"]
OFREP = os.environ["FLAGD_OFREP_URL"]
CLIENT_KEY = os.environ["FLAGSMITH_CLIENT_KEY"]
# UC-008 BR-011: from the event of the last write to flagd serving the preset.
BOUND = 2.0


def nest(flat: dict) -> dict:
    """Dotted semconv keys nested by segment, as the extensions build the context (FR-005)."""
    nested: dict = {}
    for key, value in flat.items():
        *path, leaf = key.split(".")
        node = nested
        for part in path:
            node = node.setdefault(part, {})
        node[leaf] = value
    return nested


def served_preset() -> str | None:
    body = httpx.post(f"{OFREP}/ofrep/v1/evaluate/flags", json={"context": {}}, timeout=2).json()
    return next(((f.get("metadata") or {}).get("preset") for f in body.get("flags", [])), None)


def wait_served(name: str, timeout: float) -> float:
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        try:
            if served_preset() == name:
                return time.time()
        except httpx.HTTPError:
            pass
        time.sleep(0.05)
    pytest.fail(f"flagd does not serve {name} after {timeout}s (serves {served_preset()!r})")


def evaluate(key: str, **attributes):
    response = httpx.post(f"{OFREP}/ofrep/v1/evaluate/flags/{key}", json={"context": nest(attributes)}, timeout=2)
    return response.json()["value"]


def proxy_flag_set() -> dict:
    return httpx.get(f"{PROXY}/api/v1/flagd/flags.json", headers={"Authorization": f"Bearer {CLIENT_KEY}"},
                     timeout=2).json()


def apply(name: str) -> dict:
    response = httpx.post(f"{STUB}/stub/apply/{name}", timeout=30)
    response.raise_for_status()
    return response.json()


def fetches() -> int:
    return httpx.get(f"{STUB}/stub/state", timeout=2).json()["fetches"]


@pytest.fixture(scope="module", autouse=True)
def stack_at_baseline():
    httpx.post(f"{STUB}/stub/realtime/on", timeout=2)
    apply("00-baseline")
    wait_served("00-baseline", 30)


PROD_WEATHER = {"service.name": "weather", "deployment.environment.name": "production"}
PROD_GEOCODE = {"service.name": "geocode", "deployment.environment.name": "production"}
STAGING_WEATHER = {"service.name": "weather", "deployment.environment.name": "staging"}

# What flagd answers after each preset, for a few spans of the demo (the full
# span table is src/flagd/test_presets.py, against the same flag sets).
EXPECTED = {
    "00-baseline": [("otelEnabled", {}, True), ("traceSampleRatio", PROD_GEOCODE, 1.0)],
    "01-otel-off": [("otelEnabled", {}, False)],
    "02-quiet-noise": [("otelEnabled", {}, True), ("telemetryLevel", {}, "IO"),
                       ("recordSpan", {**PROD_GEOCODE, "span.kind": "server", "url.path": "/health"}, True)],
    "03-semconv-rules": [("recordSpan", {**PROD_GEOCODE, "span.kind": "server", "url.path": "/health"}, False),
                         ("recordSpan", {**PROD_WEATHER, "otel.scope.name": "io.opentelemetry.jdbc"}, False),
                         ("recordSpan", {**PROD_WEATHER, "span.kind": "server", "url.path": "/health"}, True),
                         ("traceSampleRatio", PROD_WEATHER, 0.1), ("traceSampleRatio", STAGING_WEATHER, 1.0)],
    "03a-weather-boost": [("traceSampleRatio", PROD_WEATHER, 0.5), ("traceSampleRatio", PROD_GEOCODE, 0.1)],
    "03b-incident": [("weatherUpstreamFailure", {}, 0.5),
                     ("traceSampleRatio", {**PROD_WEATHER, "otelfeature.http.server.error_rate": 0.3}, 1.0),
                     ("traceSampleRatio", PROD_WEATHER, 0.5)],
}


def test_pushed_progression():
    """Item 3: each preset, pushed, is served within the bound and equals its file."""
    report = []
    for name in STAGE_ORDER + ["03a-weather-boost"]:
        before = fetches()
        result = apply(name)
        lag = wait_served(name, 10) - result["updated_at"]
        report.append(f"{name}: {result['calls']} CLI calls, served {lag:.2f}s after the last event, "
                      f"{fetches() - before} document fetches")
        assert lag <= BOUND, report[-1]
        assert proxy_flag_set() == json.loads((PRESETS / f"{name}.json").read_text()), name
        for key, attributes, want in EXPECTED[name]:
            assert evaluate(key, **attributes) == want, (name, key, attributes)
    print("\n".join(report))


def test_rejected_environment():
    """Item 5: an override the translation rejects leaves flagd on the previous preset."""
    apply("03a-weather-boost")
    wait_served("03a-weather-boost", 10)
    bad = ["flag", "update", "traceSampleRatio", "--segment", "production", "--value", "0.3",
           "--type", "string", "--enable"]
    before = fetches()
    httpx.post(f"{STUB}/stub/cli", json=bad, timeout=5).raise_for_status()
    time.sleep(BOUND + 1)
    assert fetches() > before, "the proxy did not fetch the rejected document"
    assert served_preset() == "03a-weather-boost"
    assert evaluate("traceSampleRatio", **PROD_GEOCODE) == 0.1
    assert proxy_flag_set() == json.loads((PRESETS / "03a-weather-boost.json").read_text())
    # A preset command repairs it.
    apply("00-baseline")
    wait_served("00-baseline", 10)
    assert evaluate("traceSampleRatio", **PROD_GEOCODE) == 1.0


def test_poll_fallback():
    """Item 4: without the real-time stream, the proxy's poll still brings the change."""
    httpx.post(f"{STUB}/stub/realtime/off", timeout=2)
    try:
        apply("03-semconv-rules")
        # Poll every 3 s in compose.test.yaml, then flagd's 1 s poll.
        wait_served("03-semconv-rules", 3 + 1 + BOUND)
    finally:
        httpx.post(f"{STUB}/stub/realtime/on", timeout=2)
