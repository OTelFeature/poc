"""Reading the spans the collector wrote, and asserting on them.

The e2e collector (collector.yaml) appends every export request it receives
as one JSON line (OTLP/JSON) to a file. SpanLog tails that file, so a test
sees every span that reached the collector: "no span of this kind since
mark M" is an exact statement, not a sampling of a backend's search results.
Take M after the flag flip has taken effect (Step.remark()), not before.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

# OTLP span kinds (opentelemetry-proto trace.proto).
KINDS = {0: "unspecified", 1: "internal", 2: "server", 3: "client", 4: "producer", 5: "consumer"}
STATUS = {0: "unset", 1: "ok", 2: "error"}

STEP_HEADER = "x-e2e-step"


def _value(v: dict):
    if not v:
        return None
    (kind, val), = v.items()
    if kind == "arrayValue":
        return [_value(x) for x in val.get("values", [])]
    if kind == "kvlistValue":
        return {kv["key"]: _value(kv.get("value", {})) for kv in val.get("values", [])}
    if kind == "intValue":
        return int(val)
    return val


def _attrs(items: Iterable[dict]) -> dict:
    return {a["key"]: _value(a.get("value", {})) for a in items or []}


@dataclass(frozen=True)
class Span:
    trace_id: str
    span_id: str
    parent_id: str
    name: str
    kind: str
    status: str
    scope: str
    attrs: dict = field(hash=False, compare=False)
    resource: dict = field(hash=False, compare=False)

    @property
    def service(self) -> str:
        return self.resource.get("service.name", "")

    @property
    def is_root(self) -> bool:
        return not self.parent_id

    @property
    def step(self) -> str | None:
        """The x-e2e-step header value, if the instrumentation recorded it.

        Recorded as http.request.header.x-e2e-step (stable semconv) or with
        underscores (older Python naming); the value is a list of strings.
        """
        for key, value in self.attrs.items():
            if key.startswith("http.request.header.") and key[20:].replace("_", "-") == STEP_HEADER:
                return value[0] if isinstance(value, list) and value else value
        return None

    def __str__(self) -> str:
        parent = self.parent_id[:8] if self.parent_id else "root"
        return f"{self.service}/{self.kind} {self.name!r} [{self.scope}] {self.span_id[:8]}<-{parent}"


class SpanLog:
    """Incrementally parses the collector's JSON-lines span file."""

    def __init__(self, path: Path):
        self.path = path
        self._offset = 0
        self._partial = b""
        self.spans: list[Span] = []

    def refresh(self) -> None:
        if not self.path.exists():
            return
        if self.path.stat().st_size < self._offset:
            # The file exporter truncates on start: the collector restarted.
            self._offset, self._partial = 0, b""
        with self.path.open("rb") as f:
            f.seek(self._offset)
            data = f.read()
        self._offset += len(data)
        data = self._partial + data
        *lines, self._partial = data.split(b"\n")
        for line in lines:
            if line.strip():
                self.spans.extend(_parse(json.loads(line)))

    def mark(self) -> int:
        """Position to count from: spans exported after this call."""
        self.refresh()
        return len(self.spans)

    def since(self, mark: int) -> list[Span]:
        self.refresh()
        return self.spans[mark:]

    def traces(self, trace_ids: Iterable[str]) -> dict[str, list[Span]]:
        """All spans seen so far for these traces, by trace id."""
        self.refresh()
        wanted = set(trace_ids)
        out: dict[str, list[Span]] = defaultdict(list)
        for span in self.spans:
            if span.trace_id in wanted:
                out[span.trace_id].append(span)
        return out

    def for_step(self, step_id: str) -> list[Span]:
        """Every span of every trace whose server span carries this step id."""
        self.refresh()
        ids = {s.trace_id for s in self.spans if s.kind == "server" and s.step == step_id}
        return [s for s in self.spans if s.trace_id in ids]


def _parse(request: dict) -> list[Span]:
    out = []
    for rs in request.get("resourceSpans", []):
        resource = _attrs(rs.get("resource", {}).get("attributes"))
        for ss in rs.get("scopeSpans", []):
            scope = ss.get("scope", {}).get("name", "")
            for sp in ss.get("spans", []):
                out.append(Span(
                    trace_id=sp["traceId"],
                    span_id=sp["spanId"],
                    parent_id=sp.get("parentSpanId", ""),
                    name=sp.get("name", ""),
                    kind=KINDS.get(sp.get("kind", 0), "unspecified"),
                    status=STATUS.get(sp.get("status", {}).get("code", 0), "unset"),
                    scope=scope,
                    attrs=_attrs(sp.get("attributes")),
                    resource=resource,
                ))
    return out


def wait_until(check: Callable[[], str | None], timeout: float = 5.0, interval: float = 0.1) -> None:
    """Poll `check` until it returns None (= satisfied) or the timeout passes.

    `check` returns a short description of what is still missing; the last
    one becomes the assertion message. No fixed sleeps anywhere else.
    """
    deadline = time.monotonic() + timeout
    while True:
        problem = check()
        if problem is None:
            return
        if time.monotonic() >= deadline:
            raise AssertionError(f"not reached within {timeout:.1f}s: {problem}")
        time.sleep(interval)


def tree_problem(trace: list[Span], remote_parents: Iterable[str] = ()) -> str | None:
    """None if every span's parent is in the trace and there is one root.

    `remote_parents`: span ids of a caller outside the stack (a traceparent
    the test sent); a span whose parent is one of them counts as the root.
    """
    ids = {s.span_id for s in trace}
    remote = set(remote_parents)
    roots = [s for s in trace if s.is_root or s.parent_id in remote]
    orphans = [s for s in trace if s.parent_id and s.parent_id not in ids and s.parent_id not in remote]
    if orphans:
        return f"orphans {[str(s) for s in orphans]}"
    if len(roots) != 1:
        return f"{len(roots)} roots {[str(s) for s in roots]}"
    return None


def describe(spans: Iterable[Span]) -> str:
    return "\n".join(f"  {s}" for s in spans) or "  (none)"
