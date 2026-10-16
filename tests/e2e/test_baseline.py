"""Baseline: with the neutral flags, both services export complete traces.

Not a spec test case of its own; every TC starts from this state, so if this
fails nothing else is meaningful.
"""

from __future__ import annotations

from conftest import Step
from spans import Span, describe, tree_problem, wait_until

RESOURCE = {
    "service.namespace": "otelfeature",
    "deployment.environment.name": "production",
}


def _is_db(span: Span) -> bool:
    return span.kind == "client" and (
        "db.system" in span.attrs or "db.system.name" in span.attrs
    )


def _is_stub_call(span: Span) -> bool:
    return span.kind == "client" and span.attrs.get("server.address") == "stub-apis"


def _complete(trace: list[Span], service: str) -> str | None:
    """What this request's trace still lacks, or None."""
    servers = [s for s in trace if s.kind == "server" and s.service == service]
    if not servers:
        return f"no {service} server span"
    if not any(_is_db(s) for s in trace):
        return f"no DB client span in {service} trace"
    if not any(_is_stub_call(s) for s in trace):
        return f"no HTTP client span to stub-apis in {service} trace"
    return tree_problem(trace)


def test_baseline(step: Step):
    # An unknown city misses every cache, so each request reads the DB and
    # calls the external API (the stub), which then answers "not found".
    city = f"e2e-{step.id[:12]}"
    assert step.geocode(city, "nowhere").status_code == 404
    assert step.weather(city, "nowhere").status_code == 404

    def problem() -> str | None:
        traces = step.traces()
        by_service = {}
        for trace in traces.values():
            root = next((s for s in trace if s.is_root), None)
            if root is not None:
                by_service[root.service] = trace
        for service in ("geocode", "weather"):
            trace = by_service.get(service)
            if trace is None:
                return f"no {service} trace for step yet"
            missing = _complete(trace, service)
            if missing:
                return f"{missing}:\n{describe(trace)}"
        return None

    wait_until(problem, timeout=10.0)

    for trace in step.traces().values():
        for span in trace:
            for key, value in RESOURCE.items():
                assert span.resource.get(key) == value, f"{key} on {span}: {span.resource}"
            assert span.resource.get("service.version"), f"service.version missing on {span}"
        root = next(s for s in trace if s.is_root)
        assert root.attrs.get("url.path") in ("/geocode", "/weather"), f"url.path on {root}: {root.attrs}"
