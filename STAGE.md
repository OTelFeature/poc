# Stage runbook

One command per script beat. Each `docker compose run --rm flag <preset>`
copies a complete preset from [src/flagd/presets](src/flagd/presets) over
`src/flagd/flagd.json` and waits until flagd serves it (it prints
`flagd serves <preset>`, or fails after 10 s). flagd pushes the change to both
services and they apply it to the next span. Aspire (http://localhost:18888,
**Traces** view) shows the effect within a second or two. Only Docker is
needed; `make flag PRESET=<preset>` does the same write without the
confirmation.

> [!NOTE]
> The stage runs the pinned extension releases: otelfeature-instrument
> **v0.4.0** in `geocode` (`src/geocode/pyproject.toml`, `uv.lock`) and
> otelfeature-java-extension **v0.5.0** in `weather`
> (`OTELFEATURE_EXTENSION_VERSION` in `src/weather/Dockerfile`). Both
> understand `otelEnabled`, `telemetryLevel` (including `OFF`), `recordSpan`,
> `traceSampleRatio` and the semconv evaluation context. The stage never builds
> an extension from a git ref; unreleased code needs a pre-release (`v…-rc.N`).
> The stage **pulls** these images prebuilt from `main`
> (`ghcr.io/otelfeature/poc-geocode`, `poc-weather`, `poc-stub-apis`; their
> labels name the extension versions) instead of building them (UC-008
> BR-008). `docker compose up` doesn't refresh images that are present:
> after a version bump lands on `main`, pull again, or the old images keep
> the old extensions. The start command below adds `--pull never --no-build`,
> so a missing image fails loudly instead of being pulled or quietly built
> from source. To
> run exactly the images you rehearsed, pin their tag:
> `export POC_IMAGE_TAG=sha-<short commit>` before pulling and starting.
> `geocode` runs with `OTEL_SEMCONV_STABILITY_OPT_IN=http`, so its server
> spans carry `url.path` at start (the old conventions only set `http.target`).

## Before the talk (online)

| Step | Command | Expect |
|---|---|---|
| Pull everything, nothing built | `docker compose --profile staging --profile tools pull` (or `make prepare-offline`) | No errors |
| Check the images are the published ones | `docker image inspect ghcr.io/otelfeature/poc-weather:${POC_IMAGE_TAG:-main} --format '{{index .Config.Labels "org.opencontainers.image.revision"}}'` (same for `poc-geocode`, `poc-stub-apis`) | A commit id; empty means a local build |
| Start empty, with staging | `docker compose --profile staging down -v` then `docker compose --profile staging up -d --pull never --no-build` | 4 app containers + 2 k6 |
| Baseline flags, fresh traffic | `docker compose run --rm flag 00-baseline` then `docker compose --profile staging restart load-generator load-generator-staging` (or `make demo-reset`) | `flagd serves 00-baseline` |

If the pull fails (not logged in, or a local code change to show), build
from source while still online: `docker compose --profile staging build`
(UC-008 A3).

Then go offline. From here nothing needs the network (see "Running on stage"
in the [README](README.md)). Start with the `staging` profile, because Demo 3
needs the staging twins.

## During the talk

| Beat | Command | Aspire shows |
|---|---|---|
| Cold open: wall of spans | none (OTel Demo footage, D1) | n/a |
| Demo 1: one flag turns tracing off | `docker compose run --rm flag 01-otel-off` | No new traces from `geocode` or `weather`; their metrics, and flagd's own traces, keep flowing |
| Demo 2: tracing back, by span kind only | `docker compose run --rm flag 02-quiet-noise` | Traces again, but only the I/O boundary (`telemetryLevel` IO): no `INTERNAL` spans. `geocode` loses the ASGI `http receive`/`http send` spans and `geocode.resolve`, `weather` its controller spans (`WeatherController.*`); server, HTTP client and DB spans stay, re-attached to their real parent. A `GET /health` trace shrinks to its single server span |
| Demo 3: rules on semconv attributes | `docker compose run --rm flag 03-semconv-rules` | No more `GET /health` traces from `geocode`, and `/weather` traces with no `SELECT`/`INSERT` (JDBC) spans (`recordSpan` rules on `service.name`, `span.kind`, `url.path`, `otel.scope.name`); `weather`'s own `/health` traces stay. About 1 in 10 production traces from both services; all staging traces (filter by `deployment.environment.name`). Demo 2's IO cut stays on |
| Demo 3: boost one service | `docker compose run --rm flag 03a-weather-boost` | Production `weather` at about half its traces; production `geocode` stays at about 1 in 10 |
| Demo 3: incident | `docker compose run --rm flag 03b-incident` | About half of the `POST /weather` requests fail (HTTP 503, span status ERROR, `error.type=503`), in `weather` and `weather-staging` (the fault flag has no targeting). Within one or two error-rate intervals (10 s), weather's error rate passes 5% and the loop rule samples it fully: production `weather` goes from about half to all traces; `geocode` stays at 1 in 10. See the note below on the margin |
| Demo 3: incident over | `docker compose run --rm flag 03a-weather-boost` | No new errors; production `weather` is back at about half right away, because the loop rule goes with the fault (OQ-14). Not a reset |
| End | `docker compose run --rm flag 00-baseline` (or `make demo-reset`, which also restarts k6) | Baseline |

