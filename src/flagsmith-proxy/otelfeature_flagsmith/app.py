"""Flagsmith's Edge Proxy with a flagd endpoint and real-time updates.

    uvicorn otelfeature_flagsmith.app:app

The Edge Proxy keeps the environment document of each configured key pair
in memory and polls Flagsmith for it (here only as a fallback,
`API_POLL_FREQUENCY_SECONDS`). This module adds (UC-008 BR-010 to BR-012):

- `GET /api/v1/flagd/flags.json`, the document as a flagd flag set, for
  flagd's HTTP sync (`authHeader: Bearer <client-side key>`; the server-side
  key works too, but stays out of flagd's command line). A document the
  translation rejects is logged once, and the last good flag set stays.
- A subscription to Flagsmith's real-time stream per key pair
  (`FLAGSMITH_REALTIME_URL`; empty switches it off). On each event, and
  after each (re)connect, the document is fetched again, without
  `If-Modified-Since` (it has one-second granularity, so a change within the
  second of the last fetch would come back as 304), until it is at least as
  new as the event.
- The cache keeps the newer document: the Edge Proxy's poll writes back the
  document it held when its request started, which must not undo a newer
  one fetched for an event in the meantime.
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from urllib.parse import urljoin

import httpx
import structlog
from fastapi import Header
from fastapi.responses import ORJSONResponse

from edge_proxy.server import app, environment_service, settings
from edge_proxy.settings import EnvironmentKeyPair

from . import CATALOG
from .translate import TranslationError, gated_flags, load_catalog, load_presets, translate

logger = structlog.get_logger("otelfeature_flagsmith")

REALTIME_URL = os.environ.get("FLAGSMITH_REALTIME_URL", "https://realtime.flagsmith.com/")
# How often an event's document is fetched again while Flagsmith still serves an older one.
FRESH_ATTEMPTS, FRESH_DELAY = 10, 0.2
# A stream silent for this long is taken as dead and reconnected (which fetches once).
STREAM_READ_TIMEOUT = float(os.environ.get("FLAGSMITH_REALTIME_READ_TIMEOUT", "30"))

catalog, presets, gated = load_catalog(CATALOG), load_presets(), gated_flags()
# Per key: the document last translated (the cache replaces the object only
# when the content changes), and its flag set.
_translated: dict[str, tuple[dict, dict]] = {}
_rejected: dict[str, int] = {}


@app.get("/api/v1/flagd/flags.json", response_class=ORJSONResponse)
async def flagd_flags(authorization: str = Header(None)) -> ORJSONResponse:
    key = (authorization or "").removeprefix("Bearer").strip()
    document = environment_service.get_environment(environment_key=key)  # 401 for an unknown key
    last = _translated.get(key)
    if last is None or last[0] is not document:
        try:
            _translated[key] = (document, translate(document, catalog, presets, gated))
            _rejected.pop(key, None)
        except TranslationError as error:
            if _rejected.get(key) != id(document):
                _rejected[key] = id(document)
                logger.error("flagd_translation_rejected", reason=str(error),
                             updated_at=document.get("updated_at"),
                             serving=last[0].get("updated_at") if last else None)
            if last is None:
                return ORJSONResponse(status_code=503, content={"status": "error", "message": str(error)})
    return ORJSONResponse(_translated[key][1])


def _timestamp(document: dict | None) -> float:
    if not document or not document.get("updated_at"):
        return 0.0
    updated_at = datetime.fromisoformat(document["updated_at"])
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return updated_at.timestamp()


_put_environment = environment_service.cache.put_environment


def _put_newer(environment_api_key: str, environment_document: dict) -> bool:
    held = environment_service.cache.get_environment(environment_api_key)
    if held is not None and _timestamp(environment_document) < _timestamp(held):
        return False
    return _put_environment(environment_api_key=environment_api_key, environment_document=environment_document)


environment_service.cache.put_environment = _put_newer


async def _fetch(client: httpx.AsyncClient, pair: EnvironmentKeyPair) -> dict:
    response = await client.get(f"{settings.api_url}/environment-document/",
                                headers={"X-Environment-Key": pair.server_side_key})
    response.raise_for_status()
    document = response.json()
    if environment_service.cache.put_environment(environment_api_key=pair.client_side_key,
                                                 environment_document=document):
        await environment_service._clear_endpoint_caches()
    return document


def _fresh(pair: EnvironmentKeyPair, event_at: float) -> bool:
    return _timestamp(environment_service.cache.get_environment(pair.client_side_key)) >= event_at


async def _on_event(client: httpx.AsyncClient, pair: EnvironmentKeyPair, event_at: float) -> None:
    for attempt in range(FRESH_ATTEMPTS):
        if _fresh(pair, event_at):
            return
        if attempt:
            await asyncio.sleep(FRESH_DELAY)
        try:
            await _fetch(client, pair)
        except (httpx.HTTPError, ValueError):
            logger.exception("realtime_fetch_failed", client_side_key=pair.client_side_key)
    if not _fresh(pair, event_at):
        logger.warning("realtime_document_stale", client_side_key=pair.client_side_key, event_at=event_at)


async def _follow(pair: EnvironmentKeyPair) -> None:
    base = REALTIME_URL if REALTIME_URL.endswith("/") else REALTIME_URL + "/"
    url = urljoin(base, f"sse/environments/{pair.client_side_key}/stream")
    timeout = httpx.Timeout(settings.api_poll_timeout_seconds, read=STREAM_READ_TIMEOUT)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        while True:
            try:
                async with client.stream("GET", url, headers={"Accept": "text/event-stream"}) as response:
                    response.raise_for_status()
                    logger.info("realtime_connected", url=url)
                    # Events sent while the stream was down are gone: catch up once.
                    await _fetch(client, pair)
                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            event = json.loads(line[len("data:"):])
                            await _on_event(client, pair, float(event["updated_at"]))
            except asyncio.CancelledError:
                raise
            except httpx.ReadTimeout:
                logger.info("realtime_stream_silent", url=url, seconds=STREAM_READ_TIMEOUT)
            except Exception:
                logger.exception("realtime_stream_failed", url=url)
            await asyncio.sleep(1)


_edge_proxy_lifespan = app.router.lifespan_context


@asynccontextmanager
async def _lifespan(application):
    async with _edge_proxy_lifespan(application):
        tasks = [asyncio.create_task(_follow(pair)) for pair in settings.environment_key_pairs] if REALTIME_URL else []
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()


app.router.lifespan_context = _lifespan
