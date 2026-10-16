"""Shared trace-shape checks used by several tests."""

from __future__ import annotations

from spans import Span, tree_problem

APP_SERVICES = ("geocode", "weather")


def is_db(span: Span) -> bool:
    return span.kind == "client" and ("db.system" in span.attrs or "db.system.name" in span.attrs)


def is_stub_call(span: Span) -> bool:
    return span.kind == "client" and span.attrs.get("server.address") == "stub-apis"


def complete_problem(trace: list[Span], service: str) -> str | None:
    """What a cache-missing request's trace still lacks, or None: a server
    span of `service`, a DB client span, an HTTP client span to the stub,
    and a connected tree with one root."""
    if not any(s.kind == "server" and s.service == service for s in trace):
        return f"no {service} server span"
    if not any(is_db(s) for s in trace):
        return f"no DB client span in {service} trace"
    if not any(is_stub_call(s) for s in trace):
        return f"no HTTP client span to stub-apis in {service} trace"
    return tree_problem(trace)


def by_root_service(traces: dict[str, list[Span]]) -> dict[str, list[Span]]:
    """Map service name -> trace, for traces whose root span is known."""
    out = {}
    for trace in traces.values():
        root = next((s for s in trace if s.is_root), None)
        if root is not None:
            out[root.service] = trace
    return out
