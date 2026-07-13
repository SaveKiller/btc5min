from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import API_HOST, API_PORT
from protocol import RoundHeader
from rounds import list_rounds, load_round_header, load_ticks_by_sec
from session import StreamHub, StreamSession
from src.setup import STALL_RECONNECT_SEC

app = FastAPI(title="btc5min dash-api", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

hub = StreamHub()
session = StreamSession(hub, STALL_RECONNECT_SEC)


class ReplayStartBody(BaseModel):
    market_start_ts: int
    start_sec: int = 300


class SeekBody(BaseModel):
    sec: int


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/rounds")
def get_rounds(limit: int = 50) -> list[dict]:
    return list_rounds(limit)


@app.get("/rounds/{market_start_ts}/header", response_model=RoundHeader)
def get_round_header(market_start_ts: int) -> RoundHeader:
    return load_round_header(market_start_ts)


@app.get("/session")
def get_session() -> dict:
    if session.mode is None:
        return {"active": False}
    return {"active": True, **session.snapshot().model_dump()}


@app.post("/session/replay")
async def start_replay(body: ReplayStartBody) -> dict:
    header, ticks_by_sec = load_ticks_by_sec(body.market_start_ts, session.stall_reconnect_sec)
    await session.start_replay(header, ticks_by_sec, body.start_sec)
    return {"active": True, **session.snapshot().model_dump()}


@app.post("/session/live")
async def start_live() -> dict:
    await session.start_live()
    return {"active": True, **session.snapshot().model_dump()}


@app.post("/session/seek")
async def seek(body: SeekBody) -> dict:
    await session.seek(body.sec)
    return {"active": True, **session.snapshot().model_dump()}


@app.post("/session/play")
async def play() -> dict:
    await session.play()
    return {"active": True, **session.snapshot().model_dump()}


@app.post("/session/pause")
async def pause() -> dict:
    await session.pause()
    return {"active": True, **session.snapshot().model_dump()}


@app.post("/session/stop")
async def stop() -> dict:
    await session.stop()
    return {"active": False}


@app.websocket("/ws/stream")
async def ws_stream(ws: WebSocket) -> None:
    await hub.connect(ws)
    if session.mode is not None:
        await ws.send_json({"type": "session", "payload": session.snapshot().model_dump()})
    try:
        while True:
            raw = await ws.receive_text()
            await hub.handle_client_message(ws, raw)
    except WebSocketDisconnect:
        await hub.disconnect(ws)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=API_HOST, port=API_PORT, reload=True)
