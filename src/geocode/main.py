import asyncio
import os

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from db import get_coordinates_from_db, insert_coordinates_into_db

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = os.environ.get("NOMINATIM_USER_AGENT", "poc-otelfeature-geocode/1.0")

app = FastAPI(title="geocode")


class GeocodeRequest(BaseModel):
    city: str
    country: str


class GeocodeResponse(BaseModel):
    latitude: float
    longitude: float


@app.post("/geocode", response_model=GeocodeResponse)
async def geocode(request: GeocodeRequest) -> GeocodeResponse:
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
