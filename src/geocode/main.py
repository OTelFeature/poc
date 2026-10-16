import asyncio
import math
import os
import random

import httpx
from fastapi import FastAPI, HTTPException
from openfeature import api as openfeature_api
from opentelemetry import trace
from opentelemetry.trace import SpanKind
from pydantic import BaseModel

from db import get_coordinates_from_db, insert_coordinates_into_db

NOMINATIM_URL = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
USER_AGENT = os.environ.get("NOMINATIM_USER_AGENT", "poc-otelfeature-geocode/1.0")
WEATHER_URL = os.environ.get("WEATHER_URL", "http://weather:8001")

tracer = trace.get_tracer(__name__)

# Fault injection (FR-012, UC-006 A3, OTelFeature/poc#80): the share of
# /geocode requests (and so /forecast) that fail with 503, from the number
# flag geocodeUpstreamFailure. Evaluated through geocode's own client on the
# OpenFeature API otelfeature-instrument already set a flagd provider on.
# No API-level (global) hooks: those would also see the extension's own
# evaluations, which must stay unrecorded (FR-014).
# A missing flag (the stage presets don't define it) resolves to 0.0.
FAULT_FLAG = "geocodeUpstreamFailure"
flags = openfeature_api.get_client("geocode")


def maybe_fail() -> None:
    share = flags.get_float_value(FAULT_FLAG, 0.0)
    # flagd accepts a boolean variant for a float flag (bool is an int);
    # non-numbers act as 0.0 (UC-006 A2).
    if isinstance(share, bool) or math.isnan(share) or share <= 0.0:
        return
    if share >= 1.0 or random.random() < share:
        raise HTTPException(status_code=503, detail=f"Injected upstream failure ({FAULT_FLAG}={share})")


app = FastAPI(title="geocode")


class GeocodeRequest(BaseModel):
    city: str
    country: str


class GeocodeResponse(BaseModel):
    latitude: float
    longitude: float


class ForecastResponse(BaseModel):
    latitude: float
    longitude: float
    weather: dict


@app.post("/geocode", response_model=GeocodeResponse)
async def geocode(request: GeocodeRequest) -> GeocodeResponse:
    # Before the cache lookup, so the error rate doesn't depend on cache hits.
    maybe_fail()
    # Wraps the cache lookup / Nominatim call / persist steps below in one
    # INTERNAL span, purely to have something for otelfeature-instrument's
    # telemetryLevel=IO to suppress. Its children (the psycopg2/httpx CLIENT
    # spans) are unaffected either way; they only lose this wrapper as a
    # parent when it's suppressed, attaching directly to the FastAPI SERVER
    # span instead.
    with tracer.start_as_current_span("geocode.resolve", kind=SpanKind.INTERNAL):
        cached = await asyncio.to_thread(get_coordinates_from_db, request.city, request.country)
        if cached is not None:
            latitude, longitude = cached
            return GeocodeResponse(latitude=latitude, longitude=longitude)

        async with httpx.AsyncClient() as client:
            response = await client.get(
                NOMINATIM_URL,
                params={"format": "json", "q": f"{request.city},{request.country}"},
                headers={"User-Agent": USER_AGENT},
            )
        response.raise_for_status()
        results = response.json()

        for result in results:
            if "lat" in result and "lon" in result:
                latitude, longitude = float(result["lat"]), float(result["lon"])
                await asyncio.to_thread(
                    insert_coordinates_into_db, request.city, request.country, latitude, longitude
                )
                return GeocodeResponse(latitude=latitude, longitude=longitude)

        raise HTTPException(status_code=404, detail="No location found for the given city/country")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/forecast", response_model=ForecastResponse)
async def forecast(request: GeocodeRequest) -> ForecastResponse:
    """The cross-service path (FR-026): resolve the coordinates, then ask
    `weather` for the current weather over HTTP. The httpx instrumentation
    propagates the trace context, so `geocode` is the trace's entry point and
    `weather` follows its sampling decision. A failing or unreachable
    `weather` call fails this request too (502); an unknown location is a
    404, as on /geocode."""
    coordinates = await geocode(request)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{WEATHER_URL}/weather", json=request.model_dump())
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"weather unreachable: {type(e).__name__}") from e
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"weather answered HTTP {response.status_code}")
    try:
        weather = response.json()
    except ValueError as e:
        raise HTTPException(status_code=502, detail="weather answered with invalid JSON") from e
    return ForecastResponse(latitude=coordinates.latitude, longitude=coordinates.longitude, weather=weather)
