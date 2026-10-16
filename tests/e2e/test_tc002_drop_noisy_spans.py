"""TC-002: drop health-check and database spans by rule (Demo 2).

docs/spec/test_cases/TC-002-drop-noisy-spans.md, UC-002. Applies the
`02-quiet-noise` preset (recordSpan targeting on the semconv context):

- rule A: service.name=geocode, span.kind=server, url.path=/health → off
- rule B: service.name=weather, otel.scope.name=io.opentelemetry.jdbc → off

and checks that exactly those spans disappear, that everything else stays
with correctly parented trees, and that the baseline brings them back.
"""

from __future__ import annotations

import uuid

from checks import by_root_service, complete_problem, is_db, is_stub_call
from conftest import FLIP_BUDGET_SECONDS, GEOCODE_URL, WEATHER_URL, Step
from flags import Flags
from spans import STEP_HEADER, Span, describe, tree_problem, wait_until

JDBC_SCOPE = "io.opentelemetry.jdbc"

# Sent by "another traced service" in front of geocode: a sampled parent.
def _traceparent() -> tuple[str, str]:
    trace_id, parent_id = uuid.uuid4().hex, uuid.uuid4().hex[:16]
    return f"00-{trace_id}-{parent_id}-01", trace_id


def _is_jdbc(span: Span) -> bool:
    return span.scope == JDBC_SCOPE or (span.service == "weather" and is_db(span))


def _weather_without_db_problem(trace: list[Span]) -> str | None:
    """A cache-missing /weather trace under rule B: server and HTTP client
    spans kept, no DB spans, tree connected."""
    if not any(s.kind == "server" and s.service == "weather" for s in trace):
        return "no weather server span"
    if not any(is_stub_call(s) for s in trace):
        return "no HTTP client span to stub-apis in weather trace"
    db = [s for s in trace if _is_jdbc(s)]
    if db:
        return f"DB spans still exported:\n{describe(db)}"
    return tree_problem(trace)


def test_tc002_drop_noisy_spans(step: Step, flags: Flags):
    city = f"e2e-{step.id[:12]}"

    # Step 1: apply the rules; wait until geocode's health checks go quiet.
    flags.apply("02-quiet-noise")
    latency = step.wait_tracing("geocode", traced=False, path="/health")
    assert latency <= FLIP_BUDGET_SECONDS, f"geocode /health dropped after {latency:.1f}s"

    step.remark()
    assert step.health(GEOCODE_URL).status_code == 200
    assert step.health(WEATHER_URL).status_code == 200
    assert step.geocode(city, "nowhere").status_code == 404
    assert step.weather(city, "nowhere").status_code == 404

    # Proxied health check: an incoming request with a sampled remote parent
    # is an entry span, so it counts as a root (UC-002 A6) and is dropped.
    traceparent, proxied_trace = _traceparent()
    r = step.http.get(f"{GEOCODE_URL}/health", headers={"traceparent": traceparent})
    assert r.status_code == 200

    # Step 2: geocode /geocode traces unchanged (complete, DB spans included).
    # Step 3: weather /weather traces keep server and HTTP client spans, no
    # DB spans, no orphans; weather's own /health is still traced.
    def kept_problem() -> str | None:
        by_service = by_root_service(step.traces())
        geocode = by_service.get("geocode")
        if geocode is None:
            return "no geocode /geocode trace yet"
        if missing := complete_problem(geocode, "geocode"):
            return f"geocode: {missing}:\n{describe(geocode)}"
        weather = [t for t in step.traces().values()
                   if any(s.kind == "server" and s.service == "weather"
                          and s.attrs.get("url.path") == "/weather" for s in t)]
        if not weather:
            return "no weather /weather trace yet"
        if missing := _weather_without_db_problem(weather[0]):
            return f"weather: {missing}:\n{describe(weather[0])}"
        weather_health = [s for s in step.since_mark()
                          if s.service == "weather" and s.kind == "server"
                          and s.attrs.get("url.path") == "/health" and s.step == step.id]
        if not weather_health:
            return "weather /health no longer traced (only geocode's should be dropped)"
        return None

    wait_until(kept_problem, timeout=10.0)

    dropped = step.quiet(
        lambda s: (s.resource.get("service.instance.id") == "geocode"
                   and s.attrs.get("url.path") == "/health")
        or (s.resource.get("service.instance.id") == "weather" and _is_jdbc(s))
        or s.trace_id == proxied_trace
    )
    assert not dropped, f"spans the rules should have dropped:\n{describe(dropped)}"

    # Steps 4/5: remove the rules; health checks and DB spans come back.
    flags.apply("00-baseline")
    latency = step.wait_tracing("geocode", traced=True, path="/health")
    assert latency <= FLIP_BUDGET_SECONDS, f"geocode /health back after {latency:.1f}s"

    restore = step.http.post(f"{WEATHER_URL}/weather",
                             json={"city": f"{city}-back", "country": "nowhere"},
                             headers={STEP_HEADER: f"{step.id}-back"})
    assert restore.status_code == 404

    def restored_problem() -> str | None:
        spans = step.spans.for_step(f"{step.id}-back")
        if not any(_is_jdbc(s) for s in spans):
            return f"no DB spans back in weather yet:\n{describe(spans)}"
        return tree_problem(spans)

    wait_until(restored_problem, timeout=FLIP_BUDGET_SECONDS)
