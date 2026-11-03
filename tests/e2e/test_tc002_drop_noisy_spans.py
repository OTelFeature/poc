"""TC-002: drop INTERNAL spans by span kind (Demo 2), then health-check and
database spans by rule (Demo 3).

docs/spec/test_cases/TC-002-drop-noisy-spans.md, UC-002.

`test_tc002_span_kind_level` applies the stage preset `02-quiet-noise`
(telemetryLevel IO, no targeting) and checks that neither service exports an
INTERNAL span while server, client and DB spans stay, re-attached to their
real parent (UC-002 steps 1 to 4, BR-008; OTelFeature/poc#110).

`test_tc002_drop_noisy_spans` applies the recordSpan flag of the stage preset
`03-semconv-rules` (targeting on the semconv context) on the baseline:

- rule A: service.name=geocode, span.kind=server, url.path=/health → off
- rule B: service.name=weather, otel.scope.name=io.opentelemetry.jdbc → off

and checks that exactly those spans disappear, that everything else stays
with correctly parented trees, and that the baseline brings them back. The
preset's 0.1 production sample ratio is left out, so every absence here is
the rule's; test_tc006_stage_progression runs the preset as it is.

Rule B is on the instrumentation scope, which a Java Sampler is never told,
so the processor enforces it in both Java modes (UC-002 A4). The stage rules
alone would therefore never exercise the Java sampler's DROP path.
`test_tc002_sampler_paths` adds a non-stage variation that does: a weather
root (`/health` server span) and weather DB leaves by `db.system`, plus
a proxied geocode request with downstream calls (UC-002 A6).
"""

from __future__ import annotations

import uuid

from checks import complete_problem, is_db, is_stub_call
from conftest import FLIP_BUDGET_SECONDS, GEOCODE_URL, WEATHER_URL, Step
from flags import Flags
from spans import STEP_HEADER, Span, describe, tree_problem, wait_until

JDBC_SCOPE = "io.opentelemetry.jdbc"


def _traceparent() -> tuple[str, str, str]:
    """A sampled parent, as sent by another traced service in front of us:
    (header value, trace id, parent span id)."""
    trace_id, parent_id = uuid.uuid4().hex, uuid.uuid4().hex[:16]
    return f"00-{trace_id}-{parent_id}-01", trace_id, parent_id


def _is_jdbc(span: Span) -> bool:
    return span.scope == JDBC_SCOPE or (span.service == "weather" and is_db(span))


def _instance(span: Span) -> str | None:
    return span.resource.get("service.instance.id")


def _server(trace: list[Span], service: str, path: str) -> Span | None:
    return next((s for s in trace if s.kind == "server" and s.service == service
                 and s.attrs.get("url.path") == path), None)


def _weather_request(step: Step, city: str):
    """send(headers) for wait_for_trace: one cache-missing /weather request."""
    def send(headers: dict) -> None:
        city_ = f"{city}-{uuid.uuid4().hex[:6]}"
        r = step.http.post(f"{WEATHER_URL}/weather", json={"city": city_, "country": "nowhere"},
                           headers=headers)
        assert r.status_code == 404, f"/weather: HTTP {r.status_code}"
    return send


def _weather_trace_problem(trace: list[Span], want_db: bool, db_check=_is_jdbc) -> str | None:
    """A cache-missing /weather trace: server and HTTP client spans, DB spans
    present or absent as wanted, tree connected."""
    if _server(trace, "weather", "/weather") is None:
        return f"no weather /weather server span:\n{describe(trace)}"
    if not any(is_stub_call(s) for s in trace):
        return f"no HTTP client span to stub-apis in weather trace:\n{describe(trace)}"
    db = [s for s in trace if db_check(s)]
    if want_db and not db:
        return f"no DB spans in weather trace:\n{describe(trace)}"
    if not want_db and db:
        return f"DB spans still exported:\n{describe(db)}"
    return tree_problem(trace)


