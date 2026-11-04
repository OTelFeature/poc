# weather

A Java 25 / Spring Boot 4.1 service that returns the current weather for a
city and country, using the [Open-Meteo](https://open-meteo.com/) API.

On each request it:

1. returns the row from the `weather` table in
   [coordinates-db](../coordinates-db) on a hit,
2. otherwise looks up the coordinates in the `coordinates` table (shared
   with [geocode](../geocode)), and on a miss asks Open-Meteo's geocoding API
   and stores them,
3. asks the Open-Meteo forecast API,
4. stores the result in `weather` and returns it.

Without the database it still works and calls the APIs every time.

## API

```sh
curl -s -X POST http://localhost:8001/weather \
  -H "Content-Type: application/json" \
  -d '{"city": "linz", "country": "austria"}'
# {"latitude":48.3069,"longitude":14.2857,"temperature":12.5,"windspeed":3.2,"weatherCode":61,"weatherDescription":"Rain"}

curl -s http://localhost:8001/health
# {"status":"ok"}
```

## Instrumentation

The [OpenTelemetry Java agent](https://github.com/open-telemetry/opentelemetry-java-instrumentation)
instruments the service with no code changes: `SERVER` spans from Spring
Boot (Tomcat), `CLIENT` spans from JDBC and `java.net.http.HttpClient`. The
[Dockerfile](Dockerfile) downloads it in its own stage (pinned by
`OTEL_AGENT_VERSION`) and attaches it with `-javaagent`.

### otelfeature-java-extension

[otelfeature-java-extension](https://github.com/OTelFeature/otelfeature-java-extension)
is an agent extension that applies the telemetry flags from flagd, the Java
counterpart of geocode's otelfeature-instrument. How it decides and
re-parents spans is in its README and in
[entity_model.md](../../docs/spec/entity_model.md).

- The Dockerfile downloads the release JAR, pinned by
  `OTELFEATURE_EXTENSION_VERSION`, and `OTEL_JAVAAGENT_EXTENSIONS` loads it.
  Test unreleased extension code with `make e2e OTELFEATURE_EXTENSION_REF=<ref>`.
- It uses flagd's in-process resolver on the sync port `8015`.
- Compose sets
  `OTEL_INSTRUMENTATION_COMMON_EXPERIMENTAL_CONTROLLER_TELEMETRY_ENABLED=true`.
  Without the `INTERNAL` controller spans, `telemetryLevel=IO` has almost
  nothing to drop in this service.

## Fault injection

The number flag `weatherUpstreamFailure` (0.0 to 1.0) makes that share of
`/weather` requests fail with HTTP 503 before the cache lookup, so the error
rate doesn't depend on the cache. The server span gets status ERROR, and the
reason ("Injected upstream failure") is in its exception event, not in the
response body. See [entity_model.md#flags](../../docs/spec/entity_model.md#flags)
for the variants.

[FaultInjection.java](src/main/java/otelfeature/poc/FaultInjection.java)
evaluates it with the OpenFeature Java SDK and the flagd provider (in-process,
same `FLAGD_HOST`/`FLAGD_PORT`), separate from the extension's isolated
OpenFeature instance. It uses no evaluation context, so it applies to
`weather` and `weather-staging` alike. Until flagd is first reachable, or if
the flag is missing, nothing fails. If flagd goes away later, the last
synced value stays.

The client has the OpenFeature OpenTelemetry traces hook
(`dev.openfeature.contrib.hooks:otel` 3.3.1), so every evaluation adds a
`feature_flag` event to the current span. Its attributes use the semconv 1.28
names (`feature_flag.key`, `feature_flag.variant`,
`feature_flag.provider_name`); [build.gradle](build.gradle) pins that
version because the spec expects them. The extension's own evaluations are
not recorded.

What to expect in the traces: because this client lives in the application,
the agent instruments its gRPC calls to flagd. There is a
`flagd.sync.v1.FlagSyncService/GetMetadata` span at startup and a
`SyncFlags` span when the sync stream ends. If an evaluation fails, for
example before flagd is reachable, the hook adds an exception event to the
current span without changing its status.

## Configuration

| Environment variable | Default | Description |
|---|---|---|
| `WEATHER_PORT` | `8001` | Listen port |
| `OPEN_METEO_GEOCODING_URL` | `https://geocoding-api.open-meteo.com/v1/search` | Open-Meteo geocoding endpoint. Compose uses [stub-apis](../stub-apis) unless started with `make start-live` |
| `OPEN_METEO_FORECAST_URL` | `https://api.open-meteo.com/v1/forecast` | Open-Meteo forecast endpoint, same as above |
| `POSTGRES_HOST` | `coordinates-db` | Postgres host |
| `POSTGRES_PORT` | `5432` | Postgres port |
| `POSTGRES_USER` | `postgres` | Postgres user |
| `POSTGRES_PWD` | `password` | Postgres password |
| `POSTGRES_DB` | `coordinates` | Postgres database |
| `FLAGD_HOST` | `localhost` | flagd host for the extension and the fault-injection client. `localhost` is the app's default; compose sets `flagd` |
| `FLAGD_PORT` | `8015` | flagd gRPC sync port |
| `FLAGD_COMPILE_TARGETING` | `auto` | Compose sets `disabled`: the extension classloader can't see `javax.tools`, so `auto` crashes the agent at startup (`NoClassDefFoundError`) |
| `OTEL_SERVICE_NAME` | - | Service name |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | - | Collector endpoint |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | - | OTLP protocol (compose: `http/protobuf`) |
| `OTEL_RESOURCE_ATTRIBUTES` | - | Compose sets `deployment.environment.name` (`production` or `staging`), `service.namespace`, `service.version` and `service.instance.id`. Flag rules can target them |

## Running locally

```sh
gradle bootRun
```

That runs without telemetry. With the agent and the extension:

```sh
java -javaagent:opentelemetry-javaagent.jar \
     -Dotel.javaagent.extensions=otelfeature-java-extension.jar \
     -Dotel.service.name=weather \
     -Dotel.exporter.otlp.endpoint=http://localhost:4318 \
     -jar build/libs/weather-0.1.0.jar
```

The service keeps serving requests without a collector (exports retry in
the background) and without Postgres (every request goes to the APIs).

Unit tests run in the Dockerfile's `test` stage: `make unit-test` from the
repo root.

## Running via Docker Compose

```sh
docker compose up -d --build weather
```

Without `--build`, compose runs the image it already has (the prebuilt one
from GHCR, or an earlier build), so your code changes don't show up. The JVM
and agent take a while to start; the healthcheck allows two minutes.
