# poc-otelfeature

The demo from the talk: OpenFeature flags, served by flagd, decide live
which spans two services create, with no restart. It runs a Python geocoding
API, a Java weather API, an OpenTelemetry Collector, and an
[Aspire Dashboard](https://learn.microsoft.com/en-us/dotnet/aspire/fundamentals/dashboard/overview)
to show the resulting traces.

> From the KubeCon + CloudNativeCon North America 2026 talk
> **OpenFeature as a Control Plane for OpenTelemetry** by Simon Schrottner
> ([Flagsmith](https://www.flagsmith.com/?utm_source=github&utm_medium=readme&utm_campaign=otelfeature&utm_content=poc)) and Juliano Costa
> ([Dash0](https://www.dash0.com/?utm_source=github&utm_medium=readme&utm_campaign=otelfeature&utm_content=poc)). The talk page has how to
> reach us, and the slides and recording once they're out:
> **[otelfeature.github.io/presentation](https://otelfeature.github.io/presentation/)**

## Try it locally

All you need is Docker with Compose v2 (Docker Desktop, or Docker Engine on
Linux or WSL2). No `make`, no Python, no Java: `main` publishes prebuilt
images for `linux/amd64` and `linux/arm64` (Apple Silicon included), so
nothing is built on your machine.

```sh
git clone https://github.com/OTelFeature/poc.git && cd poc

docker compose pull       # prebuilt geocode, weather, stub-apis + third-party images
docker compose up -d      # starts the stack; builds nothing
```

Open the Aspire dashboard at http://localhost:18888 (**Traces**). Traces
from `geocode` and `weather` show up within a few seconds; the load generator
sends traffic for 15 minutes.

Flip flags with the `flag` service. It applies a preset from
[src/flagd/presets](src/flagd/presets) and waits until flagd serves it:

```sh
docker compose run --rm flag 01-otel-off       # Demo 1: tracing off
docker compose run --rm flag 02-quiet-noise    # Demo 2: INTERNAL spans off (span kind only)
docker compose run --rm flag 03-semconv-rules  # Demo 3: drop health checks, DB spans; sample by environment
docker compose run --rm flag 03a-weather-boost
docker compose run --rm flag 03b-incident      # fault injection + error-driven sampling
docker compose run --rm flag 00-baseline       # back to the start
docker compose run --rm flag                   # prints usage and the presets
```

[STAGE.md](STAGE.md) says what each preset changes and what Aspire shows.
`docker compose --profile staging up -d` adds the staging twins Demo 3 uses;
`docker compose --profile staging down` stops everything.

- `POC_IMAGE_TAG=sha-<short commit>` pins the images of one commit
  instead of the latest of `main` (`main`).
- `docker compose up -d --build` builds the images from your checkout
  instead, for example after changing a service. The build needs network
  access; the result keeps the image names, so a later `docker compose pull`
  replaces it with the published images again.

## Architecture

```mermaid
flowchart LR
    classDef load fill:#00e5ff,color:black;
    classDef geocode fill:#4ab52f,color:white;
    classDef weather fill:#ee0943,color:white;
    classDef otelcol fill:#ffd500,color:black;
    classDef aspire fill:#9966ff,color:white;
    classDef docker fill:#607d8b,color:white;
    classDef flagd fill:#f57c00,color:white;
    classDef datadog fill:#632ca6,color:white;


    subgraph Service Diagram
        load("load-generator<br/>(k6)"):::load
        geocode(geocode):::geocode
        weather(weather):::weather
        flagd(flagd):::flagd
        otelcol{"otel-collector<br/>(contrib)"}:::otelcol
        docker[("Docker socket")]:::docker
        coordinates[(coordinates-db<br/>PostgreSQL)]
        aspire[aspire]:::aspire
        datadog("Datadog<br/>(optional)"):::datadog

        docker -..->|docker_stats| otelcol
        load -->|OTLP/gRPC| otelcol
        load -->|HTTP| geocode
        load -->|HTTP| weather
        
        geocode -..->|cache miss| stub["stub-apis<br/>(Nominatim + Open-Meteo,<br/>or the real APIs)"]
        geocode ---->|OTLP/HTTP| otelcol
        geocode --->|"telemetryLevel<br/>(gRPC sync)"| flagd

        geocode -->|SQL| coordinates
        geocode -->|"POST /weather<br/>(from /forecast)"| weather
        weather -->|SQL| coordinates
        weather --->|"telemetryLevel<br/>(gRPC sync)"| flagd
        weather --->|OTLP/HTTP| otelcol
        weather -..->|cache miss| stub
        flagd -->|OTLP/HTTP| otelcol
        otelcol -->|OTLP/gRPC| aspire
        otelcol -.->|OTLP/HTTP| datadog
    end
```

- **geocode** ([src/geocode](src/geocode)) — a FastAPI service that resolves
  a city/country to latitude/longitude. It checks `coordinates-db` first; on
  a cache miss it falls back to the
  [Nominatim](https://nominatim.org/release-docs/latest/api/Search/) API and
  persists the result for next time. Runs under
  [otelfeature-instrument](https://github.com/OTelFeature/otelfeature-instrument),
  a separate, reusable zero-code launcher that also suppresses `INTERNAL`
  spans live, controlled by the `telemetryLevel` flag served from `flagd`.
- **flagd** ([src/flagd](src/flagd)) — an [OpenFeature](https://openfeature.dev/)
  flag backend serving the `telemetryLevel` flag that controls both
  `geocode`'s and `weather`'s trace verbosity (via `otelfeature-instrument`
  and `otelfeature-java-extension` respectively), editable live with no
  restart.
- **weather** ([src/weather](src/weather)) — a Java/Spring Boot service that
  resolves current weather for a city/country pair. It checks the `weather`
  cache table in `coordinates-db` first; on a miss it looks up coordinates
  (from the `coordinates` table shared with `geocode`, or Open-Meteo's
  geocoding API as fallback), queries the
  [Open-Meteo](https://open-meteo.com/) forecast API, and persists the result.
  Instrumented with the [OpenTelemetry Java auto-instrumentation
  agent](https://github.com/open-telemetry/opentelemetry-java-instrumentation)
  — zero-code `-javaagent` instrumentation of Spring Boot, JDBC, and
  `java.net.http.HttpClient`. Also uses
  [otelfeature-java-extension](https://github.com/OTelFeature/otelfeature-java-extension)
  for flagd-controlled `INTERNAL`-span suppression (the Java counterpart to
  `otelfeature-instrument`). Like `geocode`, it syncs the flag ruleset
  in-process from flagd over the gRPC sync stream, so a flag edit takes effect
  on the very next span.
- **coordinates-db** ([src/coordinates-db](src/coordinates-db)) — a Postgres
  instance caching previously resolved city/country → lat/lon lookups (shared
  by `geocode` and `weather`) and weather results, so repeat requests don't
  hit external APIs.
- **stub-apis** ([src/stub-apis](src/stub-apis)) — an offline stand-in for
  Nominatim and Open-Meteo, so the stack runs with no network. `make start`
  points both services at it; `make start-live` uses the real APIs.
- **load-generator** ([src/load-generator](src/load-generator)) — a k6 script
  that continuously sends requests to both `geocode` (`POST /geocode`) and
  `weather` (`POST /weather`), plus a steady `GET /health` on both
  (`HEALTHCHECK_RATE`), exporting its own metrics to the collector over
  OTLP/gRPC.
- **otel-collector** ([src/otel-collector](src/otel-collector)) — an
  `opentelemetry-collector-contrib` instance that receives OTLP from the
  services, also scrapes Docker container stats, derives span metrics, and
  forwards everything to the Aspire Dashboard — and, optionally, to Datadog.
- **aspire-dashboard** — Microsoft's Aspire Dashboard, used here purely as a
  local OTLP viewer/UI.

> [!NOTE]
> `geocode`'s telemetry bootstrap (`opentelemetry-instrument`-style zero-code
> launcher, plus the flagd-controlled `INTERNAL`-span suppression) has moved
> out of this repo into
> [OTelFeature/otelfeature-instrument](https://github.com/OTelFeature/otelfeature-instrument),
> a standalone, reusable dependency any Python service can adopt — not just
> `geocode`. `src/geocode` pulls it in as a regular (if not-yet-published)
> dependency; see [geocode's README](src/geocode/README.md#dependencies).
>
> `weather` uses the Java counterpart,
> [OTelFeature/otelfeature-java-extension](https://github.com/OTelFeature/otelfeature-java-extension),
> an OTel Java agent extension JAR that adds the same flagd-controlled
> `INTERNAL`-span suppression. The JAR is downloaded from
> [GitHub Releases](https://github.com/OTelFeature/otelfeature-java-extension/releases)
> during the Docker build. See
> [weather's README](src/weather/README.md#otelfeature-java-extension) for details.
>
> Both services now talk to flagd the same way — the in-process resolver on
> the gRPC sync port `8015` — and both evaluate `telemetryLevel` only as often
> as the flag actually requires: once while it is static, per span once it
> carries a `targeting` block. See [flagd's README](src/flagd/README.md).

## Requirements

- Docker and Docker Compose v2. That is all for running the demo (see
  [Try it locally](#try-it-locally)).
- `make` is optional: the targets below are shortcuts around Docker.
  `make test`, `make shell` and `make e2e` run in
  the toolchain image (`ci/Dockerfile`). [uv](https://docs.astral.sh/uv/) is
  optional, only for working on `geocode` outside a container.

## Running

```sh
make build            # build geocode, weather, stub-apis from source (staging twins included)
make start            # docker compose up -d, external APIs stubbed
make start-live       # same, but geocode/weather call the real Nominatim and Open-Meteo
make start-staging    # also start the staging twins (compose profile `staging`)
make prepare-offline  # pull every image (prebuilt ones from main), so `make start` later needs no network
make prepare-offline BUILD=1  # same, but build geocode, weather, stub-apis from source
make stop             # docker compose down (staging included)

make flag PRESET=02-quiet-noise  # apply a flag preset (see STAGE.md); without make:
                                 #   docker compose run --rm flag 02-quiet-noise
make demo-reset                  # baseline flags, restart k6
make test                        # preset checks (schema + evaluation), in the toolchain image
make unit-test                   # geocode and weather unit tests, in each Dockerfile's test stage
make shell                       # shell in the toolchain image (ci/Dockerfile), repo at /workspace
make e2e                         # end-to-end suite against the real stack (tests/e2e)
```

[STAGE.md](STAGE.md) is the stage runbook: one command per script beat.

Once started:

- Aspire Dashboard: http://localhost:18888
- Geocode health check: http://localhost:8000/health
- Weather health check: http://localhost:8001/health

Example requests:

```sh
# Geocode — resolve city/country to lat/lon
curl -s -X POST http://localhost:8000/geocode \
  -H "Content-Type: application/json" \
  -d '{"city": "linz", "country": "austria"}'

# Weather — get current weather for a city/country
curl -s -X POST http://localhost:8001/weather \
  -H "Content-Type: application/json" \
  -d '{"city": "linz", "country": "austria"}'
```

### Resource attributes and environments

`geocode` and `weather` set their own semantic-convention resource
attributes through `OTEL_RESOURCE_ATTRIBUTES` in
[compose.yaml](compose.yaml):

| Attribute | Value |
|---|---|
| `service.name` | `geocode` / `weather` (`OTEL_SERVICE_NAME`) |
| `service.namespace` | `otelfeature` |
| `service.version` | `0.1.0` (the version in `pyproject.toml` / `build.gradle`) |
| `deployment.environment.name` | `production`, or `staging` for the staging twins |
| `service.instance.id` | the container name (`geocode`, `geocode-staging`, ...) |

The flag decisions happen in the SDK, so rules on these attributes only work
if the service itself sets them. The collector's `resource` processor only
*inserts* `deployment.environment.name=otelfeature` for senders that don't set
one (flagd, k6, docker stats); it never overwrites a service's value.

`make start-staging` (or `docker compose --profile staging up -d`) adds
`geocode-staging` (port 8002), `weather-staging` (port 8003) and a second k6
instance driving them. Aspire groups by `service.name`, so it shows two
instances each of `geocode` and `weather` (told apart by
`service.instance.id`), with the environment in the resource attributes.
Both environments share `coordinates-db`, so a location one environment has
resolved is a cache hit for the other.

### Running on stage

The default stack needs no network once its images exist. `geocode` and
`weather` call [stub-apis](src/stub-apis) instead of Nominatim and Open-Meteo,
and nothing else in the stack needs to reach outside the compose network.
One exception: the collector's optional Datadog exporter is always in the
pipelines and, without `DD_SITE`/`DD_API_KEY`, logs export errors (which
also show up in Aspire as collector logs). Ignore them.

1. While online: `make prepare-offline` (without make:
   `docker compose --profile staging --profile tools pull`). This pulls every
   image, including the prebuilt `geocode`, `weather` and `stub-apis` images
   and the `flag` service's busybox. `make prepare-offline BUILD=1` builds
   the three from source instead (their builds download dependencies, the
   OTel Java agent and the otelfeature extension, so they can't run offline).
2. Offline: `docker compose up -d --pull never --no-build` (STAGE.md uses
   this): a missing image then fails loudly. Plain `docker compose up -d` and
   `make start` don't refresh images that are present, but they pull a missing
   one and, if that fails, build it from source; don't run `make build` or
   `docker compose up --build` without network.

The outgoing `CLIENT` spans still show a real HTTP call, with
`server.address` = `stub-apis` and 20–120 ms of latency. They only appear on
a cache miss, and the Postgres volume survives `make stop`. To show them
again after a rehearsal, start from an empty cache with
`docker compose --profile staging down -v`.

To demo against the real APIs instead, use `make start-live` (and keep the
request rate within
[Nominatim's usage policy](https://operations.osmfoundation.org/policies/nominatim/)).
Live mode lasts only for that invocation: a later `make start` or
`docker compose up -d <service>` recreates the services with the stub URLs.
To make it stick, put `NOMINATIM_URL`, `OPEN_METEO_GEOCODING_URL` and
`OPEN_METEO_FORECAST_URL` in `.env` (gitignored).

Each service has its own README with configuration details:
[geocode](src/geocode/README.md), [weather](src/weather/README.md),
[flagd](src/flagd/README.md), [coordinates-db](src/coordinates-db/README.md),
[load-generator](src/load-generator/README.md),
[stub-apis](src/stub-apis/README.md),
[otel-collector](src/otel-collector/README.md).

## Which `OTEL_*` env vars can be live flags

**The env var is the default, the flag is the live override.** Each setting
starts from its standard `OTEL_*` env var, read the way the SDK or the Java
agent reads it. A flag changes it while the service runs, and if the flag
can't be evaluated, the env var value applies again. There are two
exceptions, the **hard floors**: with `OTEL_SDK_DISABLED=true` or
`OTEL_TRACES_SAMPLER=always_off` the env var wins, and no flag turns tracing
back on. Flags never re-enable what a hard floor switched off.

Not every env var can work this way. Most are read once, while the SDK is
built, and nothing reads them again.

| Tier | Env vars | Live flag | Why |
|---|---|---|---|
| **Live flag** | `OTEL_SDK_DISABLED` | `otelEnabled=false`, `telemetryLevel=OFF` | The flags suppress spans instead of disabling the SDK; `true` is a hard floor |
| **Live flag** | `OTEL_TRACES_SAMPLER`, `OTEL_TRACES_SAMPLER_ARG` | `traceSampleRatio`, for trace roots | The env vars give the fallback ratio; `always_off` is a hard floor; `parentbased_always_off` keeps its standard meaning |
| **Live flag, approximated** | `OTEL_INSTRUMENTATION_<name>_ENABLED` (Java agent; for Python see `OTEL_PYTHON_DISABLED_INSTRUMENTATIONS`) | a `telemetryLevel` rule on `otel.scope.name` | Scope filtering: the instrumentation stays installed, only its spans are left out. A `recordSpan` rule on the scope goes further: a root or entry span from that scope drops its whole local trace |
| **Startup only, honoured** | `OTEL_TRACES_EXPORTER=none`, `OTEL_METRICS_EXPORTER=none` | none | Both extensions honour `none` at startup, like the SDK. A live per-signal switch (`signalsEnabled`, [#11](https://github.com/OTelFeature/poc/issues/11)) was closed as not planned |
| **Startup only** | `OTEL_LOGS_EXPORTER` | none | Java: the agent reads it. Python: otelfeature-instrument sets up no logs pipeline. Logs are out of scope here |
| **Feasible, deferred** | `OTEL_SPAN_ATTRIBUTE_VALUE_LENGTH_LIMIT`, `OTEL_ATTRIBUTE_COUNT_LIMIT` | none | Fixed in the span limits when the provider is built. An exporter-side truncating wrapper could approximate them ("clamp it now"), with different semantics |
| **Feasible, deferred** | `OTEL_BSP_SCHEDULE_DELAY`, `OTEL_METRIC_EXPORT_INTERVAL` | none | Changing them live means rebuilding the processor or reader mid-flight, with a flush; small payoff |
| **Feasible, deferred** | `OTEL_PROPAGATORS` | none | Easy (a delegating propagator), but no incident calls for flipping propagators live |
| **Excluded: security** | `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS` (and per-signal variants) | none, by decision | See below |
| **Cannot be a flag** | `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES` | none | The resource is fixed when the providers are built |
| **Cannot be a flag** | `OTEL_EXPORTER_OTLP_PROTOCOL` | none | Chooses the exporter implementation at startup |
| **Cannot be a flag** | `OTEL_JAVAAGENT_ENABLED` | none | Decides whether the agent, and so the extension, loads at all |
| **Cannot be a flag** | `OTEL_PYTHON_DISABLED_INSTRUMENTATIONS` | none | Decides at launch which libraries get patched; the scope rule above is the live alternative |
| **Cannot be a flag** | `OTEL_SEMCONV_STABILITY_OPT_IN` | none | Instrumentations pick their attribute and metric names when installed |

The env vars in the last tier are consumed before there is anything to
re-evaluate. A flag for one of them would only take effect at the next
restart, and at a restart the env var already does the job.

**Why the OTLP endpoint is excluded.** A live endpoint flag is technically
feasible (rebuild the exporter, flush), but it should not ship. A flag that
redirects a whole fleet's telemetry to an arbitrary endpoint is a
data-exfiltration primitive, and flagd rulesets usually have weaker access
control than deployment config. The headers carry credentials. If it is ever
built, it may only choose from an allowlist of endpoints fixed at startup.

**Out of scope: startup-time flags.** Reading configuration from flagd at
bootstrap would give central configuration without a redeploy per service,
though not without a restart. That is a different product, and this project
does not pursue it.

Details per language:
[otelfeature-instrument](https://github.com/OTelFeature/otelfeature-instrument#configuration)
(Python; see also [one policy, one read](https://github.com/OTelFeature/otelfeature-instrument#one-policy-one-read)
and [muting an instrumentation](https://github.com/OTelFeature/otelfeature-instrument#muting-an-instrumentation-once-per-tracer))
and
[otelfeature-java-extension](https://github.com/OTelFeature/otelfeature-java-extension#configuration)
(Java; see also [sampling ratio](https://github.com/OTelFeature/otelfeature-java-extension#sampling-ratio-tracesampleratio)
and [dropping single spans](https://github.com/OTelFeature/otelfeature-java-extension#dropping-single-spans-recordspan)).
The spec keeps the reference table in
[docs/spec/entity_model.md](docs/spec/entity_model.md#otel_-env-vars-and-live-flags).

## Repository layout

```
compose.yaml              # service definitions and wiring
compose.e2e.yaml          # override for the end-to-end suite (make e2e); builds the checkout
ci/Dockerfile             # toolchain image (make test, make shell, make e2e)
STAGE.md                  # stage runbook: one command per script beat
Makefile                  # build/start/stop shortcuts around docker compose
src/
  geocode/                # FastAPI geocoding service (uv + Docker)
  weather/                # Java/Spring Boot weather service (Gradle + Docker)
  flagd/                  # OpenFeature flag definitions (flagd)
    presets/              # one complete flagd.json per demo state (STAGE.md)
    flag.sh               # the `flag` compose service: apply a preset, confirm over OFREP
  coordinates-db/         # Postgres init script (coordinates + weather cache)
  load-generator/         # k6 load test script targeting geocode and weather
  stub-apis/              # offline stand-in for Nominatim and Open-Meteo
  otel-collector/         # collector config.yaml
```

> [!NOTE]
> This note is about `make start-live`; the default `make start` talks to
> `stub-apis`, which has no rate limit.
> `geocode` caches resolved coordinates in `coordinates-db`, so only
> first-time city/country lookups hit Nominatim. `weather` similarly caches
> weather results and shares the `coordinates` table with `geocode`, so only
> first-time lookups hit [Open-Meteo](https://open-meteo.com/) (which has no
> API key and generous rate limits). `load-generator`'s default rate is still
> deliberately low (1 request every 5s per service) to stay well under
> [Nominatim's usage policy](https://operations.osmfoundation.org/policies/nominatim/)
> for whatever does miss the cache — raise `REQUEST_INTERVAL_SECONDS` at your
> own risk of getting rate-limited (HTTP 429).

> [!NOTE]
> Forwarding telemetry to Datadog (`otel-collector`'s `otlp_http/datadog`
> exporter) is optional and off by default — see
> [otel-collector's README](src/otel-collector/README.md#datadog-export).

## Talk to us

This is a prototype with open questions, and we'd like to hear how it
fits your setup:

- [Open an issue](https://github.com/OTelFeature/poc/issues/new)
- CNCF Slack ([invite](https://slack.cncf.io)): `#openfeature` and `#opentelemetry`
- The speakers' websites: [Simon Schrottner](https://schrottner.at) and
  [Juliano Costa](https://jcosta.dev)
