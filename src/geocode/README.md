# geocode

A FastAPI service that resolves a city and country to latitude and longitude.
It looks in the `coordinates` table of [coordinates-db](../coordinates-db)
first and calls the
[Nominatim](https://nominatim.org/release-docs/latest/api/Search/) search API
on a miss, then stores the result. Without the database it still works and
calls Nominatim every time.

## API

| Endpoint | Body | Returns |
|---|---|---|
| `POST /geocode` | `{"city": "linz", "country": "austria"}` | `{"latitude": 48.3059078, "longitude": 14.286198}`; `404` for an unknown location |
| `POST /forecast` | same as `/geocode` | the coordinates plus `weather`'s answer under `"weather"`; `404` for an unknown location, `502` if `weather` fails or can't be reached |
| `GET /health` | | `{"status": "ok"}` |

`/forecast` calls `weather`'s `POST /weather` at `WEATHER_URL`. Its traces
span both services, and `geocode` makes the sampling decision.

```sh
curl -s -X POST http://localhost:8000/geocode \
  -H "Content-Type: application/json" \
  -d '{"city": "linz", "country": "austria"}'
```

### Fault injection

The number flag `geocodeUpstreamFailure` (0.0 to 1.0) makes that share of
`/geocode` requests, and so of `/forecast`, fail with `503` before the cache
lookup. Only the e2e suite sets it; the stage presets don't define it, so it
resolves to 0.0. `geocode` evaluates it with its own OpenFeature client,
which has the OpenFeature OpenTelemetry traces hook, so the failed request's
span carries the evaluation as an event. See
[entity_model.md#flags](../../docs/spec/entity_model.md#flags).

## Configuration

| Environment variable | Default | Description |
|---|---|---|
| `GEOCODE_PORT` | `8000` | Listen port |
| `NOMINATIM_URL` | `https://nominatim.openstreetmap.org/search` | Nominatim search endpoint. Compose uses [stub-apis](../stub-apis) unless started with `make start-live` |
| `NOMINATIM_USER_AGENT` | `poc-otelfeature-geocode/1.0` | `User-Agent` sent to Nominatim |
| `WEATHER_URL` | `http://weather:8001` | `weather` base URL for `/forecast` |
| `POSTGRES_HOST` | `coordinates-db` | Postgres host |
| `POSTGRES_PORT` | `5432` | Postgres port |
| `POSTGRES_USER` | `postgres` | Postgres user |
| `POSTGRES_PWD` | `password` | Postgres password |
| `POSTGRES_DB` | `coordinates` | Postgres database |
| `FLAGD_HOST` | `localhost` | flagd host (compose: `flagd`) |
| `FLAGD_PORT` | `8015` | flagd gRPC sync port |
| `OTEL_SERVICE_NAME` | - | Service name |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | - | Collector endpoint (OTLP/HTTP) |
| `OTEL_SEMCONV_STABILITY_OPT_IN` | - | Compose sets `http`, so the server span has `url.path` at start, which flag rules on the path need |
| `OTEL_RESOURCE_ATTRIBUTES` | - | Compose sets `deployment.environment.name` (`production` or `staging`), `service.namespace`, `service.version` and `service.instance.id`. Flag rules can target them |

## Telemetry

`main.py` has no OpenTelemetry setup. The service runs under
[otelfeature-instrument](https://github.com/OTelFeature/otelfeature-instrument),
a zero-code launcher like `opentelemetry-instrument` (see the `CMD` in the
[Dockerfile](Dockerfile)). It instruments `fastapi`, `httpx` and `psycopg2`,
which stay in [pyproject.toml](pyproject.toml) so it can find them, and
applies the telemetry flags. The one manual span, `geocode.resolve`, is
`INTERNAL`, so `telemetryLevel=IO` drops it and its `CLIENT` children attach
to the server span.

## Running locally

```sh
uv sync
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
OTEL_SERVICE_NAME=geocode \
  uv run otelfeature-instrument uvicorn main:app --reload
```

The service keeps serving requests without a collector (exports retry in
the background), without Postgres (every lookup goes to Nominatim, and the
log shows the exception) and without flagd (the flags use their defaults
until flagd is reachable).

Unit tests ([test_fault_injection.py](test_fault_injection.py)) run in the
Dockerfile's `test` stage: `make unit-test` from the repo root.

## Running via Docker Compose

```sh
docker compose up -d --build geocode
```

Without `--build`, compose runs the image it already has (the prebuilt one
from GHCR, or an earlier build). Your code changes and a new
`otelfeature-instrument` pin don't show up, which can look like a flagd
problem.

## Dependencies

Dependencies are declared in [pyproject.toml](pyproject.toml) and locked in
[uv.lock](uv.lock). Change them with `uv add` / `uv remove`, which update
both files. After editing `pyproject.toml` by hand, run:

```sh
uv lock                 # regenerate uv.lock
uv sync --locked        # make .venv match it
```

The Docker build runs `uv sync --locked` and fails if `uv.lock` is stale.

`otelfeature-instrument` is a git dependency (`[tool.uv.sources]`), pinned to
a release tag (`tag = "v0.4.0"`, C-006). That is why the builder stage
installs `git`. To bump it, change `tag` and run
`uv lock --upgrade-package otelfeature-instrument`. Test unreleased extension
code with `make e2e OTELFEATURE_INSTRUMENT_REF=<ref>` or an `-rc` pre-release
(C-013), never through this pin.
