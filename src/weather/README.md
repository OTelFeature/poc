# weather

A Java 25 / Spring Boot 4.1 service that resolves current weather for a
city/country pair, using the [Open-Meteo](https://open-meteo.com/) API (free,
no API key, generous rate limits — no Nominatim rate-limit conflicts).

On each request it:

1. Checks the `weather` cache table in Postgres (`coordinates-db`) — returns
   immediately on a hit.
2. On a miss, looks up coordinates in the `coordinates` table (shared with the
   [geocode](../geocode) service). If not found there either, it queries
   Open-Meteo's geocoding API and persists the coordinates for next time.
3. Queries the Open-Meteo forecast API with the coordinates.
4. Persists the weather result in the `weather` table and returns it.

If the database is unreachable, the service still serves requests from the
API — caching is an optimization, not a hard dependency.

## Instrumentation

This service uses the [OpenTelemetry Java auto-instrumentation
agent](https://github.com/open-telemetry/opentelemetry-java-instrumentation)
— a `-javaagent` JAR that instruments supported libraries with **zero code
changes**:

| Library | Auto-instrumented span type |
|---------|---------------------------|
| Spring Boot (embedded Tomcat) | `SERVER` — incoming HTTP requests |
| JDBC (PostgreSQL driver) | `CLIENT` — database queries |
| `java.net.http.HttpClient` | `CLIENT` — outgoing API calls |

The agent JAR is downloaded in a dedicated Docker build stage and attached
via `-javaagent` in the `CMD`. The agent version is pinned via a build arg
(`OTEL_AGENT_VERSION` in [Dockerfile](Dockerfile)). Configuration is entirely
through environment variables — no code-level OpenTelemetry imports or setup.

### otelfeature-java-extension

This service also uses
[otelfeature-java-extension](https://github.com/OTelFeature/otelfeature-java-extension),
an OTel Java agent extension that adds flagd-controlled `INTERNAL` span
suppression — the Java counterpart to the Python
[otelfeature-instrument](https://github.com/OTelFeature/otelfeature-instrument).

The extension wraps the agent's span exporter and, when the `telemetryLevel`
flag served by flagd is set to `"IO"`, drops `INTERNAL` spans (e.g. Spring
WebMVC controller spans) while **re-parenting** their children to the
nearest non-suppressed ancestor — preserving the trace tree instead of
orphaning child spans. Flip the flag in
[flagd.json](../flagd/flagd.json) and the change takes effect on the very next
span — no restart needed.

The extension uses flagd's
[in-process resolver](https://flagd.dev/reference/specifications/in-process-providers/)
(gRPC sync port `8015`), the same mechanism `geocode` uses: flagd pushes the
whole flag ruleset to the JVM and keeps it current, so evaluation never leaves
the process. Earlier versions polled flagd's OFREP REST endpoint (`8016`) every
five seconds instead — hence the `FLAGD_PORT` change in
[compose.yaml](../../compose.yaml).

Controller spans must be enabled for the extension to have something to
suppress, so `OTEL_INSTRUMENTATION_COMMON_EXPERIMENTAL_CONTROLLER_TELEMETRY_ENABLED=true`
is set in [compose.yaml](../../compose.yaml).

The extension JAR is downloaded from [GitHub Releases](https://github.com/OTelFeature/otelfeature-java-extension/releases)
during the Docker build (pinned via `OTELFEATURE_EXTENSION_VERSION` in
[Dockerfile](Dockerfile)) and loaded by the agent via
`OTEL_JAVAAGENT_EXTENSIONS`.

## API

### `POST /weather`

```sh
curl -s -X POST http://localhost:8001/weather \
  -H "Content-Type: application/json" \
  -d '{"city": "linz", "country": "austria"}'
```

Response:

```json
{
  "latitude": 48.3069,
  "longitude": 14.2857,
  "temperature": 12.5,
  "windspeed": 3.2,
  "weatherCode": 61,
  "weatherDescription": "Rain"
}
```

### `GET /health`

```sh
curl -s http://localhost:8001/health
# {"status":"ok"}
```

## Configuration

| Environment variable          | Default           | Description                                         |
|-------------------------------|-------------------|-----------------------------------------------------|
| `WEATHER_PORT`                | `8001`            | Port the embedded Tomcat server listens on          |
| `OPEN_METEO_GEOCODING_URL`    | `https://geocoding-api.open-meteo.com/v1/search` | Open-Meteo geocoding endpoint. Compose points it at [stub-apis](../stub-apis) unless started with `make start-live` |
| `OPEN_METEO_FORECAST_URL`     | `https://api.open-meteo.com/v1/forecast` | Open-Meteo forecast endpoint, same as above |
| `POSTGRES_HOST`               | `coordinates-db`  | Postgres host (shared with geocode)                  |
| `POSTGRES_PORT`               | `5432`            | Postgres port                                       |
| `POSTGRES_USER`               | `postgres`        | Postgres user                                        |
| `POSTGRES_PWD`                | `password`        | Postgres password                                    |
| `POSTGRES_DB`                 | `coordinates`     | Postgres database name                              |
| `OTEL_SERVICE_NAME`           | -                 | Service name reported in telemetry                  |
| `OTEL_RESOURCE_ATTRIBUTES` | - | Compose sets `deployment.environment.name` (`production`, or `staging` for the staging twin), `service.namespace=otelfeature` and `service.version`; flag rules can target them |
| `OTEL_EXPORTER_OTLP_ENDPOINT`  | -                 | OTLP collector endpoint                             |
| `OTEL_EXPORTER_OTLP_PROTOCOL`  | -                 | OTLP protocol (`http/protobuf`, `grpc`, etc.)       |
| `FLAGD_HOST`                  | `flagd`           | flagd host for the extension's telemetry flags and for `weatherUpstreamFailure` (the app's own default is `localhost`; compose sets `flagd`). `FLAGD_PORT` and `FLAGD_COMPILE_TARGETING` apply to both clients too |
| `FLAGD_PORT`                  | `8015`            | flagd gRPC **sync** port (in-process resolver)      |
| `FLAGD_COMPILE_TARGETING`     | `auto`            | flagd targeting-rule compile mode. Set to `disabled` — the agent's extension classloader can't see `javax.tools`, so the `auto` probe crashes the agent at startup (`NoClassDefFoundError`) |

## Fault injection

`weather` reads one feature flag in its own code: `weatherUpstreamFailure`,
a number from 0.0 to 1.0 (OTelFeature/poc#28). That share of `/weather`
requests fails with HTTP 503 before the cache lookup, so the error rate is
steady whatever the cache holds (a real upstream outage would spare cache
hits). The reason ("Injected upstream failure") is in the exception event on
the span, not in the response body. The server span gets
status ERROR, and the span metrics count it as an error. That is the input
for Demo 3's incident beat (`make flag PRESET=03b-incident`, 0.5).

[FaultInjection.java](src/main/java/otelfeature/poc/FaultInjection.java)
uses the OpenFeature Java SDK with the flagd provider (in-process resolver,
same `FLAGD_HOST`/`FLAGD_PORT` as the extension). It is a normal application
client, separate from the agent extension's isolated OpenFeature instance.
Until flagd is first reachable, or if the flag is missing, nothing fails. If
flagd goes away later, the provider keeps serving the last value it synced.
The flag is evaluated without an evaluation context, so it applies to
`weather` and `weather-staging` alike.

Because this client lives in the application, the Java agent instruments its
gRPC calls to flagd: expect a `flagd.sync.v1.FlagSyncService/GetMetadata`
client span at startup, and a `SyncFlags` span when the sync stream ends.

### Flag evaluations in the trace

The app's OpenFeature client also has the OpenFeature OpenTelemetry traces
hook (`dev.openfeature.contrib.hooks:otel` 3.3.1, UC-007). Every
`weatherUpstreamFailure` evaluation adds a span event to the request's
current span, so a failed `/weather` trace shows which flag failed it. This
hook version uses the semantic conventions 1.28 names: event `feature_flag`
with `feature_flag.key`, `feature_flag.variant` and
`feature_flag.provider_name` (not yet `feature_flag.evaluation` /
`feature_flag.result.variant` / `feature_flag.provider.name`). The hook is on
the app's client only; the agent extension's own evaluations run in its
isolated OpenFeature API and are not recorded. If an evaluation fails (for
example while flagd isn't reachable yet at startup), the hook adds an
exception event to the current span; the span's status is unchanged.

## Running locally

```sh
gradle bootRun
```

Without the OTel agent attached, the app runs fine but produces no
telemetry. To run with instrumentation locally:

```sh
java -javaagent:opentelemetry-javaagent.jar \
     -Dotel.javaagent.extensions=otelfeature-java-extension.jar \
     -Dotel.service.name=weather \
     -Dotel.exporter.otlp.endpoint=http://localhost:4318 \
     -jar build/libs/weather-0.1.0.jar
```

Without a collector at `OTEL_EXPORTER_OTLP_ENDPOINT`, the app still serves
requests — exports just fail/retry in the background. Same for Postgres:
without `coordinates-db` reachable, requests still succeed, just always
querying the Open-Meteo APIs directly.

## Running via Docker Compose

The service is wired up as `weather` in the repo-root
[compose.yaml](../../compose.yaml):

```sh
docker compose up --build weather
```

> **Tip:** The `--build` matters — `compose.yaml` doesn't rebuild on its own
> when `src/weather`'s code changes. Running `docker compose up -d` (no
> `--build`) silently keeps serving the old image.
