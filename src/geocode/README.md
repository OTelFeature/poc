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
| `OTEL_EXPORTER_OTLP_ENDPOINT` | -                             | OTLP collector endpoint (OTLP/HTTP always)     |
| `FLAGD_HOST`                  | `localhost`                   | flagd host, used to resolve the `telemetryLevel` flag (see [Telemetry](#telemetry)) |
| `FLAGD_PORT`                  | `8015`                        | flagd gRPC sync port (in-process resolver)     |
| `POSTGRES_HOST`               | `coordinates-db`              | Postgres host                                  |
| `POSTGRES_PORT`               | `5432`                        | Postgres port                                  |
| `POSTGRES_USER`               | `postgres`                    | Postgres user                                  |
| `POSTGRES_PWD`                | `password`                    | Postgres password                              |
| `POSTGRES_DB`                 | `coordinates`                 | Postgres database name                         |

## Running locally

```sh
uv sync
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
OTEL_SERVICE_NAME=geocode \
  uv run uvicorn main:app --reload
```

Without a collector running at `OTEL_EXPORTER_OTLP_ENDPOINT`, the app still
serves requests fine — exports just fail/retry in the background. Same for
Postgres: without `coordinates-db` reachable, requests still succeed, just
always querying Nominatim (logged as an exception, but non-fatal). Without
flagd reachable at `FLAGD_HOST`/`FLAGD_PORT`, `telemetryLevel` evaluations
just fall back to the hardcoded default (`FULL`) until it becomes reachable.

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

> [!TIP]
> The `--build` matters: `compose.yaml` doesn't rebuild on its own when
> `src/geocode`'s code changes. Running `docker compose up -d` (no `--build`)
> after editing e.g. [otel_setup.py](otel_setup.py) silently keeps serving
> the old image — symptoms look like a flagd/config problem (e.g. flipping
> `telemetryLevel` in [flagd.json](../flagd/flagd.json) appears to do
> nothing) when it's actually just a stale container.

## Telemetry

Telemetry is bootstrapped by hand in [otel_setup.py](otel_setup.py) rather
than via the zero-code `opentelemetry-instrument` launcher, so that a custom
`TracerProvider`/`Tracer` can sit between the instrumentation libraries and
the SDK. The `FastAPIInstrumentor`, `HTTPXClientInstrumentor`, and
`Psycopg2Instrumentor` are still wired up explicitly in [main.py](main.py),
covering the inbound FastAPI requests, the outbound `httpx` calls to
Nominatim, and the `psycopg2` queries against `coordinates-db` — all
correlated under one trace per request, exported over OTLP/HTTP to the
collector configured via `OTEL_EXPORTER_OTLP_ENDPOINT`.

### The `telemetryLevel` flag

This is a prototype of controlling trace verbosity live, without an app
restart, via [OpenFeature](https://openfeature.dev/) and
[flagd](https://flagd.dev/) (see [src/flagd](../flagd)): `otel_setup.py`
wraps the real `TracerProvider`/`Tracer` so that, when the `telemetryLevel`
flag evaluates to `IO`, any span of kind `INTERNAL` —
[main.py](main.py)'s own `geocode.resolve` span, and the ASGI-level spans
FastAPI's instrumentation creates — is never created and never attached to
context. Its would-be children (the `psycopg2`/`httpx` `CLIENT` spans) attach
directly to the real parent instead, so nothing is orphaned; the suppressed
span simply never existed.

The flagd provider runs in ["in-process" resolver
mode](https://flagd.dev/reference/specifications/in-process-providers/):
geocode syncs the flag ruleset from flagd once (over gRPC, `FLAGD_PORT`,
default `8015`) and evaluates it in memory on every span — no network call on
the per-span hot path. flagd pushes ruleset updates over that same stream as
they happen, so editing [src/flagd/flagd.json](../flagd/flagd.json) (or
whatever's behind flagd's configured source) takes effect on geocode's very
next span, with no restart. See [flagd's README](../flagd/README.md#updating-a-flag)
for how to flip it.

With `telemetryLevel=FULL`, a `/geocode` request that misses cache produces:

```
POST /geocode                    (SERVER)
├─ http receive / http send × N  (INTERNAL, from the ASGI instrumentation)
└─ geocode.resolve                (INTERNAL, from main.py)
   └─ GET                         (CLIENT, httpx → Nominatim)
```

With `telemetryLevel=IO`, the same request produces:

```
POST /geocode      (SERVER)
└─ GET              (CLIENT, httpx → Nominatim)
```
