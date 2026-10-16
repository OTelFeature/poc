# Stage runbook

One command per script beat. Each `make flag` copies a complete preset from
[src/flagd/presets](src/flagd/presets) over `src/flagd/flagd.json`. flagd
pushes the change to both services and they apply it to the next span. Aspire
(http://localhost:18888, **Traces** view) shows the effect within a second or two.

> [!IMPORTANT]
> The `weatherUpstreamFailure` part of 03b works with the stack as it is:
> weather's own code evaluates it. Every other preset needs extension versions
> that understand `otelEnabled`, `recordSpan`, `traceSampleRatio` and the
> semconv evaluation context. Those are on the extensions' `main` but **not
> released yet**, so the pinned images ignore these flags and every preset
> looks like baseline. Until the releases exist, build the extensions from
> git (FR-026), while online:
>
> ```sh
> make prepare-offline EXT_REF=main
> make start-staging EXT_REF=main
> ```
>
> `make start` lists the extension each running image was built with (`git
> main`, or the pinned version). The images keep that build: plain `make
> start` reuses them, offline too. `make build` goes back to the pinned
> versions, and so does `make prepare-offline` without `EXT_REF`. A ref build
needs the network: offline, run plain `make start-staging`. `geocode` runs with `OTEL_SEMCONV_STABILITY_OPT_IN=http`, so its
> server spans carry `url.path` at start (the old conventions only set
> `http.target`).

## Before the talk (online)

| Step | Command | Expect |
|---|---|---|
| Pull and build everything | `make prepare-offline` | No errors |
| Until the releases exist: build from git (online) | `make prepare-offline EXT_REF=main` then `make start-staging EXT_REF=main` | `git main` for all four app images in the start banner. On stage, offline, plain `make start-staging` reuses these images |
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
| Demo 3: rules on semconv attributes | `make flag PRESET=03-semconv-rules` | About 1 in 10 production traces from both services; all staging traces (filter by `deployment.environment.name`). Demo 2's drops stay on |
| Demo 3: one service back to full | `make flag PRESET=03a-weather-full` | All production `weather` traces again; production `geocode` stays at about 1 in 10 |
| Demo 3: incident | `make flag PRESET=03b-incident` | About 30% of `POST /weather` traces turn red, in both `weather` and `weather-staging` (the flag has no targeting): HTTP 503, span status ERROR, `error.type=503`; the span metrics (built from sampled spans only) show the error rate. Sampling is back at `03-semconv-rules` (production 0.1), so a rule on the error rate (#29) has something to raise |
| Demo 3: incident over | `make flag PRESET=03-semconv-rules` | No new errors |
| End | `make demo-reset` | Baseline, fresh k6 run |

If a beat doesn't show its effect, switch to the fallback video for that demo
(OTelFeature/poc#32) and carry on with the next command.

## What each preset sets

Presets follow the talk's order and are **cumulative**: each one keeps the
rules of the beat before it, so Demo 2's dropped health checks and DB spans
stay dropped through Demo 3. The order is `00-baseline` → `01-otel-off` →
(back to `00`) → `02-quiet-noise` → `03-semconv-rules` → `03a-weather-full`
→ `03b-incident` → `03-semconv-rules`.
Demo 1 is the exception: it is a kill switch shown on its own, and the talk
returns to `00-baseline` before Demo 2.

Every preset is still a full flag file, so any one can be applied directly.
Anything not listed is at its baseline value (`otelEnabled=on`,
`telemetryLevel=full`, `recordSpan=on`, `traceSampleRatio=all` = 1.0,
`weatherUpstreamFailure=none` = 0.0).

| Preset | Change from baseline |
|---|---|
| `00-baseline` | none; identical to the committed `flagd.json` |
| `01-otel-off` | `otelEnabled` default `off` |
| `02-quiet-noise` | `recordSpan` targeting → `off` for `service.name=geocode` + `span.kind=server` + `url.path=/health`, and for `service.name=weather` + `otel.scope.name=io.opentelemetry.jdbc` |
| `03-semconv-rules` | `02-quiet-noise` plus `traceSampleRatio` targeting: production → 0.1, everything else (staging, or no environment) → 1.0 |
| `03a-weather-full` | `02-quiet-noise` plus `traceSampleRatio` targeting: production `weather` → 1.0, other production → 0.1, everything else → 1.0 |
| `03b-incident` | `03-semconv-rules` plus `weatherUpstreamFailure` default `incident` (0.3) |

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
- `make flag` swaps `flagd.json` atomically (temp file + rename) and always
  gives it a newer mtime, so flags flipped in quick succession all arrive.
- A flip that does nothing usually means a stale image (see
  [flagd's README](src/flagd/README.md#flag-changes-with-no-effect)) or
  extension versions that predate the flag (see the note at the top).
