"""Contratto plugin bot (code / config / ai)."""

from __future__ import annotations

from typing import Any, Protocol


class BotPlugin(Protocol):
    """Interfaccia minima di un bot collaborativo."""

    name: str
    kind: str  # code | config | ai

    def on_session(self, session: dict) -> list[dict]: ...
    def on_tick(self, tick: dict, session: dict | None, orders: dict | None) -> list[dict]: ...
    def on_orders(self, orders: dict) -> list[dict]: ...
    def on_action(self, action: dict) -> list[dict]: ...
    def on_consult(self, message: dict) -> list[dict]: ...
    def on_round_start(self, session: dict) -> list[dict]: ...
    def on_round_end(self, payload: dict) -> list[dict]: ...


def empty_actions() -> list[dict]:
    return []
