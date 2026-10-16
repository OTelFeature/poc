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

| Environment variable          | Default                       | Description                                                                         |
|-------------------------------|-------------------------------|-------------------------------------------------------------------------------------|
| `GEOCODE_PORT`                | `8000`                        | Port uvicorn listens on                                                             |
| `NOMINATIM_URL`               | `https://nominatim.openstreetmap.org/search` | Nominatim search endpoint. Compose points it at [stub-apis](../stub-apis) unless started with `make start-live` |
| `NOMINATIM_USER_AGENT`        | `poc-otelfeature-geocode/1.0` | `User-Agent` header sent to Nominatim                                               |
| `OTEL_SERVICE_NAME`           | -                             | Service name reported in telemetry                                                  |
| `OTEL_SEMCONV_STABILITY_OPT_IN` | - | Compose sets `http`: stable HTTP semconv, so the server span has `url.path` at start (flag rules on the path need it) and the duration metric is `http.server.request.duration` |
| `OTEL_RESOURCE_ATTRIBUTES` | - | Compose sets `deployment.environment.name` (`production`, or `staging` for the staging twin), `service.namespace=otelfeature` and `service.version`; flag rules can target them |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | -                             | OTLP collector endpoint (OTLP/HTTP always)                                          |
| `FLAGD_HOST`                  | `localhost`                   | flagd host, used to resolve the `telemetryLevel` flag (see [Telemetry](#telemetry)) |
| `FLAGD_PORT`                  | `8015`                        | flagd gRPC sync port (in-process resolver)                                          |
| `POSTGRES_HOST`               | `coordinates-db`              | Postgres host                                                                       |
| `POSTGRES_PORT`               | `5432`                        | Postgres port                                                                       |
| `POSTGRES_USER`               | `postgres`                    | Postgres user                                                                       |
| `POSTGRES_PWD`                | `password`                    | Postgres password                                                                   |
| `POSTGRES_DB`                 | `coordinates`                 | Postgres database name                                                              |

## Running locally

```sh
uv sync
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
OTEL_SERVICE_NAME=geocode \
  uv run otelfeature-instrument uvicorn main:app --reload
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

> [!NOTE]
> `otelfeature-instrument` isn't published to a package index yet — it's
> pulled straight from its GitHub repo (`[tool.uv.sources]` in
> [pyproject.toml](pyproject.toml)). That's why the Dockerfile's builder
> stage installs `git` before running `uv sync`: without it, resolving that
> dependency fails with "Git executable not found." `uv lock` re-pins it to
> the repo's current `HEAD` commit; if you've pushed new commits there and
> want geocode to pick them up, re-run `uv lock`.

## Running via Docker Compose

The service is wired up as `geocode` in the repo-root [compose.yaml](../../compose.yaml),
alongside the OpenTelemetry Collector it exports traces to:

```sh
docker compose up --build geocode
```

> [!TIP]
> The `--build` matters: `compose.yaml` doesn't rebuild on its own when
> `src/geocode`'s code changes, or when `otelfeature-instrument`'s repo gets
> new commits (only `uv lock` re-pins to them — see
> [Dependencies](#dependencies)). Running `docker compose up -d` (no
> `--build`) silently keeps serving the old image — symptoms look like a
> flagd/config problem (e.g. flipping `telemetryLevel` in
> [flagd.json](../flagd/flagd.json) appears to do nothing) when it's
> actually just a stale container.

## Telemetry

`main.py` has zero OpenTelemetry configuration code — telemetry is bootstrapped
entirely by [otelfeature-instrument](https://github.com/OTelFeature/otelfeature-instrument),
a zero-code launcher (like `opentelemetry-instrument`) that this service runs
under instead of running `uvicorn` directly (see the `CMD` in
[Dockerfile](Dockerfile)). It handles resource detection, OTLP export, and
zero-code instrumentation of `fastapi`/`httpx`/`psycopg2` (all still declared
as dependencies in [pyproject.toml](pyproject.toml) so it can discover them),
exported over OTLP/HTTP to the collector configured via
`OTEL_EXPORTER_OTLP_ENDPOINT` — all correlated under one trace per request.

The one manual span in this codebase is `geocode.resolve` in
[main.py](main.py), wrapping the cache-lookup/Nominatim-call/persist logic —
kept purely to have something concrete for the flag below to suppress.

### The `telemetryLevel` flag

`otelfeature-instrument`'s one addition over a plain zero-code launcher:
trace verbosity is controlled live, with no restart, via
[OpenFeature](https://openfeature.dev/) and [flagd](https://flagd.dev/) (see
[src/flagd](../flagd)). When the `telemetryLevel` flag evaluates to `IO`, any
span of kind `INTERNAL` — `geocode.resolve` above, and the ASGI-level spans
FastAPI's instrumentation creates — is suppressed transparently: never
created, never attached to context. Its would-be children (the
`psycopg2`/`httpx` `CLIENT` spans) attach directly to the real parent
instead, so nothing is orphaned. See
[otelfeature-instrument's README](https://github.com/OTelFeature/otelfeature-instrument#how-it-works)
for exactly how (and why a `Sampler` can't do this cleanly), and
[flagd's README](../flagd/README.md#updating-a-flag) for how to flip the
flag — this service just consumes it via `FLAGD_HOST`/`FLAGD_PORT`.

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
