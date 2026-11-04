# load-generator

A [k6](https://k6.io/) script, [load-test.js](load-test.js), that sends
steady traffic to [geocode](../geocode) and [weather](../weather). It runs
in the stock `grafana/k6` image with the script mounted in; there is no
build step. With the `staging` profile, `load-generator-staging` runs the
same script against the staging twins.

## Scenarios

Four `constant-arrival-rate` scenarios run at the same time, so the rate
holds regardless of response latency:

| Scenario | Endpoint | Rate |
|---|---|---|
| `geocode` | `POST /geocode` | `REQUEST_RATE` per `REQUEST_INTERVAL_SECONDS` |
| `weather` | `POST /weather` | `REQUEST_RATE` per `REQUEST_INTERVAL_SECONDS` |
| `healthchecks` | `GET /health` on both services | `HEALTHCHECK_RATE` per second, per service |
| `forecast` | `POST /forecast` on `geocode`, which calls `weather` | 1 per `FORECAST_INTERVAL_SECONDS` |

Each request picks a random pair from `LOCATIONS`. All scenarios share that
list, so `weather` finds the coordinates `geocode` cached. If you add a
location, add it to [stub-apis](../stub-apis/stub.py) too.

k6 sends no trace context, so every health check is a root `SERVER` span of
its own trace. `forecast` stays at one request per 15 s so that a `weather`
incident can't push `geocode`'s error rate over the control-loop threshold
(UC-005 A7).

## Configuration

| Environment variable | Script default | Compose | Description |
|---|---|---|---|
| `GEOCODE_BASE_URL` | `http://geocode:8000` | same | `geocode` base URL |
| `WEATHER_BASE_URL` | `http://weather:8001` | same | `weather` base URL |
| `REQUEST_INTERVAL_SECONDS` | `5` | `1` | Interval for the `geocode` and `weather` scenarios |
| `REQUEST_RATE` | `1` | - | Requests per interval for those two (the bench harness raises it) |
| `HEALTHCHECK_RATE` | `2` | `2` | Health checks per second, per service. Whole number, `0` = off |
| `FORECAST_INTERVAL_SECONDS` | `15` | `15` | Seconds between `/forecast` requests. Whole number, `0` = off |
| `DURATION` | `1h` | `15m` | Run time. `make demo-reset` restarts k6 |
| `K6_OTEL_GRPC_EXPORTER_ENDPOINT` | - | `otel-collector:4317` | Collector endpoint for k6's own metrics |
| `K6_OTEL_GRPC_EXPORTER_INSECURE` | - | `true` | No TLS for that export |
| `K6_OTEL_SERVICE_NAME` | - | `load-generator` | `service.name` of k6's metrics |

A `HEALTHCHECK_RATE` or `FORECAST_INTERVAL_SECONDS` that isn't a whole
number makes k6 exit at startup. Changing any variable needs a k6 restart.

With `make start-live`, only cache misses reach the real APIs. Nominatim's
usage policy allows about 1 request per second per source IP, and more gets
HTTP 429. The default stub has no limit.

## Running standalone

```sh
docker compose run --rm -e DURATION=30s load-generator
```

## Telemetry

k6 exports its own test metrics (`http_reqs`, `http_req_duration`,
`http_req_failed`, ...) over OTLP/gRPC to `otel-collector`. Split them by
the `scenario` tag; the health checks are in there too. Only the gRPC
exporter works with this image; the HTTP exporter variables were ignored in
testing.
