"""Offline stand-in for the external APIs geocode and weather call.

Serves just enough of three APIs for the demo, on one port:

- Nominatim search          GET /search?format=json&q=<city>,<country>
- Open-Meteo geocoding      GET /v1/search?name=<city>&country=<country>
- Open-Meteo forecast       GET /v1/forecast?latitude=..&longitude=..&current=..

Only the k6 location list is known; anything else gets the same "not found"
answer the real API would give. Every response waits a small random time so
the outgoing CLIENT spans look like real network calls.

Standard library only, so the compose service runs it on a stock Python image
with no build step and no network.
"""

import json
import os
import random
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = int(os.environ.get("STUB_PORT", "8080"))
LATENCY_MIN_MS = int(os.environ.get("STUB_LATENCY_MIN_MS", "20"))
LATENCY_MAX_MS = int(os.environ.get("STUB_LATENCY_MAX_MS", "120"))

# Same list as src/load-generator/load-test.js, with real coordinates.
LOCATIONS = {
    ("linz", "austria"): (48.3059, 14.2862),
    ("graz", "austria"): (47.0707, 15.4395),
    ("berlin", "germany"): (52.5200, 13.4050),
    ("araraquara", "brazil"): (-21.7946, -48.1756),
    ("paris", "france"): (48.8566, 2.3522),
    ("madrid", "spain"): (40.4168, -3.7038),
    ("rome", "italy"): (41.9028, 12.4964),
    ("amsterdam", "netherlands"): (52.3676, 4.9041),
}


def _first(query: dict, key: str) -> str:
    return query.get(key, [""])[0].strip().lower()


def nominatim_search(query: dict) -> list:
    city, _, country = _first(query, "q").partition(",")
    coords = LOCATIONS.get((city.strip(), country.strip()))
    if coords is None:
        return []
    lat, lon = coords
    return [{
        "place_id": list(LOCATIONS).index((city.strip(), country.strip())) + 1,
        "lat": f"{lat:.7f}",
        "lon": f"{lon:.7f}",
        "display_name": f"{city.title()}, {country.title()}",
        "class": "boundary",
        "type": "administrative",
    }]


def open_meteo_geocoding(query: dict) -> dict:
    city, country = _first(query, "name"), _first(query, "country")
    coords = LOCATIONS.get((city, country))
    if coords is None:
        # The real API leaves "results" out when nothing matches.
        return {"generationtime_ms": 0.1}
    lat, lon = coords
    return {
        "results": [{
            "name": city.title(),
            "latitude": lat,
            "longitude": lon,
            "country": country.title(),
        }],
        "generationtime_ms": 0.1,
    }


def open_meteo_forecast(query: dict) -> dict:
    lat = float(_first(query, "latitude") or 0)
    lon = float(_first(query, "longitude") or 0)
    return {
        "latitude": lat,
        "longitude": lon,
        "current_units": {"temperature_2m": "°C", "wind_speed_10m": "km/h", "weather_code": "wmo code"},
        "current": {
            "time": time.strftime("%Y-%m-%dT%H:%M", time.gmtime()),
            "interval": 900,
            "temperature_2m": round(random.uniform(-5, 30), 1),
            "wind_speed_10m": round(random.uniform(0, 40), 1),
            "weather_code": random.choice([0, 1, 2, 3, 45, 61, 71, 80, 95]),
        },
    }


ROUTES = {
    "/search": nominatim_search,
    "/v1/search": open_meteo_geocoding,
    "/v1/forecast": open_meteo_forecast,
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/health":
            self._send(200, {"status": "ok"}, delay=False)
            return
        route = ROUTES.get(url.path)
        if route is None:
            self._send(404, {"error": f"no stub for {url.path}"}, delay=False)
            return
        try:
            body = route(parse_qs(url.query))
        except ValueError as e:
            self._send(400, {"error": str(e)}, delay=False)
            return
        self._send(200, body)

    def _send(self, status: int, body, delay: bool = True):
        if delay:
            time.sleep(random.uniform(LATENCY_MIN_MS, LATENCY_MAX_MS) / 1000)
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        pass  # one line per request would drown the compose logs


if __name__ == "__main__":
    print(f"stub-apis listening on :{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
