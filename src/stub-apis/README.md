# stub-apis

An offline stand-in for the external APIs, so the stack runs without network:

| Real API | Stub path | Called by |
|---|---|---|
| [Nominatim search](https://nominatim.org/release-docs/latest/api/Search/) | `GET /search?format=json&q=<city>,<country>` | `geocode` |
| [Open-Meteo geocoding](https://open-meteo.com/en/docs/geocoding-api) | `GET /v1/search?name=<city>&country=<country>` | `weather` |
| [Open-Meteo forecast](https://open-meteo.com/en/docs) | `GET /v1/forecast?latitude=..&longitude=..` | `weather` |

It knows the locations in the
[load generator's](../load-generator/load-test.js) `LOCATIONS` list. Other
locations get the real API's empty answer, so the services return `404`.
Forecast values are random. Each API response waits a random 20 to 120 ms,
so the `CLIENT` spans look like network calls. `GET /health` answers at once.

[stub.py](stub.py) uses only the Python standard library. The
[Dockerfile](Dockerfile) copies it into the stock Python image, published as
`ghcr.io/otelfeature/poc-stub-apis`. After editing `stub.py`, run
`docker compose up -d --build stub-apis`. If you add a location to
`load-test.js`, add it to `LOCATIONS` in `stub.py` too.

## Stub or real APIs

Compose points `NOMINATIM_URL` (geocode) and `OPEN_METEO_GEOCODING_URL`,
`OPEN_METEO_FORECAST_URL` (weather) at this stub. `make start-live` sets
them to the real endpoints for that run only. To stay live, put the three
variables in `.env`.

Postgres caches results with no expiry, so the stub or the real API is only
called on a cache miss. `docker compose --profile staging down -v` empties
the cache.

## Configuration

| Environment variable | Default | Description |
|---|---|---|
| `STUB_PORT` | `8080` | Listen port |
| `STUB_LATENCY_MIN_MS` | `20` | Lower bound of the response delay |
| `STUB_LATENCY_MAX_MS` | `120` | Upper bound of the response delay |

## Running standalone

```sh
python src/stub-apis/stub.py
curl 'http://localhost:8080/search?format=json&q=linz,austria'
```