def _geocode_request(step: Step, city: str):
    """send(headers) for wait_for_trace: one cache-missing /geocode request."""
    def send(headers: dict) -> None:
        city_ = f"{city}-{uuid.uuid4().hex[:6]}"
        r = step.http.post(f"{GEOCODE_URL}/geocode", json={"city": city_, "country": "nowhere"},
                           headers=headers)
        assert r.status_code == 404, f"/geocode: HTTP {r.status_code}"
    return send


def _io_problem(trace: list[Span], service: str) -> str | None:
    """A cache-missing request's trace under telemetryLevel IO: no INTERNAL
    span, server, DB and stub client spans present, and the client spans
    re-attached to the server span (their INTERNAL parents are gone)."""
    if internal := [s for s in trace if s.kind == "internal"]:
        return f"{service}: INTERNAL spans still exported:\n{describe(internal)}"
    if missing := complete_problem(trace, service):
        return f"{service}: {missing}:\n{describe(trace)}"
    server = next(s for s in trace if s.kind == "server" and s.service == service)
    if stray := [s for s in trace if s.kind == "client" and s.parent_id != server.span_id]:
        return f"{service}: client spans not under the server span:\n{describe(stray)}"
    return None


def _full_problem(trace: list[Span], service: str) -> str | None:
    """The same trace at baseline: the INTERNAL spans are back."""
    if not any(s.kind == "internal" for s in trace):
        return f"{service}: no INTERNAL span yet:\n{describe(trace)}"
    return complete_problem(trace, service)


def test_tc002_span_kind_level(step: Step, flags: Flags):
    """Demo 2 (UC-002 steps 1 to 4, TC-002 item 19): telemetryLevel IO
    leaves out every INTERNAL span (geocode: the ASGI http receive/send spans
    and geocode.resolve; weather: the controller and error-handling spans)
    and nothing else."""
    city = f"e2e-{step.id[:12]}"

    # Steps 1/2: barriers in both services, on a request that has INTERNAL
    # spans at baseline.
    flags.apply("02-quiet-noise")
    for service, send in (("geocode", _geocode_request(step, city)),
                          ("weather", _weather_request(step, city))):
        latency = step.wait_for_trace(send, lambda t, s=service: _io_problem(t, s))
        assert latency <= FLIP_BUDGET_SECONDS, f"{service} INTERNAL spans gone after {latency:.1f}s"

    step.remark()
    assert step.health(GEOCODE_URL).status_code == 200
    assert step.health(WEATHER_URL).status_code == 200
    assert step.geocode(city, "nowhere").status_code == 404
    assert step.weather(city, "nowhere").status_code == 404

    def kept_problem() -> str | None:
        traces = list(step.traces().values())
        for service, path in (("geocode", "/geocode"), ("weather", "/weather")):
            trace = next((t for t in traces if _server(t, service, path)), None)
            if trace is None:
                return f"no {service} {path} trace yet"
            if problem := _io_problem(trace, service):
                return problem
        for service in ("geocode", "weather"):
            # /health stays traced: one server span, its INTERNAL children gone
            if not any(_server(t, service, "/health") for t in traces):
                return f"{service} /health no longer traced (IO only leaves out INTERNAL spans)"
        return None

    wait_until(kept_problem, timeout=10.0)

    # Healthchecks keep calling /health meanwhile: under IO no request of
    # either service may export an INTERNAL span.
    leaked = step.quiet(lambda s: _instance(s) in ("geocode", "weather") and s.kind == "internal")
    assert not leaked, f"INTERNAL spans under telemetryLevel IO:\n{describe(leaked)}"

    # Baseline: the INTERNAL spans come back.
    flags.apply("00-baseline")
    for service, send in (("geocode", _geocode_request(step, city)),
                          ("weather", _weather_request(step, city))):
        latency = step.wait_for_trace(send, lambda t, s=service: _full_problem(t, s))
        assert latency <= FLIP_BUDGET_SECONDS, f"{service} INTERNAL spans back after {latency:.1f}s"


