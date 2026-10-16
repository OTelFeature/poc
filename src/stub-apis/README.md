# stub-apis

An offline stand-in for the two external APIs the demo calls, so the stack
runs on stage with no network (OTelFeature/poc#24):

| Real API | Stub path | Called by |
|---|---|---|
| [Nominatim search](https://nominatim.org/release-docs/latest/api/Search/) | `GET /search?format=json&q=<city>,<country>` | `geocode` |
| [Open-Meteo geocoding](https://open-meteo.com/en/docs/geocoding-api) | `GET /v1/search?name=<city>&country=<country>` | `weather` |
| [Open-Meteo forecast](https://open-meteo.com/en/docs) | `GET /v1/forecast?latitude=..&longitude=..` | `weather` |

It knows the city/country pairs in the
[load generator's](../load-generator/load-test.js) `LOCATIONS` list. Any other
location gets the same empty answer the real API gives, so the services
return `404` as they would live. Forecast values are random. Every API
response waits 20–120 ms, so the outgoing `CLIENT` spans look like real
network calls (with `server.address` = `stub-apis`).

[stub.py](stub.py) uses only the Python standard library. Compose runs it on
the stock `python:3.14-slim-bookworm` image with the script mounted in, so
there is no build step.

If you add a location to `load-test.js`, add it to `LOCATIONS` in `stub.py`
too.

## Switching between stub and real APIs

`geocode` reads `NOMINATIM_URL`, `weather` reads `OPEN_METEO_GEOCODING_URL`
and `OPEN_METEO_FORECAST_URL`. Compose defaults all three to this stub;
`make start-live` sets them to the real endpoints. Postgres caches results
either way, so after a live run the stub sees fewer calls.

## Configuration

| Environment variable  | Default | Description |
|-----------------------|---------|-------------|
| `STUB_PORT`           | `8080`  | Listen port |
| `STUB_LATENCY_MIN_MS` | `20`    | Lower bound of the random response delay |
| `STUB_LATENCY_MAX_MS` | `120`   | Upper bound of the random response delay |

## Running standalone

```sh
python src/stub-apis/stub.py
curl 'http://localhost:8080/search?format=json&q=linz,austria'
```
