# geocode

A small FastAPI service that resolves a city/country to latitude/longitude.

On each request it first checks the `coordinates` table in Postgres
(`coordinates-db`). On a cache hit, it returns immediately with no external
call. On a miss, it queries the
[Nominatim](https://nominatim.org/release-docs/latest/api/Search/) search
API, persists the result, and returns it. If the database is unreachable,
lookups just always fall through to Nominatim — caching is an optimization,
not a hard dependency.

## API

### `POST /geocode`

Request body:

```json
{
  "city": "linz",
  "country": "austria"
}
```

Response body:

```json
{
  "latitude": 48.3059078,
  "longitude": 14.286198
}
```

Returns `404` if no location matches the given city/country.

### `GET /health`

Liveness check, returns `{"status": "ok"}`.

## curl example

```sh
curl -s -X POST http://localhost:8000/geocode \
  -H "Content-Type: application/json" \
  -d '{"city": "linz", "country": "austria"}'
```

## Configuration

| Environment variable          | Default                       | Description                                    |
|-------------------------------|-------------------------------|------------------------------------------------|
| `GEOCODE_PORT`                | `8000`                        | Port uvicorn listens on                        |
| `NOMINATIM_USER_AGENT`        | `poc-otelfeature-geocode/1.0` | `User-Agent` header sent to Nominatim          |
| `OTEL_SERVICE_NAME`           | -                             | Service name reported in telemetry             |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | -                             | OTLP collector endpoint                        |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | -                             | OTLP wire protocol (e.g. `http/protobuf`)      |
| `POSTGRES_HOST`               | `coordinates-db`              | Postgres host                                  |
| `POSTGRES_PORT`               | `5432`                        | Postgres port                                  |
| `POSTGRES_USER`               | `postgres`                    | Postgres user                                  |
| `POSTGRES_PWD`                | `password`                    | Postgres password                              |
| `POSTGRES_DB`                 | `coordinates`                 | Postgres database name                         |

## Running locally

Only the OTLP/HTTP exporter is installed, so `OTEL_EXPORTER_OTLP_PROTOCOL`
must be set to `http/protobuf` (otherwise auto-instrumentation defaults to
the gRPC exporter, which isn't installed, and telemetry init fails).

```sh
uv sync
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
OTEL_SERVICE_NAME=geocode \
  uv run opentelemetry-instrument uvicorn main:app --reload
```

Without a collector running at `OTEL_EXPORTER_OTLP_ENDPOINT`, the app still
serves requests fine — exports just fail/retry in the background. Same for
Postgres: without `coordinates-db` reachable, requests still succeed, just
always querying Nominatim (logged as an exception, but non-fatal).

## Dependencies

Dependencies are declared in [pyproject.toml](pyproject.toml) and pinned in
[uv.lock](uv.lock). To update the lock file:

```sh
uv lock                 # regenerate uv.lock from pyproject.toml
uv sync --locked        # reinstall .venv to match the lock file exactly
```

Use `uv add <package>` / `uv remove <package>` to change dependencies — both
update `pyproject.toml` and `uv.lock` together, so `uv lock` is only needed
when `pyproject.toml` (or the Python version pin) changed by other means, e.g.
after manually editing `requires-python` or a version constraint.

The Docker build runs `uv sync --locked` (see [Dockerfile](Dockerfile)),
which fails if `uv.lock` is out of sync with `pyproject.toml` — run `uv lock`
locally first if the build complains about a stale lock file.

## Running via Docker Compose

The service is wired up as `geocode` in the repo-root [compose.yaml](../../compose.yaml),
alongside the OpenTelemetry Collector it exports traces to:

```sh
docker compose up --build geocode
```

## Telemetry

The service is auto-instrumented via `opentelemetry-distro`
(`opentelemetry-instrument`), covering the inbound FastAPI requests, the
outbound `httpx` calls to Nominatim, and the `psycopg2` queries against
`coordinates-db` — all correlated under one trace per request. Traces,
metrics, and logs are exported over OTLP/HTTP to the collector configured via
`OTEL_EXPORTER_OTLP_ENDPOINT`.
