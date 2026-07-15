"""Envelope IPC tra processo server e processo dati."""

from __future__ import annotations

import uuid
from typing import Any


def make_request(cmd: str, payload: dict | None = None, request_id: str | None = None) -> dict:
    return {"kind": "request", "request_id": request_id or uuid.uuid4().hex, "cmd": cmd, "payload": payload or {}}


def make_response(request_id: str, payload: dict | None = None) -> dict:
    return {"kind": "response", "request_id": request_id, "payload": payload or {}}


def make_error(request_id: str, message: str) -> dict:
    return {"kind": "response", "request_id": request_id, "error": message}


def make_event(name: str, payload: dict | None = None) -> dict:
    return {"kind": "event", "name": name, "payload": payload or {}}


def is_response(msg: dict) -> bool:
    return msg.get("kind") == "response"


def is_event(msg: dict) -> bool:
    return msg.get("kind") == "event"
