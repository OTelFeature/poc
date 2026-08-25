# load-generator

A [k6](https://k6.io/) script that continuously sends requests to both
[geocode](../geocode) and [weather](../weather), so there's steady traffic
from two services to look at in the Aspire Dashboard.

Runs via the official `grafana/k6` image in [compose.yaml](../../compose.yaml)
— no build step, just the script in [load-test.js](load-test.js) mounted in.

## Behavior

The script defines two k6 scenarios that run **concurrently**:

| Scenario | Target | Endpoint | Rate |
|----------|--------|----------|------|
| `geocode` | `geocode` service | `POST /geocode` | 1 request / N seconds |
| `weather` | `weather` service | `POST /weather` | 1 request / N seconds |

Each iteration in each scenario picks a random city/country pair from a small
fixed list and POSTs it. Both scenarios use the same `LOCATIONS` list, so when
both services run together `geocode` populates the `coordinates` table and
`weather` finds those coordinates cached — minimizing external API calls.

k6's `constant-arrival-rate` executor holds a steady request rate regardless of
response latency.

> [!NOTE]
> Nominatim's public usage policy caps requests at ~1/s, *shared across all
> users of the source IP*. `geocode` caches resolved coordinates in
> `coordinates-db`, so only new city/country pairs cost a live Nominatim
> lookup — but the default rate here is still deliberately low (1 request
> every 5s) to stay well under that limit for whatever does miss the cache.
> Raise `REQUEST_INTERVAL_SECONDS` at your own risk of getting rate-limited
> (HTTP 429).
>
> Open-Meteo has no comparable rate limit, but the same interval is used for
> consistency and readability in the dashboard.

## Configuration

| Environment variable             | Default               | Description                                       |
|----------------------------------|-----------------------|---------------------------------------------------|
| `GEOCODE_BASE_URL`               | `http://geocode:8000` | Base URL of the `geocode` service                 |
| `WEATHER_BASE_URL`               | `http://weather:8001` | Base URL of the `weather` service                 |
| `REQUEST_INTERVAL_SECONDS`       | `5`                   | Seconds between requests per scenario (1 / N s)   |
| `DURATION`                       | `1h`                  | How long the test runs                            |
| `K6_OTEL_GRPC_EXPORTER_ENDPOINT` | -                     | Collector endpoint for k6's own OTLP/gRPC metrics |
| `K6_OTEL_GRPC_EXPORTER_INSECURE` | -                     | Disable TLS for the gRPC exporter                 |
| `K6_OTEL_SERVICE_NAME`           | -                     | `service.name` reported in k6's own telemetry     |

## Running standalone

```sh
docker compose run --rm -e DURATION=30s load-generator
```

## Telemetry

This isn't instrumentation of *application* code — it's k6 exporting its own
built-in test metrics (`http_req_duration`, `http_req_failed`, `iterations`,
etc.) over OTLP/gRPC to `otel-collector`, tagged with `service.name:
load-generator`. Only the gRPC exporter is confirmed working in this setup;
see [compose.yaml](../../compose.yaml) for the exact env vars — the HTTP
exporter env vars are documented upstream but were not honored by this k6
image in testing.
