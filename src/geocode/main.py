import asyncio
import os

import httpx
from fastapi import FastAPI, HTTPException
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.trace import SpanKind
from pydantic import BaseModel

from db import get_coordinates_from_db, insert_coordinates_into_db
from otel_setup import configure_telemetry

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = os.environ.get("NOMINATIM_USER_AGENT", "poc-otelfeature-geocode/1.0")

configure_telemetry()
Psycopg2Instrumentor().instrument()
HTTPXClientInstrumentor().instrument()

tracer = trace.get_tracer(__name__)

app = FastAPI(title="geocode")
FastAPIInstrumentor.instrument_app(app)


class GeocodeRequest(BaseModel):
    city: str
    country: str


class GeocodeResponse(BaseModel):
    latitude: float
    longitude: float


@app.post("/geocode", response_model=GeocodeResponse)
async def geocode(request: GeocodeRequest) -> GeocodeResponse:
    # Wraps the cache lookup / Nominatim call / persist steps below in one
    # INTERNAL span, purely to have something for TRACE_VERBOSITY_LEVEL=IO to
    # suppress - see otel_setup.py. Its children (the psycopg2/httpx CLIENT
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
