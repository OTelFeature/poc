# Stage runbook

One command per script beat. Each `make flag` copies a complete preset from
[src/flagd/presets](src/flagd/presets) over `src/flagd/flagd.json`. flagd
pushes the change to both services and they apply it to the next span. Aspire
(http://localhost:18888, **Traces** view) shows the effect within a second or two.

> [!IMPORTANT]
> Presets 01–03 need extension releases that understand `otelEnabled`,
> `recordSpan`, `traceSampleRatio` and the semconv evaluation context
> (otelfeature-instrument and otelfeature-java-extension, not released yet).
> Until `src/geocode` and `src/weather` are bumped to those versions, the
> pinned extensions ignore these flags and every preset looks like baseline.
> `geocode` runs with `OTEL_SEMCONV_STABILITY_OPT_IN=http`, so its server
> spans carry `url.path` at start (the old conventions only set `http.target`).

## Before the talk (online)

| Step | Command | Expect |
|---|---|---|
| Pull and build everything | `make prepare-offline` | No errors |
| Start empty, with staging | `docker compose --profile staging down -v` then `make start-staging` | 4 app containers + 2 k6 |
| Baseline flags, fresh traffic | `make demo-reset` | `flagd.json is now 00-baseline` |

Then go offline. From here nothing needs the network (see "Running on stage"
in the [README](README.md)). Use `make start-staging` rather than `make start`,
because Demo 3 needs the staging twins.

## During the talk

| Beat | Command | Aspire shows |
|---|---|---|
| Cold open: wall of spans | none (OTel Demo footage, D1) | n/a |
| Demo 1: one flag turns tracing off | `make flag PRESET=01-otel-off` | No new traces from `geocode` or `weather`; their metrics, and flagd's own traces, keep flowing |
| Demo 1: and back on | `make flag PRESET=00-baseline` | Complete traces from both services again |
| Demo 2: drop the noise | `make flag PRESET=02-quiet-noise` | No new `GET /health` traces from `geocode`, and new `/weather` traces with no `SELECT`/`INSERT` (JDBC) spans. `weather`'s own `/health` traces stay |
| Demo 3: rules on semconv attributes | `make flag PRESET=03-semconv-rules` | About 1 in 10 production `geocode` traces; all production `weather` traces; all staging traces (filter by `deployment.environment.name`) |
| Demo 3: incident | `03b-incident`, added with the fault-injection flag (OTelFeature/poc#28) | n/a |
| End | `make demo-reset` | Baseline, fresh k6 run |

If a beat doesn't show its effect, switch to the fallback video for that demo
(OTelFeature/poc#32) and carry on with the next command.

## What each preset sets

Every preset is a full flag file. Anything not listed is at its baseline value
(`otelEnabled=on`, `telemetryLevel=full`, `recordSpan=on`,
`traceSampleRatio=all` = 1.0).

| Preset | Change from baseline |
|---|---|
| `00-baseline` | none; identical to the committed `flagd.json` |
| `01-otel-off` | `otelEnabled` default `off` |
| `02-quiet-noise` | `recordSpan` targeting → `off` for `service.name=geocode` + `span.kind=server` + `url.path=/health`, and for `service.name=weather` + `otel.scope.name=io.opentelemetry.jdbc` |
| `03-semconv-rules` | `traceSampleRatio` targeting: production `weather` → 1.0, other production → 0.1, everything else (staging, or no environment) → 1.0 |

Rules read the evaluation context the extensions build from OTel semantic
conventions, nested by dot segment, so `{"var": "service.name"}` works as
written. The trace id is the `targetingKey`. Only attributes known when the span
starts are available, so rules use `url.path`, never `http.route`.

## Rehearsal tips

- `make flags` lists the presets; `make flag` with no argument prints usage.
- `make flag` leaves `src/flagd/flagd.json` modified in git. `make demo-reset`
  restores it.
- Run `make validate-flags` after editing a preset. It runs the CI checks:
  the flagd schema, baseline = `flagd.json`, and an evaluation of every rule
  with the Python flagd provider (`src/flagd/test_presets.py`).
- `make flag` rewrites `flagd.json` in place, so flagd can briefly see a
  half-written file. It logs a parse error and applies the next write. Check
  this once during rehearsal.
- A flip that does nothing usually means a stale image (see
  [flagd's README](src/flagd/README.md#flag-changes-with-no-effect)) or
  extension versions that predate the flag (see the note at the top).