**How much Demo 2 saves** depends on how much `INTERNAL` detail the
instrumentation produces: `geocode`'s come with FastAPI's defaults, while
`weather` has Spring controller telemetry switched on (experimental, off by
default in the Java agent; spec C-015). Measured: spans −66 % / −38 %, export
bytes −37 % / −25 % (`geocode` / `weather`, OTelFeature/poc#110).

**Incident margin.** The loop reads weather's error rate over *all* its
requests in a 10 s interval, and only `POST /weather` fails. With the stage
load (k6: `/weather` 1/s and `/health` 2/s, plus the compose healthcheck
every 2 s) that is about 5 failures in 35 requests, an error rate of about
**14%** at the incident share of 0.5 (UC-006 BR-003). An interval not above
the 5% threshold (at most one failure in ten `/weather` requests) happens
about 1% of the time, so over a minute-long beat there is roughly a 6%
chance of one 10 s dip back to half. The span metrics in Aspire are built from *sampled* spans,
so their error rate moves with the sampling and isn't the loop's input
(that is the services' unsampled HTTP metric).

If a beat doesn't show its effect, switch to the fallback video for that demo
(OTelFeature/poc#32) and carry on with the next command.

## What each preset sets

Presets follow the talk's order and are **cumulative**: each one keeps the
rules of the beat before it, so Demo 2's IO cut stays on through Demo 3,
and Demo 3's dropped health checks and DB spans stay dropped through the
incident. The demo is a **progression with no resets**
(UC-008 BR-006): `00-baseline` → `01-otel-off` → `02-quiet-noise` →
`03-semconv-rules` → `03a-weather-boost` → `03b-incident`, and back to
`03a-weather-boost` when the incident is over. `01-otel-off` is
the exception: it is the baseline with tracing off, and `02-quiet-noise`
turns tracing back on at `telemetryLevel` IO. `make demo-reset` is for
rehearsals, never between beats.

Every preset is still a full flag file, so any one can be applied directly.
Anything not listed is at its baseline value (`otelEnabled=on`,
`telemetryLevel=full`, `recordSpan=on`, `traceSampleRatio=all` = 1.0, `weatherUpstreamFailure=none` = 0.0). The
ratio's other variants are `half` 0.5, `tenth` 0.1 and `none` 0.0.

| Preset | Change from baseline |
|---|---|
| `00-baseline` | none; identical to the committed `flagd.json` |
| `01-otel-off` | `otelEnabled` default `off` |
| `02-quiet-noise` | `telemetryLevel` default `io` (no `INTERNAL` spans); no targeting anywhere |
| `03-semconv-rules` | `02-quiet-noise` plus `recordSpan` targeting → `off` for `service.name=geocode` + `span.kind=server` + `url.path=/health`, and for `service.name=weather` + `otel.scope.name=io.opentelemetry.jdbc`, plus `traceSampleRatio` targeting: production → 0.1, everything else (staging, or no environment) → 1.0 |
| `03a-weather-boost` | `03-semconv-rules` plus production `weather` → 0.5 (other production 0.1, everything else 1.0) |
| `03b-incident` | `03a-weather-boost` plus `weatherUpstreamFailure` default `incident` (0.5) and the control-loop rule: `otelfeature.http.server.error_rate > 0.05` → 1.0, ahead of the other ratio rules |

Rules read the evaluation context the extensions build from OTel semantic
conventions, nested by dot segment, so `{"var": "service.name"}` works as
written. The trace id is the `targetingKey`. Only attributes known when the span
starts are available, so rules use `url.path`, never `http.route`.

## Rehearsal tips

- `docker compose run --rm flag` (no preset) and `make flags` list the
  presets.
- Every flip leaves `src/flagd/flagd.json` modified in git; applying
  `00-baseline` (or `make demo-reset`) restores it.
- A flip that fails with "flagd did not answer" means the stack isn't up;
  "does not serve" means flagd rejected the file (see
  `docker compose logs flagd`).
- Run `make test` after editing a preset. It runs the CI checks:
  the flagd schema, baseline = `flagd.json`, and an evaluation of every rule
  with the Python flagd provider (`src/flagd/test_presets.py`).
- The `flag` service and `make flag` swap `flagd.json` atomically (temp
  file + rename) and always give it a newer mtime, so flags flipped in quick
  succession all arrive.
- A flip that does nothing usually means a stale image (see
  [flagd's README](src/flagd/README.md#flag-changes-with-no-effect)) or
  extension versions that predate the flag (see the note at the top).
