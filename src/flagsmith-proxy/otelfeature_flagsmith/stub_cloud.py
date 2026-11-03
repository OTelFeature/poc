"""A stub of Flagsmith Cloud for `make flagsmith-test` (TC-008 items 3 to 5).

    uvicorn otelfeature_flagsmith.stub_cloud:app --port 8080

It holds one environment as the model (otelfeature_flagsmith.model) and
serves what the proxy reads from Flagsmith:

- `GET /api/v1/environment-document/` with the server-side key, honouring
  `If-Modified-Since` the way Flagsmith does (whole seconds), and counting
  requests, so a test can see how many fetches a flip costs.
- `GET /sse/environments/<client-side key>/stream`, Flagsmith's real-time
  stream: one `environment_updated` event per change, with its updated_at.

Instead of the Admin API the CLI writes to, tests drive it with:

- `POST /stub/apply/<preset>`: the preset command's CLI calls, applied one by
  one, each a change of its own (and an event), as the real CLI makes them.
- `POST /stub/cli` with a JSON list: one CLI call.
- `POST /stub/realtime/on|off`: stop or resume sending events.
"""

from __future__ import annotations

import asyncio
import json
import os
from email.utils import parsedate_to_datetime

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .model import CLIError, Environment
from .preset import apply_plan, execute, seed_plan

SERVER_KEY = os.environ.get("FLAGSMITH_SERVER_KEY", "ser.stub")
CLIENT_KEY = os.environ.get("FLAGSMITH_CLIENT_KEY", "stub")
# Time between two CLI calls, roughly one Admin API round trip.
CLI_DELAY = float(os.environ.get("STUB_CLI_DELAY", "0.05"))

app = FastAPI()
environment = Environment(client_key=CLIENT_KEY)
execute(seed_plan(environment.document()), environment.run)
execute(apply_plan("00-baseline", environment.document()), environment.run)
state = {"realtime": True, "fetches": 0, "events": 0}
_subscribers: set[asyncio.Queue] = set()


def _changed() -> None:
    if not state["realtime"]:
        return
    state["events"] += 1
    for queue in _subscribers:
        queue.put_nowait(environment.updated_at.timestamp())


@app.get("/api/v1/environment-document/")
async def environment_document(x_environment_key: str = Header(None),
                               if_modified_since: str = Header(None)) -> Response:
    if x_environment_key != SERVER_KEY:
        return JSONResponse(status_code=401, content={"detail": "Invalid server-side key"})
    state["fetches"] += 1
    if if_modified_since:
        try:
            since = parsedate_to_datetime(if_modified_since)
        except (TypeError, ValueError):
            since = None
        if since is not None and environment.updated_at.replace(microsecond=0) <= since:
            return Response(status_code=304)
    return JSONResponse(environment.document())


@app.get("/sse/environments/{key}/stream")
async def stream(key: str, request: Request) -> Response:
    if key != CLIENT_KEY:
        return JSONResponse(status_code=404, content={"detail": "Not found"})
    queue: asyncio.Queue = asyncio.Queue()
    _subscribers.add(queue)

    async def events():
        try:
            while not await request.is_disconnected():
                try:
                    updated_at = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"event: environment_updated\ndata: {json.dumps({'updated_at': updated_at})}\n\n"
        finally:
            _subscribers.discard(queue)

    return StreamingResponse(events(), media_type="text/event-stream")


async def _run(argv: list[str]) -> None:
    environment.run(argv)
    _changed()
    await asyncio.sleep(CLI_DELAY)


@app.post("/stub/apply/{preset}")
async def stub_apply(preset: str) -> dict:
    plan = apply_plan(preset, environment.document())
    for argv in plan:
        await _run(argv)
    return {"calls": len(plan), "updated_at": environment.updated_at.timestamp()}


@app.post("/stub/cli")
async def stub_cli(argv: list[str]) -> Response:
    try:
        await _run(argv)
    except CLIError as error:
        return JSONResponse(status_code=400, content={"detail": str(error)})
    return JSONResponse({"updated_at": environment.updated_at.timestamp()})


@app.post("/stub/realtime/{mode}")
async def stub_realtime(mode: str) -> dict:
    state["realtime"] = mode == "on"
    return state


@app.get("/stub/state")
async def stub_state() -> dict:
    return state
