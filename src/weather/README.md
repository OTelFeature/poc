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
| `POSTGRES_HOST`               | `coordinates-db`  | Postgres host (shared with geocode)                  |
| `POSTGRES_PORT`               | `5432`            | Postgres port                                       |
| `POSTGRES_USER`               | `postgres`        | Postgres user                                        |
| `POSTGRES_PWD`                | `password`        | Postgres password                                    |
| `POSTGRES_DB`                 | `coordinates`     | Postgres database name                              |
| `OTEL_SERVICE_NAME`           | -                 | Service name reported in telemetry                  |
| `OTEL_EXPORTER_OTLP_ENDPOINT`  | -                 | OTLP collector endpoint                             |
| `OTEL_EXPORTER_OTLP_PROTOCOL`  | -                 | OTLP protocol (`http/protobuf`, `grpc`, etc.)       |
| `FLAGD_HOST`                  | `flagd`           | flagd host (for `telemetryLevel` flag evaluation)  |
| `FLAGD_PORT`                  | `8015`            | flagd gRPC **sync** port (in-process resolver)      |
| `FLAGD_COMPILE_TARGETING`     | `auto`            | flagd targeting-rule compile mode. Set to `disabled` — the agent's extension classloader can't see `javax.tools`, so the `auto` probe crashes the agent at startup (`NoClassDefFoundError`) |

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
