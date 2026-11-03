"""Local web server for a TV and a robot vacuum: REST + live updates (SSE) + a phone-friendly page.

    python -m uvicorn app:app --host 0.0.0.0 --port 8080

LAN only, no login: don't expose it to the internet. DEMO=1 uses pretend devices.
"""
import asyncio
import json
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

import devices
import settings

STATIC = Path(__file__).parent / "static"
DEMO = os.environ.get("DEMO") == "1"
cfg = {"tv": {"driver": "fake"}, "vacuum": {"driver": "fake"}} if DEMO else settings.config()

version, lock = 0, threading.Lock()


def bump():
    """Something changed: every open page gets the new state."""
    global version
    with lock:
        version += 1


events_log = []     # recent alerts from the vacuum (also printed)


def on_event(kind, text):
    events_log.append({"t": time.time(), "kind": kind, "text": text})
    del events_log[:-20]
    print("event:", kind, text)
    bump()


tv = devices.make_tv(cfg["tv"], bump) if "tv" in cfg else None
vac = devices.make_vacuum(cfg["vacuum"], bump, on_event) if "vacuum" in cfg else None

@asynccontextmanager
async def lifespan(_):
    if tv:
        tv.start()
    if vac:
        vac.start()
    yield


app = FastAPI(title="TV + vacuum remote", lifespan=lifespan)


def state():
    return {"tv": tv.view() if tv else None, "vacuum": vac.view() if vac else None,
            "alerts": events_log[-5:][::-1]}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/state")
def get_state():
    return state()


@app.get("/api/events")
async def events():
    async def stream():
        seen, last = -1, 0.0
        while True:
            if version != seen:
                seen, last = version, time.monotonic()
                yield f"data: {json.dumps(state())}\n\n"
            elif time.monotonic() - last > 15:
                last = time.monotonic()
                yield ": keepalive\n\n"
            await asyncio.sleep(0.15)
    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def call(fn, *args):
    """Run a device call and turn its errors into HTTP codes the page understands."""
    try:
        fn(*args)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    except Exception:
        raise HTTPException(502, "Couldn't reach the device")
    return {"ok": True, **state()}


def need(dev, what):
    if not dev:
        raise HTTPException(404, f"No {what} configured")
    return dev


class Key(BaseModel):
    key: str


class Power(BaseModel):
    on: bool


class App(BaseModel):
    id: str


@app.post("/api/tv/warm")
def tv_warm():
    need(tv, "TV").warm()
    return {"ok": True}


@app.post("/api/tv/key")
def tv_key(body: Key):
    return call(need(tv, "TV").key, body.key)


@app.post("/api/tv/power")
def tv_power(body: Power):
    return call(need(tv, "TV").power, body.on)


@app.post("/api/tv/app")
def tv_app(body: App):
    return call(need(tv, "TV").app, body.id)


@app.get("/api/vacuum")
def vacuum_view():
    """Last known state. Reading it never wakes the robot."""
    return need(vac, "vacuum").view() or {}


@app.post("/api/vacuum-refresh")
def vacuum_refresh():
    need(vac, "vacuum").refresh()
    return {"ok": True}


@app.post("/api/vacuum/{cmd}")
def vacuum_command(cmd: str):
    return call(need(vac, "vacuum").command, cmd)
