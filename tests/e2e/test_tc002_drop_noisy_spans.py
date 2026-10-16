"""TC-002: drop health-check and database spans by rule (Demo 2).

docs/spec/test_cases/TC-002-drop-noisy-spans.md, UC-002.

`test_tc002_drop_noisy_spans` applies the stage preset `02-quiet-noise`
(recordSpan targeting on the semconv context):

- rule A: service.name=geocode, span.kind=server, url.path=/health → off
- rule B: service.name=weather, otel.scope.name=io.opentelemetry.jdbc → off

and checks that exactly those spans disappear, that everything else stays
with correctly parented trees, and that the baseline brings them back.

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


def test_tc002_drop_noisy_spans(step: Step, flags: Flags):
    city = f"e2e-{step.id[:12]}"

    # Step 1: apply the rules. Barriers in both services: geocode's /health
    # goes untraced, weather's /weather traces lose their DB spans.
    flags.apply("02-quiet-noise")
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

    # Step 2: geocode /geocode traces unchanged (complete, DB spans included).
    # Step 3: weather /weather traces keep server and HTTP client spans, no
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

    # Steps 4/5: remove the rules; health checks and DB spans come back.
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
    """02-quiet-noise with recordSpan rules the Java sampler can decide."""
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
