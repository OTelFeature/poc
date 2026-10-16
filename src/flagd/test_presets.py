"""Checks every preset with the same flagd evaluator geocode uses.

The JSON schema check (CI) proves a preset is valid flagd syntax. This script
proves two more things the schema can't:

- the Python in-process provider can parse it (it rejects keys the schema
  allows, such as a flag-level "description"), and
- each rule gives the intended answer for the spans of each demo beat, using
  the evaluation context the extensions build: semconv attributes nested by
  dot segment, trace id as targetingKey (OTelFeature/poc#22).

Run: make test (in the ci/Dockerfile image, with the schema check)
(keep openfeature-provider-flagd in tests/e2e/pyproject.toml in step with
src/geocode/uv.lock)
"""

import json
import sys
from pathlib import Path

from openfeature.contrib.tools.flagd.core import FlagdCore
from openfeature.evaluation_context import EvaluationContext

PRESETS = Path(__file__).parent / "presets"
TRACE_ID = "0af7651916cd43dd8448eb211c80319c"

# Spans of the demo stack, as flat semconv attributes.
SPANS = {
    "geocode /health": {"service.name": "geocode", "deployment.environment.name": "production",
                        "span.kind": "server", "url.path": "/health"},
    "geocode /geocode": {"service.name": "geocode", "deployment.environment.name": "production",
                         "span.kind": "server", "url.path": "/geocode"},
    "geocode psycopg2": {"service.name": "geocode", "deployment.environment.name": "production",
                         "span.kind": "client", "otel.scope.name": "opentelemetry.instrumentation.psycopg2",
                         "db.system.name": "postgresql"},
    "weather /weather": {"service.name": "weather", "deployment.environment.name": "production",
                         "span.kind": "server", "url.path": "/weather"},
    "weather /health": {"service.name": "weather", "deployment.environment.name": "production",
                        "span.kind": "server", "url.path": "/health"},
    "weather jdbc": {"service.name": "weather", "deployment.environment.name": "production",
                     "span.kind": "client", "otel.scope.name": "io.opentelemetry.jdbc"},
    "weather http client": {"service.name": "weather", "deployment.environment.name": "production",
                            "span.kind": "client", "otel.scope.name": "io.opentelemetry.java-http-client"},
    "geocode staging": {"service.name": "geocode", "deployment.environment.name": "staging",
                        "span.kind": "server", "url.path": "/geocode"},
    "weather staging": {"service.name": "weather", "deployment.environment.name": "staging",
                        "span.kind": "server", "url.path": "/weather"},
    "geocode, no env": {"service.name": "geocode", "span.kind": "server", "url.path": "/geocode"},
    # With the extension-owned error rate in the context (UC-005).
    "weather /weather failing": {"service.name": "weather", "deployment.environment.name": "production",
                                 "span.kind": "server", "url.path": "/weather",
                                 "otelfeature.http.server.error_rate": 0.3},
    "weather /weather at threshold": {"service.name": "weather", "deployment.environment.name": "production",
                                      "span.kind": "server", "url.path": "/weather",
                                      "otelfeature.http.server.error_rate": 0.05},
    "geocode /geocode failing": {"service.name": "geocode", "deployment.environment.name": "production",
                                 "span.kind": "server", "url.path": "/geocode",
                                 "otelfeature.http.server.error_rate": 0.3},
}

DEFAULTS = {"otelEnabled": True, "telemetryLevel": "FULL", "recordSpan": True, "traceSampleRatio": 1.0,
            "weatherUpstreamFailure": 0.0}

def _production(service: str | None = None) -> list[str]:
    return [
        span for span, attrs in SPANS.items()
        if attrs.get("deployment.environment.name") == "production"
        and (service is None or attrs["service.name"] == service)
    ]


# From 02 on, presets are cumulative: each beat keeps the previous beat's
# rules (01, the kill switch, stands alone).
QUIET_NOISE = {
    ("geocode /health", "recordSpan"): False,
    ("weather jdbc", "recordSpan"): False,
}

# Per preset: (span, flag) -> expected value. Anything not listed must be the default.
EXPECTED = {
    "00-baseline": {},
    "01-otel-off": {(span, "otelEnabled"): False for span in SPANS},
    "02-quiet-noise": QUIET_NOISE,
    # The ratio resolves for every span, but only root spans use it.
    "03-semconv-rules": {
        **QUIET_NOISE,
        **{(span, "traceSampleRatio"): 0.1 for span in _production()},
    },
    "03a-weather-boost": {
        **QUIET_NOISE,
        **{(span, "traceSampleRatio"): 0.1 for span in _production("geocode")},
        **{(span, "traceSampleRatio"): 0.5 for span in _production("weather")},
    },
    # 03a plus fault injection plus the error-rate loop: above 5% (strictly)
    # a service is sampled fully, whatever its environment rule says; without
    # the key, or at exactly 5%, the 03a rules apply.
    "03b-incident": {
        **QUIET_NOISE,
        **{(span, "traceSampleRatio"): 0.1 for span in _production("geocode")},
        **{(span, "traceSampleRatio"): 0.5 for span in _production("weather")},
        **{(span, "weatherUpstreamFailure"): 0.3 for span in SPANS},
        ("weather /weather failing", "traceSampleRatio"): 1.0,
        ("geocode /geocode failing", "traceSampleRatio"): 1.0,
    },
}


def nest(flat: dict) -> dict:
    out: dict = {}
    for key, value in flat.items():
        node = out
        *parents, leaf = key.split(".")
        for part in parents:
            node = node.setdefault(part, {})
        node[leaf] = value
    return out


def main() -> int:
    failures = []
    files = sorted(PRESETS.glob("*.json"))
    missing = {f.stem for f in files} - EXPECTED.keys()
    if missing:
        failures.append(f"presets without expectations here: {sorted(missing)}")

    for file in files:
        if file.stem not in EXPECTED:
            continue
        before = len(failures)
        core = FlagdCore()
        try:
            core.set_flags(file.read_text(encoding="utf-8"))
        except Exception as e:  # ParseError for keys the provider rejects
            failures.append(f"{file.stem}: the Python flagd provider can't parse it: {e!r} {e.__cause__!r}")
            continue
        for span, attrs in SPANS.items():
            ctx = EvaluationContext(TRACE_ID, nest(attrs))
            for flag, default in DEFAULTS.items():
                want = EXPECTED[file.stem].get((span, flag), default)
                try:
                    details = _resolve(core, flag, default, ctx)
                except Exception as e:
                    failures.append(f"{file.stem}: {flag} for {span!r} raised {e!r}")
                    continue
                # A DISABLED or missing flag would also return the default,
                # so the value alone can't tell "baseline" from "broken".
                if details.error_code is not None or details.reason == "DISABLED" or details.variant is None:
                    failures.append(f"{file.stem}: {flag} for {span!r} did not resolve: "
                                    f"reason={details.reason} error={details.error_code} variant={details.variant}")
                    continue
                got = details.value
                if got != want:
                    failures.append(f"{file.stem}: {flag} for {span!r} = {got!r}, want {want!r}")
        print(f"{'ok  ' if len(failures) == before else 'FAIL'} {file.stem}")

    for failure in failures:
        print(f"FAIL {failure}")
    return 1 if failures else 0


def _resolve(core, flag, default, ctx):
    if isinstance(default, bool):
        return core.resolve_boolean_value(flag, default, ctx)
    if isinstance(default, float):
        return core.resolve_float_value(flag, default, ctx)
    return core.resolve_string_value(flag, default, ctx)


if __name__ == "__main__":
    sys.exit(main())
