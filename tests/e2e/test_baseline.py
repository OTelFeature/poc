"""Baseline: with the neutral flags, both services export complete traces.

Not a spec test case of its own; every TC starts from this state, so if this
fails nothing else is meaningful.
"""

from __future__ import annotations

from conftest import Step
from checks import APP_SERVICES, by_root_service, complete_problem
from spans import describe, wait_until

RESOURCE = {
    "service.namespace": "otelfeature",
    "deployment.environment.name": "production",
}


def test_baseline(step: Step):
    # An unknown city misses every cache, so each request reads the DB and
    # calls the external API (the stub), which then answers "not found".
    city = f"e2e-{step.id[:12]}"
    assert step.geocode(city, "nowhere").status_code == 404
    assert step.weather(city, "nowhere").status_code == 404

    def problem() -> str | None:
        by_service = by_root_service(step.traces())
        for service in APP_SERVICES:
            trace = by_service.get(service)
            if trace is None:
                return f"no {service} trace for step yet"
            missing = complete_problem(trace, service)
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