def _semconv_drops(flags: Flags) -> dict:
    """00-baseline with the recordSpan flag of 03-semconv-rules, as it is."""
    config = flags.preset("00-baseline")
    config["flags"]["recordSpan"] = flags.preset("03-semconv-rules")["flags"]["recordSpan"]
    return config


def test_tc002_drop_noisy_spans(step: Step, flags: Flags):
    city = f"e2e-{step.id[:12]}"

    # Step 3: apply the rules. Barriers in both services: geocode's /health
    # goes untraced, weather's /weather traces lose their DB spans.
    flags.write(_semconv_drops(flags))
    latency = step.wait_tracing("geocode", traced=False, path="/health")
    assert latency <= FLIP_BUDGET_SECONDS, f"geocode /health dropped after {latency:.1f}s"
    latency = step.wait_for_trace(_weather_request(step, city),
                                  lambda t: _weather_trace_problem(t, want_db=False))
    assert latency <= FLIP_BUDGET_SECONDS, f"weather DB spans dropped after {latency:.1f}s"

    step.remark()
    assert step.health(GEOCODE_URL).status_code == 200
    assert step.health(WEATHER_URL).status_code == 200
    assert step.geocode(city, "nowhere").status_code == 404
    assert step.weather(city, "nowhere").status_code == 404

    # Proxied health check: an incoming request with a sampled remote parent
    # is an entry span, so it counts as a root (UC-002 A6) and is dropped
    # with everything under it (FastAPI's "http send" children included).
    traceparent, proxied_trace, _ = _traceparent()
    r = step.http.get(f"{GEOCODE_URL}/health", headers={"traceparent": traceparent})
    assert r.status_code == 200

    # Step 4: geocode /geocode traces unchanged (complete, DB spans included).
    # Step 5: weather /weather traces keep server and HTTP client spans, no
    # DB spans, no orphans; weather's own /health is still traced.
    geocode_traces: set[str] = set()

    def kept_problem() -> str | None:
        traces = step.traces()
        geocode = next((t for t in traces.values() if _server(t, "geocode", "/geocode")), None)
        if geocode is None:
            return "no geocode /geocode trace yet"
        if missing := complete_problem(geocode, "geocode"):
            return f"geocode: {missing}:\n{describe(geocode)}"
        if not any(s.name == "geocode.resolve" for s in geocode):
            return f"geocode: geocode.resolve span missing:\n{describe(geocode)}"
        weather = next((t for t in traces.values() if _server(t, "weather", "/weather")), None)
        if weather is None:
            return "no weather /weather trace yet"
        if missing := _weather_trace_problem(weather, want_db=False):
            return f"weather: {missing}"
        if not any(_server(t, "weather", "/health") for t in traces.values()):
            return "weather /health no longer traced (only geocode's should be dropped)"
        geocode_traces.add(geocode[0].trace_id)
        return None

    wait_until(kept_problem, timeout=10.0)

    # After the mark, geocode serves only /health (rule A) and the one
    # /geocode request, so any other geocode span is a leak: a dropped
    # /health server span whose children (no url.path on them) leaked.
    dropped = step.quiet(
        lambda s: (_instance(s) == "geocode" and s.trace_id not in geocode_traces)
        or (_instance(s) == "weather" and _is_jdbc(s))
        or s.trace_id == proxied_trace
    )
    assert not dropped, f"spans the rules should have dropped:\n{describe(dropped)}"

    # Steps 6/7: remove the rules; health checks and DB spans come back.
    flags.apply("00-baseline")
    latency = step.wait_tracing("geocode", traced=True, path="/health")
    assert latency <= FLIP_BUDGET_SECONDS, f"geocode /health back after {latency:.1f}s"
    latency = step.wait_for_trace(
        _weather_request(step, city),
        lambda t: _weather_trace_problem(t, want_db=True, db_check=lambda s: s.scope == JDBC_SCOPE))
    assert latency <= FLIP_BUDGET_SECONDS, f"weather DB spans back after {latency:.1f}s"

    # Positive control for the proxied check: at baseline the same kind of
    # request is traced, continues the sent trace, has the sent span as its
    # parent and has children. So the drop above was the remote-parent root
    # rule, not a request that never took part in the trace.
    traceparent, trace_id, parent_id = _traceparent()
    r = step.http.get(f"{GEOCODE_URL}/health", headers={"traceparent": traceparent})
    assert r.status_code == 200

    def control_problem() -> str | None:
        trace = step.spans.traces([trace_id]).get(trace_id, [])
        server = _server(trace, "geocode", "/health")
        if server is None:
            return f"proxied /health not traced at baseline:\n{describe(trace)}"
        if server.parent_id != parent_id:
            return f"proxied /health parent {server.parent_id}, sent {parent_id}"
        if not any(s.parent_id == server.span_id for s in trace):
            return f"proxied /health has no children:\n{describe(trace)}"
        return tree_problem(trace, remote_parents=[parent_id])

    wait_until(control_problem, timeout=FLIP_BUDGET_SECONDS)


