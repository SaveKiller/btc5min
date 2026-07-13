"""Protocollo streaming unificato replay/live — messaggi WebSocket verso la dashboard."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

StreamMode = Literal["replay", "live"]
StateReason = Literal["seek", "play", "pause", "stop", "round_end", "session_start"]


class RoundHeader(BaseModel):
    market_start_ts: int
    market_end_ts: int
    outcome: str
    tick_count: int
    ptb_chainlink: float
    ptb_gamma: float | None
    final_chainlink: float
    final_gamma: float | None


class SessionPayload(BaseModel):
    mode: StreamMode
    market_start_ts: int
    market_end_ts: int
    ptb_chainlink: float
    outcome: str
    playing: bool
    sec: int


class TickPayload(BaseModel):
    """Un tick al secondo — stesso formato in replay e live."""

    seq: int
    sec: int
    recv_ts_ms: int
    chainlink_btc: float | None
    chainlink_stale: bool
    up_bid: float | None
    up_ask: float | None
    down_bid: float | None
    down_ask: float | None
    delta_usd: int | None
    majority_gain: float | None
    partial: bool


class StatePayload(BaseModel):
    playing: bool
    sec: int
    reason: StateReason


class ErrorPayload(BaseModel):
    message: str


class WsEnvelope(BaseModel):
    type: Literal["session", "tick", "state", "error", "pong"]
    payload: dict[str, Any] = Field(default_factory=dict)


def ws_session(payload: SessionPayload) -> dict:
    return WsEnvelope(type="session", payload=payload.model_dump()).model_dump()


def ws_tick(payload: TickPayload) -> dict:
    return WsEnvelope(type="tick", payload=payload.model_dump()).model_dump()


def ws_state(payload: StatePayload) -> dict:
    return WsEnvelope(type="state", payload=payload.model_dump()).model_dump()


def ws_error(message: str) -> dict:
    return WsEnvelope(type="error", payload=ErrorPayload(message=message).model_dump()).model_dump()


def ws_pong() -> dict:
    return WsEnvelope(type="pong", payload={}).model_dump()