def _variation(flags: Flags) -> dict:
    """The baseline with recordSpan rules the Java sampler can decide."""
    config = flags.preset("00-baseline")
    eq = lambda key, value: {"==": [{"var": key}, value]}  # noqa: E731
    config["flags"]["recordSpan"]["targeting"] = {"if": [
        {"or": [
            # weather root: an entry span the sampler can DROP
            {"and": [eq("service.name", "weather"), eq("span.kind", "server"), eq("url.path", "/health")]},
            # weather DB leaves by a span attribute the sampler is told. The
            # Java agent 2.31 emits the old `db.system` (the stable
            # `db.system.name` needs OTEL_SEMCONV_STABILITY_OPT_IN=database).
            {"and": [eq("service.name", "weather"), eq("db.system", "postgresql")]},
            # geocode entry span with downstream calls (UC-002 A6)
            {"and": [eq("service.name", "geocode"), eq("span.kind", "server"), eq("url.path", "/geocode")]},
        ]},
        "off", "on",
    ]}
    return config


def test_tc002_sampler_paths(step: Step, flags: Flags):
    """Root and leaf drops the Java sampler can make (TC-002 V4/V11), and a
    dropped remote-parent entry span that takes its downstream calls along
    (V9). Runs in both Java modes; in sampler mode it is the sampler's DROP
    path, in processor mode the processor's."""
    city = f"e2e-{step.id[:12]}"
    flags.write(_variation(flags))
    latency = step.wait_tracing("weather", traced=False, path="/health")
    assert latency <= FLIP_BUDGET_SECONDS, f"weather /health dropped after {latency:.1f}s"
    step.wait_for_trace(
        _weather_request(step, city),
        lambda t: _weather_trace_problem(t, want_db=False,
                                         db_check=lambda s: "db.system.name" in s.attrs or "db.system" in s.attrs))

    step.remark()
    assert step.health(WEATHER_URL).status_code == 200
    assert step.weather(city, "nowhere").status_code == 404
    traceparent, proxied_trace, _ = _traceparent()
    r = step.http.post(f"{GEOCODE_URL}/geocode", json={"city": f"{city}-p", "country": "nowhere"},
                       headers={"traceparent": traceparent})
    assert r.status_code == 404

    def kept_problem() -> str | None:
        weather = next((t for t in step.traces().values() if _server(t, "weather", "/weather")), None)
        if weather is None:
            return "no weather /weather trace yet"
        return _weather_trace_problem(weather, want_db=False)

    wait_until(kept_problem, timeout=10.0)

    dropped = step.quiet(
        lambda s: (_instance(s) == "weather" and (s.attrs.get("url.path") == "/health"
                                                  or "db.system.name" in s.attrs
                                                  or "db.system" in s.attrs))
        # the whole proxied /geocode request: server, geocode.resolve, DB, httpx
        or s.trace_id == proxied_trace
    )
    assert not dropped, f"spans the variation should have dropped:\n{describe(dropped)}"
